"""Episode downloads share one small disk with SQLite, logs and the nightly backup.

A full disk stops the WAL, and every role with it. Send workers reserve
bytes before writing an episode and grow the reservation as the file grows.
What does not fit now waits (DiskBusy, retryable). What could not fit even
on an otherwise idle disk is refused (DiskTooSmall).
"""
import os
import shutil
import threading

MB = 1024 * 1024

# Left free for db/yourcast.db + WAL, logs and the backup tarball of db/.
MIN_FREE_BYTES = 512 * MB
# HEAD had no Content-Length: start here and grow while downloading.
UNKNOWN_SIZE_BYTES = 100 * MB
GROW_STEP_BYTES = 64 * MB
RETRY_AFTER_SECONDS = 60


class DiskBusy(Exception):
    """Other downloads hold the space. Try again after retry_after_seconds."""

    def __init__(self, need, headroom, retry_after_seconds=RETRY_AFTER_SECONDS):
        super().__init__(
            "disk busy: need %d MB, %d MB free for downloads" % (need // MB, max(headroom, 0) // MB))
        self.retry_after_seconds = retry_after_seconds


class DiskTooSmall(Exception):
    """The file would not fit even if no other download were running."""

    def __init__(self, need, capacity):
        super().__init__(
            "disk too small: need %d MB, at most %d MB for downloads" % (need // MB, max(capacity, 0) // MB))


class Reservation:
    def __init__(self, budget, limit):
        self._budget = budget
        self.limit = limit
        self.written = 0

    def outstanding(self):
        return max(self.limit - self.written, 0)

    def wrote(self, nbytes):
        """Record progress; raises DiskBusy / DiskTooSmall if the file outgrew what it can get."""
        self._budget._grow(self, nbytes)

    def release(self):
        """Call after the file is deleted."""
        self._budget._release(self)


class DiskBudget:
    def __init__(self, path, min_free_bytes=MIN_FREE_BYTES, disk_free=None,
                 unknown_size_bytes=UNKNOWN_SIZE_BYTES, grow_step_bytes=GROW_STEP_BYTES):
        self._disk_free = disk_free or (lambda: shutil.disk_usage(path).free)
        self._min_free = min_free_bytes
        self._unknown_size = unknown_size_bytes
        self._grow_step = grow_step_bytes
        self._lock = threading.Lock()
        self._live: list[Reservation] = []

    def reserve(self, size_bytes):
        need = int(size_bytes) if size_bytes else self._unknown_size
        with self._lock:
            self._check(need)
            reservation = Reservation(self, need)
            self._live.append(reservation)
            return reservation

    def _grow(self, reservation, nbytes):
        with self._lock:
            # Bytes already written are already gone from free space.
            reservation.written = nbytes
            if nbytes <= reservation.limit:
                return
            self._check(self._grow_step, growing=reservation)
            reservation.limit = nbytes + self._grow_step

    def _release(self, reservation):
        with self._lock:
            if reservation in self._live:
                self._live.remove(reservation)

    def _check(self, need, growing=None):
        free = self._disk_free()
        headroom = free - self._min_free - sum(r.outstanding() for r in self._live)
        if need <= headroom:
            return
        # Other downloads delete their files when done: what they wrote comes back.
        # The growing file keeps its own bytes.
        capacity = free - self._min_free + sum(r.written for r in self._live if r is not growing)
        if need > capacity:
            raise DiskTooSmall(need, capacity)
        raise DiskBusy(need, headroom)


class BudgetedDownload:
    """One downloaded file: its path, the space it holds and its cleanup, together."""

    CHUNK_BYTES = 32769

    def __init__(self, budget, path, expected_bytes=None):
        self.path = path
        self._budget = budget
        self._expected_bytes = expected_bytes
        self._reservation = None

    def fetch(self, requester, url, progress=None):
        """Reserve, then stream to disk. DiskBusy / DiskTooSmall before or during."""
        if self._reservation is None:
            self._reservation = self._budget.reserve(self._expected_bytes)

        def on_chunk(done, total):
            self._reservation.wrote(done)
            if progress is not None:
                progress(done, total)

        requester.download_chunked(url, self.path, chunk_size=self.CHUNK_BYTES, callback=on_chunk)

    def size_bytes(self):
        return os.path.getsize(self.path) if os.path.isfile(self.path) else 0

    def close(self):
        """Delete the file and give its space back. Safe to call twice."""
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
        finally:
            if self._reservation is not None:
                self._reservation.release()
                self._reservation = None
