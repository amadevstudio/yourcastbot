# -*- coding: utf-8 -*-
"""Reentrant mutex that is safe across threads and processes.

The process lock is flock(2) on a sibling file. Nested acquires from the
same thread (storage helpers calling each other) do not unlock early.
"""
import os
import threading
from types import TracebackType
from typing import Optional


class InterprocessLock:
    def __init__(self, path: str):
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._fh = open(path, "a+")
        self._thread = threading.RLock()
        self._depth = 0

    def acquire(self) -> None:
        self._thread.acquire()
        if self._depth == 0:
            import fcntl
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
        self._depth += 1

    def release(self) -> None:
        self._depth -= 1
        if self._depth == 0:
            import fcntl
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        self._thread.release()

    def __enter__(self) -> "InterprocessLock":
        self.acquire()
        return self

    def __exit__(
            self,
            exc_type: Optional[type[BaseException]],
            exc: Optional[BaseException],
            tb: Optional[TracebackType]
    ) -> None:
        self.release()
