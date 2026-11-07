# -*- coding: utf-8 -*-
"""Who may ask for a new AI summary: hours of audio per 30 days by plan.

A new summary takes the episode's length from the asker's plan quota
(`ai_hours` of the chat's profile: app/service/plan/entitlements.py). What a summary costs
grows with the audio (transcription bills by the second), so a count of
summaries would let long episodes cost more than the plan brings. The
charges themselves are ai_requests.seconds (db/ai.py). Without a plan
only summaries someone already made, which are free.

A plan nobody paid for yet (the welcome Relay, referral days) has the
trial profile's hours whatever its level: every new user gets
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
from app.service.plan import entitlements, features
from db import ai

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
    grant: str | None = None  # a grant holds the plan (db/plan_grants.py): its profile, no AI today

    @property
    def left(self) -> int:
        return max(self.limit - self.used, 0)

    @property
    def top_plan(self) -> bool:
        """Nothing bigger to sell: the top plan, paid for."""
        return not self.trial and self.level >= features.top_level()


class Budget(NamedTuple):
    """USD: the most this plan's AI may cost in 30 days, and what it cost in the last 30 days."""
    limit: float
    spent: float

    def fits(self, cost: float) -> bool:
        return self.spent + cost <= self.limit


def budget(chat_id, now=None, database=None) -> Budget | None:
    """The budget of a plan whose profile has one (paid for); None for a trial (its own few hours and
    questions), no plan, or a plan without a price."""
    rights = entitlements.of(chat_id, database)
    if not rights.get('ai_budget') or rights.price <= 0:
        return None
    from db import usage
    share = config.payout_share.get('telegramStars', 1.0) * config.ai_budget_share
    since = (time.time() if now is None else now) - QUOTA_DAYS * 86400
    return Budget(rights.price / 100.0 * share, usage.ai_spent_since(chat_id, since, database))


def transcribe_cost(seconds, paid_model=False) -> float:
    """What a new transcript of `seconds` and a model call on it are reckoned to cost."""
    rate = config.ai_paid_transcribe_usd_hour if paid_model else config.ai_transcribe_usd_hour
    return (seconds or UNKNOWN_SECONDS) / 3600.0 * rate + config.ai_call_usd


def paid_transcribe_fits(chat_id, seconds, now=None, database=None) -> bool:
    """Does making this episode's transcript with the paid model fit the plan's hours of it
    (`ai_paid_hours`: a plan paid for only) and the plan's budget?"""
    rights = entitlements.of(chat_id, database)
    limit = (rights.get('ai_paid_hours') or 0) * 3600 if rights.ai else 0
    if limit <= 0:
        return False
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
    The chat's plan is read unless `level` (and `trial`: nobody paid for it) is given."""
    rights = (entitlements.of(chat_id, database) if level is None
              else entitlements.for_plan(level, paid=not trial))
    limit = int((rights.get('ai_hours') or 0) * 3600) if rights.ai else 0
    since = (time.time() if now is None else now) - QUOTA_DAYS * 86400
    used = ai.seconds_used(chat_id, since, database)
    allowed = limit > 0 and used + needed <= limit
    if allowed and rights.get('ai_budget'):
        left = budget(chat_id, now, database)
        cost = transcribe_cost(needed) if needed else config.ai_call_usd
        if left is not None and not left.fits(cost):
            return Quota(False, limit, used, int(needed), rights.level, rights.trial, budget=True)
    return Quota(allowed, limit, used, int(needed), rights.level, rights.trial, grant=rights.grant)


# Questions about an episode (summaryModule.ask): one model call each, a few
# tenths of a cent with the transcript cached, so a count per 24 hours (`ai_questions_day`),
# one per 30 days (`ai_questions_month`) and the budget are enough.


def most_questions_per_day() -> int:
    """The most a paid plan gives a day ("up to" in the copy)."""
    return features.most('ai_questions_day')


class Questions(NamedTuple):
    allowed: bool
    limit: int  # 0: no plan
    left: int
    trial: bool = False
    budget: bool = False  # refused by the plan's budget, not by the day's count
    level: int = 0
    month_limit: int = 0  # refused by the 30 days' count: what it is
    grant: str | None = None  # a grant holds the plan (db/plan_grants.py)


def questions(chat_id, now=None, database=None) -> Questions:
    """Questions left today (the last 24 hours) for this chat, within the last 30 days' count: a plan
    with AI only, fewer on a trial."""
    from db import usage
    rights = entitlements.of(chat_id, database)
    if not rights.ai:
        return Questions(False, 0, 0, grant=rights.grant)
    limit = int(rights.get('ai_questions_day') or 0)
    now = time.time() if now is None else now
    left = max(limit - usage.count_since(chat_id, 'ask', now - 86400, database), 0)
    month = int(rights.get('ai_questions_month') or 0)
    if left > 0 and month:
        left = min(left, max(month - usage.count_since(chat_id, 'ask', now - QUOTA_DAYS * 86400, database), 0))
        if left <= 0:
            return Questions(False, limit, 0, rights.trial, level=rights.level, month_limit=month)
    if left > 0 and rights.get('ai_budget'):
        spend = budget(chat_id, now, database)
        if spend is not None and not spend.fits(config.ai_call_usd):
            return Questions(False, limit, left, rights.trial, budget=True, level=rights.level)
    return Questions(left > 0, limit, left, rights.trial, level=rights.level)
