# -*- coding: utf-8 -*-
"""Disk budget for episode downloads. No real disk writes.

Run from the repo root: python lib/system/test_disk_budget.py
"""
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from lib.system.disk_budget import MB, BudgetedDownload, DiskBudget, DiskBusy, DiskTooSmall  # noqa: E402


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _raises(exc, fn, label):
    try:
        fn()
    except exc as e:
        print("ok  %s (%s)" % (label, e))
        return e
    raise AssertionError("%s: %s not raised" % (label, exc.__name__))


class FakeDisk:
    """Free space that shrinks as files are written and grows when deleted."""

    def __init__(self, free_mb):
        self.free = free_mb * MB

    def write(self, reservation, total_mb):
        # Like download_chunked: bytes hit the disk, then the progress callback runs.
        self.free -= total_mb * MB - reservation.written
        reservation.wrote(total_mb * MB)

    def delete(self, reservation):
        self.free += reservation.written
        reservation.release()


def main():
    # Production today: 1.5 GB free, 512 MB kept for db/logs/backup.
    disk = FakeDisk(1500)
    budget = DiskBudget("/unused", min_free_bytes=512 * MB, disk_free=lambda: disk.free)

    mix = budget.reserve(408 * MB)
    _assert(mix is not None, "408 MB Radio Record mix fits")
    chart = budget.reserve(130 * MB)
    _assert(chart is not None, "second circle worker fits alongside")

    # 1500 - 512 - 408 - 130 = 450 MB headroom left.
    busy = _raises(DiskBusy, lambda: budget.reserve(500 * MB), "third download waits, it does not start")
    _assert(busy.retry_after_seconds > 0, "busy tells the outbox when to retry")

    # Progress does not double-count: written bytes left free space and the reservation.
    disk.write(mix, 400)
    _assert(budget.reserve(40 * MB) is not None, "headroom stays 450 MB while the mix downloads")

    _raises(DiskTooSmall, lambda: budget.reserve(2000 * MB),
            "a file bigger than the whole download space is refused, not retried")

    # Finished and deleted: space returns.
    disk.write(mix, 408)
    disk.delete(mix)
    _assert(budget.reserve(400 * MB) is not None, "deleted download frees its reservation")

    # Unknown size (HEAD without Content-Length) starts small and grows.
    disk2 = FakeDisk(900)
    budget2 = DiskBudget("/unused", min_free_bytes=512 * MB, disk_free=lambda: disk2.free,
                         unknown_size_bytes=100 * MB, grow_step_bytes=64 * MB)
    unknown = budget2.reserve(None)
    _assert(unknown.limit == 100 * MB, "unknown size reserves the default")
    disk2.write(unknown, 150)
    _assert(unknown.limit >= 150 * MB, "reservation grows with the file")
    disk2.write(unknown, 300)
    _raises(DiskTooSmall, lambda: disk2.write(unknown, 400),
            "a file outgrowing the disk stops the download")

    # A second reservation blocks growth only while it holds space.
    disk3 = FakeDisk(1000)
    budget3 = DiskBudget("/unused", min_free_bytes=512 * MB, disk_free=lambda: disk3.free,
                         unknown_size_bytes=100 * MB, grow_step_bytes=64 * MB)
    growing = budget3.reserve(None)
    other = budget3.reserve(300 * MB)
    _raises(DiskBusy, lambda: disk3.write(growing, 200), "growth waits for another download's space")
    other.release()
    disk3.write(growing, 200)
    _assert(growing.limit >= 200 * MB, "growth resumes after the other download is gone")

    # BudgetedDownload keeps path, reservation and cleanup together.
    class Requester:
        def __init__(self, size):
            self.size = size

        def download_chunked(self, url, destination, chunk_size=None, callback=None):
            with open(destination, 'wb') as f:
                for done in range(chunk_size, self.size + chunk_size, chunk_size):
                    f.truncate(min(done, self.size))
                    callback(min(done, self.size), self.size)

    directory = tempfile.mkdtemp(prefix="yourcast_budget_")
    budget4 = DiskBudget(directory, min_free_bytes=0, disk_free=lambda: 10 * MB)
    seen = []
    download = BudgetedDownload(budget4, os.path.join(directory, "ep.mp3"), expected_bytes=3 * MB)
    download.fetch(Requester(3 * MB), "https://cdn.example/ep.mp3", progress=lambda d, t: seen.append(d))
    _assert(download.size_bytes() == 3 * MB and seen[-1] == 3 * MB, "file written, progress passed on")
    _assert(len(budget4._live) == 1, "space held while the file exists")
    download.close()
    download.close()
    _assert(not os.path.exists(download.path) and budget4._live == [], "close deletes and releases, twice is fine")

    full = DiskBudget(directory, min_free_bytes=0, disk_free=lambda: 1 * MB)
    refused = BudgetedDownload(full, os.path.join(directory, "big.mp3"), expected_bytes=5 * MB)
    _raises(DiskTooSmall, lambda: refused.fetch(Requester(5 * MB), "https://cdn.example/big.mp3"),
            "no space: refused before writing")
    _assert(not os.path.exists(refused.path), "nothing written when refused")

    print("all disk budget checks passed")


if __name__ == "__main__":
    main()
