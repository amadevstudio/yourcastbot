# -*- coding: utf-8 -*-
"""What a plan gives, as data: a profile of features per kind of plan.

Profiles: NONE (no plan running), TRIAL (a plan nobody paid for: the welcome
plan, referral days, whatever its level), level_key(n) (a plan paid for, by
its level in `tariffs`), grant_key(kind) (a plan given for something else,
db/plan_grants.py, whoever holds it). entitlements.py picks the chat's profile; the AI
quota and the click limits read their numbers from it, never from config or a
plan's level. Delivery (notify_count, channel_control) stays in `tariffs`.

The defaults are config.py's, what the bot gave before profiles. The admin
edits them (page "Tariffs": bot_runtime_kv OVERRIDES_KEY, {profile: {feature:
value}}, only what differs); every process reads the edits within
CACHE_SECONDS. A level without values gives no AI and no click limit, as a paid
plan without hours always did.
Lock: python app/service/plan/test_entitlements.py
"""
import json
import threading
import time

import config
from db import runtime_kv
from lib.tools.logger import logger

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
OVERRIDES_KEY = 'plan_profiles'
CACHE_SECONDS = 60
BOOLEAN = ('ai', 'ai_budget')
WHOLE = ('ai_questions_day', 'ai_questions_month', 'clicks', 'clicks_hours')
NULLABLE = ('clicks',)  # None: no limit
# grants (db/plan_grants.py): the plan level each kind gives
CHANNELS = 'channels'  # Bronze while subscribed to the owner's channels (app/service/plan/channels.py)
GRANT_LEVELS = {CHANNELS: 1}


def level_key(level) -> str:
    return 'level:%d' % int(level)


def grant_key(kind) -> str:
    return 'grant:%s' % kind


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
        # Bronze's delivery for free, without AI; clicks as a trial's: nobody pays for the rec workers
        grant_key(CHANNELS): {'ai': False, 'ai_hours': 0, 'ai_paid_hours': 0, 'ai_questions_day': 0,
                              'ai_questions_month': 0, 'ai_budget': False, 'clicks': config.trial_rec_per_day,
                              'clicks_hours': DAY_HOURS},
    }
    for level in config.ai_summary_hours_per_month:
        profiles[level_key(level)] = _paid_level(level)
    return profiles


_cache = {'at': 0.0, 'value': {}}
_cache_lock = threading.Lock()


def overrides(database=None, fresh=False) -> dict:
    """The admin's edits, {profile: {feature: value}}; {} when there are none or they cannot be read."""
    with _cache_lock:
        if database is None and not fresh and time.time() - _cache['at'] < CACHE_SECONDS:
            return _cache['value']
        try:
            value = json.loads(runtime_kv.get_kv(OVERRIDES_KEY, database=database) or '{}')
            value = value if isinstance(value, dict) else {}
        except Exception as e:  # never a reason for a plan to give nothing
            logger.warn("plan profiles:", type(e).__name__, e)
            value = {}
        if database is None:
            _cache.update(at=time.time(), value=value)
        return value


def merged(edits) -> dict:
    """defaults() with `edits` over them: known profiles and features only."""
    result = defaults()
    for name, edited in (edits or {}).items():
        if name in result and isinstance(edited, dict):
            result[name].update({key: value for key, value in edited.items() if key in FEATURES})
    return result


def profiles() -> dict:
    return merged(overrides())


def clean(edited) -> dict:
    """A profile's features as the admin sent them, checked; ValueError says what is wrong."""
    result = {}
    for key, value in edited.items():
        if key not in FEATURES:
            raise ValueError('unknown feature: %s' % key)
        if key in BOOLEAN:
            if not isinstance(value, bool):
                raise ValueError('%s: true or false' % key)
        elif value is None and key in NULLABLE:
            pass
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0 \
                or (key in WHOLE and value != int(value)):
            raise ValueError('%s: a number of 0 or more%s' % (key, ', whole' if key in WHOLE else ''))
        elif key == 'clicks_hours' and value < 1:
            raise ValueError('clicks_hours: 1 or more')
        result[key] = int(value) if key in WHOLE and value is not None else value
    return result


def save(name, edited, database=None) -> dict:
    """The admin's features of profile `name` (what equals the default is not kept; {} resets it)."""
    base = defaults()
    if name not in base:
        raise ValueError('unknown profile: %s' % name)
    edited = {key: value for key, value in clean(edited).items() if base[name][key] != value}
    edits = dict(overrides(database, fresh=True))
    if edited:
        edits[name] = edited
    else:
        edits.pop(name, None)
    runtime_kv.set_kv(OVERRIDES_KEY, json.dumps(edits), database=database)
    if database is None:
        with _cache_lock:
            _cache.update(at=time.time(), value=edits)
    return edits


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
