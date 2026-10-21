# -*- coding: utf-8 -*-
"""Who may ask for a new AI summary: hours of audio per 30 days by plan.

A new summary takes the episode's length from the asker's plan quota
(config.ai_summary_hours_per_month, by plan level). What a summary costs
grows with the audio (transcription bills by the second), so a count of
summaries would let long episodes cost more than the plan brings. The
charges themselves are ai_requests.seconds (db/ai.py). Without a plan
only summaries someone already made, which are free.
"""
import time
from typing import NamedTuple

from config import ai_summary_hours_per_month
from db import ai
from db.tariff_rows import running_plan_level

QUOTA_DAYS = 30
# a feed without itunes:duration: charged an hour until Whisper measures the audio
UNKNOWN_SECONDS = 3600


class Quota(NamedTuple):
    """Seconds of audio: the plan's limit for 30 days, used so far, what this episode needs."""
    allowed: bool
    limit: int
    used: int
    needed: int
    level: int

    @property
    def left(self) -> int:
        return max(self.limit - self.used, 0)

    @property
    def top_plan(self) -> bool:
        return self.level >= max(ai_summary_hours_per_month, default=0)


def seconds_needed(episode) -> int:
    """What a new summary of `episode` takes: its length, an hour if the feed has none."""
    return int(episode.get('seconds') or 0) or UNKNOWN_SECONDS


def check(chat_id, needed, level=None, now=None, database=None) -> Quota:
    """May this chat ask for a new summary of `needed` seconds of audio? Its requests of the
    last 30 days count, done and on their way; one someone else's summary served counts 0."""
    level = running_plan_level(chat_id, database) if level is None else int(level)
    limit = int(ai_summary_hours_per_month.get(level, 0) * 3600)
    since = (time.time() if now is None else now) - QUOTA_DAYS * 86400
    used = ai.seconds_used(chat_id, since, database)
    return Quota(limit > 0 and used + needed <= limit, limit, used, int(needed), level)
