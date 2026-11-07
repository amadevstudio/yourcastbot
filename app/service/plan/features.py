# -*- coding: utf-8 -*-
"""What a plan gives, as data: a profile of features per kind of plan.

Profiles: NONE (no plan running), TRIAL (a plan nobody paid for: the welcome
plan, referral days, whatever its level), level_key(n) (a plan paid for, by
its level in `tariffs`). entitlements.py picks the chat's profile; the AI
quota and the click limits read their numbers from it, never from config or a
plan's level. Delivery (notify_count, channel_control) stays in `tariffs`.

The values are config.py's, what the bot gave before profiles; the admin's
edits are to override them. A level without config values gives no AI and
no click limit, as a paid plan without hours always did.
Lock: python app/service/plan/test_entitlements.py
"""
import config

NONE = 'none'
TRIAL = 'trial'
# every feature of a profile: what it means
FEATURES = {
    'ai': 'AI at all: summaries, transcripts, questions, voice messages',
    'ai_hours': 'hours of new audio for summaries and transcripts in any 30 days',
    'ai_paid_hours': 'of them, hours the paid speech model may make',
    'ai_questions_day': 'questions in any 24 hours',
    'ai_questions_month': 'questions in any 30 days',
    'ai_budget': "AI stops at a share of what the plan's price brings (quota.budget)",
    'clicks': 'episodes by click in the window; None: no limit',
    'clicks_hours': 'the window of `clicks`, hours',
}
WEEK_HOURS = 7 * 24
DAY_HOURS = 24


def level_key(level) -> str:
    return 'level:%d' % int(level)


def _paid_level(level) -> dict:
    hours = config.ai_summary_hours_per_month.get(level, 0)
    return {'ai': hours > 0, 'ai_hours': hours,
            'ai_paid_hours': config.ai_paid_transcribe_hours_per_month.get(level, 0),
            'ai_questions_day': config.ai_questions_per_day.get(level, 0),
            'ai_questions_month': config.ai_questions_per_month.get(level, 0),
            'ai_budget': True, 'clicks': None, 'clicks_hours': DAY_HOURS}


def defaults() -> dict:
    """{profile name: features} as config.py has them."""
    profiles = {
        NONE: {'ai': False, 'ai_hours': 0, 'ai_paid_hours': 0, 'ai_questions_day': 0, 'ai_questions_month': 0,
               'ai_budget': False, 'clicks': config.free_rec_per_week, 'clicks_hours': WEEK_HOURS},
        TRIAL: {'ai': True, 'ai_hours': config.ai_summary_trial_hours, 'ai_paid_hours': 0,
                'ai_questions_day': config.ai_trial_questions_per_day,
                'ai_questions_month': config.ai_trial_questions_per_month,
                'ai_budget': False, 'clicks': config.trial_rec_per_day, 'clicks_hours': DAY_HOURS},
    }
    for level in config.ai_summary_hours_per_month:
        profiles[level_key(level)] = _paid_level(level)
    return profiles


def profiles() -> dict:
    return defaults()


def profile(name) -> dict:
    """The features of a profile; a level with none of its own: a paid plan without AI."""
    known = profiles()
    if name in known:
        return dict(known[name])
    if str(name).startswith('level:'):
        return _paid_level(None)
    return dict(known[NONE])


def paid_levels() -> list:
    """Plan levels that have a profile, lowest first."""
    return sorted(int(name.split(':', 1)[1]) for name in profiles() if name.startswith('level:'))


def top_level() -> int:
    """The highest paid level: nothing bigger to sell."""
    return max(paid_levels(), default=0)


def most(feature) -> int:
    """The most any paid level gives of `feature` ("up to" in the copy)."""
    return max((profile(level_key(level))[feature] or 0 for level in paid_levels()), default=0)
