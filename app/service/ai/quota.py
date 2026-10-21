# -*- coding: utf-8 -*-
"""Who may ask for a new AI summary: hours of audio per 30 days by plan.

A new summary takes the episode's length from the asker's plan quota
(config.ai_summary_hours_per_month, by plan level). What a summary costs
grows with the audio (transcription bills by the second), so a count of
summaries would let long episodes cost more than the plan brings. The
charges themselves are ai_requests.seconds (db/ai.py). Without a plan
only summaries someone already made, which are free.

A plan nobody paid for yet (the welcome Relay, referral days) has
config.ai_summary_trial_hours whatever its level: every new user gets
two weeks of Relay. The first payment opens the plan's own hours.
"""
import time
from typing import NamedTuple

from config import ai_summary_hours_per_month, ai_summary_trial_hours
from db import ai
from db.tariff_rows import ever_paid, running_plan_level

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
    trial: bool = False

    @property
    def left(self) -> int:
        return max(self.limit - self.used, 0)

    @property
    def top_plan(self) -> bool:
        """Nothing bigger to sell: the top plan, paid for."""
        return not self.trial and self.level >= max(ai_summary_hours_per_month, default=0)


def seconds_needed(episode) -> int:
    """What a new summary of `episode` takes: its length, an hour if the feed has none."""
    return int(episode.get('seconds') or 0) or UNKNOWN_SECONDS


def check(chat_id, needed, level=None, trial=False, now=None, database=None) -> Quota:
    """May this chat ask for a new summary of `needed` seconds of audio? Its requests of the
    last 30 days count, done and on their way; one someone else's summary served counts 0.
    `level` and `trial` are read for the chat unless given."""
    if level is None:
        level = running_plan_level(chat_id, database)
        trial = level > 0 and not ever_paid(chat_id, database)
    level, trial = int(level), bool(trial)
    hours = ai_summary_trial_hours if trial else ai_summary_hours_per_month.get(level, 0)
    limit = int(hours * 3600)
    since = (time.time() if now is None else now) - QUOTA_DAYS * 86400
    used = ai.seconds_used(chat_id, since, database)
    return Quota(limit > 0 and used + needed <= limit, limit, used, int(needed), level, trial)


# Questions about an episode (summaryModule.ask): one model call each, a few
# tenths of a cent with the transcript cached, so a count per day is enough
QUESTIONS_PER_DAY = 20
TRIAL_QUESTIONS_PER_DAY = 5


class Questions(NamedTuple):
    allowed: bool
    limit: int  # 0: no plan
    left: int


def questions(chat_id, now=None, database=None) -> Questions:
    """Questions left today (the last 24 hours) for this chat: a running plan only, fewer on a trial."""
    from db import usage
    level = running_plan_level(chat_id, database)
    if level <= 0:
        return Questions(False, 0, 0)
    limit = TRIAL_QUESTIONS_PER_DAY if not ever_paid(chat_id, database) else QUESTIONS_PER_DAY
    since = (time.time() if now is None else now) - 86400
    left = max(limit - usage.count_since(chat_id, 'ask', since, database), 0)
    return Questions(left > 0, limit, left)
