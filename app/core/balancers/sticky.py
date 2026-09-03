# -*- coding: utf-8 -*-
"""Sticky least-loaded slot assignment for incoming and outgoing workers.

Same user stays on the same worker so FSM/shelve mutations for one chat do
not interleave. New users go to a least-loaded slot; ties rotate so work
does not pile onto slot 0.
"""


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
