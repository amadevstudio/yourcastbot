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
two weeks of Relay. The first payment opens the plan's own hours; a
Patreon pledge credited to the balance is a payment (tariff_rows.paid_for_days).

A plan paid for also has a budget (`budget`): what its AI cost in the last
30 days (the usage ledger) stays under config.ai_budget_share of what its price
brings. A call starts only if what it is reckoned to cost fits what is left; the
paid model is used only if the episode fits at its rate. Hours and questions are
what users see; the budget is the owner's rule that no plan costs more than it
brings, whatever the rates and transcripts' lengths.
"""
import time
from typing import NamedTuple

import config
from config import ai_summary_hours_per_month, ai_summary_trial_hours
from db import ai
from db.tariff_rows import paid_for_days, running_plan_level, running_plan_price

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
    budget: bool = False  # refused by the plan's budget, not by its hours

    @property
    def left(self) -> int:
        return max(self.limit - self.used, 0)

    @property
    def top_plan(self) -> bool:
        """Nothing bigger to sell: the top plan, paid for."""
        return not self.trial and self.level >= max(ai_summary_hours_per_month, default=0)


class Budget(NamedTuple):
    """USD: the most this plan's AI may cost in 30 days, and what it cost in the last 30 days."""
    limit: float
    spent: float

    def fits(self, cost: float) -> bool:
        return self.spent + cost <= self.limit


def budget(chat_id, now=None, database=None) -> Budget | None:
    """The budget of a plan paid for; None for a trial (its own few hours and questions), no plan,
    or a plan without a price."""
    if running_plan_level(chat_id, database) <= 0 or not paid_for_days(chat_id, database):
        return None
    from db import usage
    price = running_plan_price(chat_id, database) / 100.0
    if price <= 0:
        return None
    share = config.payout_share.get('telegramStars', 1.0) * config.ai_budget_share
    since = (time.time() if now is None else now) - QUOTA_DAYS * 86400
    return Budget(price * share, usage.ai_spent_since(chat_id, since, database))


def transcribe_cost(seconds, paid_model=False) -> float:
    """What a new transcript of `seconds` and a model call on it are reckoned to cost."""
    rate = config.ai_paid_transcribe_usd_hour if paid_model else config.ai_transcribe_usd_hour
    return (seconds or UNKNOWN_SECONDS) / 3600.0 * rate + config.ai_call_usd


def paid_transcribe_fits(chat_id, seconds, now=None, database=None) -> bool:
    """Does making this episode's transcript with the paid model fit the plan's hours of it
    (config.ai_paid_transcribe_hours_per_month) and the plan's budget?"""
    level = running_plan_level(chat_id, database)
    if level <= 0 or not paid_for_days(chat_id, database):  # a plan paid for only
        return False
    limit = config.ai_paid_transcribe_hours_per_month.get(level, 0) * 3600
    since = (time.time() if now is None else now) - QUOTA_DAYS * 86400
    if ai.paid_seconds_used(chat_id, since, database) + (seconds or UNKNOWN_SECONDS) > limit:
        return False
    left = budget(chat_id, now, database)
    return left is None or left.fits(transcribe_cost(seconds, paid_model=True))


def seconds_needed(episode) -> int:
    """What a new summary of `episode` takes: its length, an hour if the feed has none."""
    return int(episode.get('seconds') or 0) or UNKNOWN_SECONDS


def check(chat_id, needed, level=None, trial=False, now=None, database=None) -> Quota:
    """May this chat ask for a new summary of `needed` seconds of audio? Its requests of the
    last 30 days count, done and on their way; one someone else's summary served counts 0.
    `level` and `trial` are read for the chat unless given."""
    if level is None:
        level = running_plan_level(chat_id, database)
        trial = level > 0 and not paid_for_days(chat_id, database)
    level, trial = int(level), bool(trial)
    hours = ai_summary_trial_hours if trial else ai_summary_hours_per_month.get(level, 0)
    limit = int(hours * 3600)
    since = (time.time() if now is None else now) - QUOTA_DAYS * 86400
    used = ai.seconds_used(chat_id, since, database)
    allowed = limit > 0 and used + needed <= limit
    if allowed and not trial:
        left = budget(chat_id, now, database)
        cost = transcribe_cost(needed) if needed else config.ai_call_usd
        if left is not None and not left.fits(cost):
            return Quota(False, limit, used, int(needed), level, trial, budget=True)
    return Quota(allowed, limit, used, int(needed), level, trial)


# Questions about an episode (summaryModule.ask): one model call each, a few
# tenths of a cent with the transcript cached, so a count per day (config.ai_questions_per_day by
# plan level), one per 30 days (config.ai_questions_per_month) and the budget are enough.
# QUESTIONS_PER_DAY: the most a plan gives ("up to")
QUESTIONS_PER_DAY = max(config.ai_questions_per_day.values(), default=0)
TRIAL_QUESTIONS_PER_DAY = 5
TRIAL_QUESTIONS_PER_MONTH = 50


class Questions(NamedTuple):
    allowed: bool
    limit: int  # 0: no plan
    left: int
    trial: bool = False
    budget: bool = False  # refused by the plan's budget, not by the day's count
    level: int = 0
    month_limit: int = 0  # refused by the 30 days' count: what it is


def month_questions(level, trial) -> int:
    """Questions in any 30 days: a trial's, else the plan level's."""
    return TRIAL_QUESTIONS_PER_MONTH if trial else config.ai_questions_per_month.get(level, 0)


def questions(chat_id, now=None, database=None) -> Questions:
    """Questions left today (the last 24 hours) for this chat, within the last 30 days' count: a running
    plan only, fewer on a trial."""
    from db import usage
    level = running_plan_level(chat_id, database)
    if level <= 0:
        return Questions(False, 0, 0)
    trial = not paid_for_days(chat_id, database)
    limit = TRIAL_QUESTIONS_PER_DAY if trial else config.ai_questions_per_day.get(level, QUESTIONS_PER_DAY)
    now = time.time() if now is None else now
    left = max(limit - usage.count_since(chat_id, 'ask', now - 86400, database), 0)
    month = month_questions(level, trial)
    if left > 0 and month:
        left = min(left, max(month - usage.count_since(chat_id, 'ask', now - QUOTA_DAYS * 86400, database), 0))
        if left <= 0:
            return Questions(False, limit, 0, trial, level=level, month_limit=month)
    if left > 0 and not trial:
        spend = budget(chat_id, now, database)
        if spend is not None and not spend.fits(config.ai_call_usd):
            return Questions(False, limit, left, trial, budget=True, level=level)
    return Questions(left > 0, limit, left, trial, level=level)
