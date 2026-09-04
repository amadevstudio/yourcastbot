# -*- coding: utf-8 -*-
"""Per-user serialization for incoming handlers.

FSM/shelve must not interleave for one chat. That is a lock on the user,
not a pin onto one worker: pinning puts every other chat booked on that
slot behind a slow request.

StickySlotAssigner is kept for tests/history; incoming workers share one
queue and take UserGate.
"""
import threading
from contextlib import contextmanager


def incoming_user_id(input_data):
    if not isinstance(input_data, dict):
        return None
    data = input_data.get('data')
    if isinstance(data, dict):
        chat_id = data.get('chat_id')
        if chat_id is not None:
            return chat_id
        inline = data.get('inline')
        if inline is not None:
            return getattr(inline, 'user_id', None)
        return None
    return input_data.get('user_id')


class UserGate:
    """One lock per user_id. Another user's request never waits on it."""

    def __init__(self):
        self._guard = threading.Lock()
        self._locks = {}
        self._anon = threading.Lock()

    def _lock_for(self, user_id):
        if user_id is None:
            return self._anon
        with self._guard:
            lock = self._locks.get(user_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[user_id] = lock
            return lock

    @contextmanager
    def hold(self, user_id):
        lock = self._lock_for(user_id)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()


class StickySlotAssigner:
    def __init__(self):
        self.user_slots = {}
        self._rr = 0

    def choose(self, user_id, qsizes):
        n = len(qsizes)
        if n == 0:
            raise ValueError("no worker slots")
        if user_id is not None:
            slot = self.user_slots.get(user_id)
            if slot is not None and 0 <= slot < n:
                return slot
        min_q = min(qsizes)
        candidates = [i for i, size in enumerate(qsizes) if size == min_q]
        slot = candidates[self._rr % len(candidates)]
        self._rr += 1
        if user_id is not None:
            self.user_slots[user_id] = slot
        return slot

    def release_idle(self, empty_flags):
        for user_id, slot in list(self.user_slots.items()):
            if slot >= len(empty_flags) or empty_flags[slot]:
                self.user_slots.pop(user_id, None)
