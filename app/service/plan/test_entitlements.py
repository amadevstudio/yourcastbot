# -*- coding: utf-8 -*-
"""What a plan gives comes from one profile: no plan, a trial, a plan paid for by its level.

The profiles' defaults are what config.py gave before them; a chat's profile is
read from its plan and whether it ever paid; the AI quota and the click limit
take their numbers from the profile, so changing a profile changes them.

Run from the repo root: python app/service/plan/test_entitlements.py
"""
import os
import sqlite3
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config  # noqa: E402
from app.service.plan import entitlements, features  # noqa: E402

NONE_CHAT, TRIAL_CHAT, PAID_CHAT, LAPSED_CHAT, PATRON_CHAT, ODD_CHAT = 3001, 3002, 3003, 3004, 3005, 3006


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def test_defaults():
    none, trial = features.profile(features.NONE), features.profile(features.TRIAL)
    _assert(not none['ai'] and none['clicks'] == config.free_rec_per_week and none['clicks_hours'] == 7 * 24,
            "no plan: no AI, the free week's episodes by click")
    _assert(trial['ai'] and trial['ai_hours'] == config.ai_summary_trial_hours and trial['ai_paid_hours'] == 0
            and trial['ai_questions_day'] == config.ai_trial_questions_per_day
            and trial['ai_questions_month'] == config.ai_trial_questions_per_month and not trial['ai_budget'],
            "a trial: its hours and questions, no paid model, no budget")
    _assert(trial['clicks'] == config.trial_rec_per_day and trial['clicks_hours'] == 24,
            "a trial: its episodes by click a day")
    for level, hours in config.ai_summary_hours_per_month.items():
        paid = features.profile(features.level_key(level))
        _assert(paid['ai_hours'] == hours
                and paid['ai_paid_hours'] == config.ai_paid_transcribe_hours_per_month.get(level, 0)
                and paid['ai_questions_day'] == config.ai_questions_per_day.get(level, 0)
                and paid['ai_questions_month'] == config.ai_questions_per_month.get(level, 0)
                and paid['ai_budget'] and paid['clicks'] is None,
                "level %d paid: config's hours, paid hours, questions; a budget; no click limit" % level)
    odd = features.profile(features.level_key(99))
    _assert(not odd['ai'] and odd['clicks'] is None, "a paid level without values: no AI, no click limit")
    _assert(features.top_level() == max(config.ai_summary_hours_per_month), "the top level")
    _assert(features.most('ai_questions_day') == max(config.ai_questions_per_day.values()), "'up to'")
    _assert(set(features.profile(features.NONE)) == set(features.FEATURES), "every profile has every feature")


def test_for_plan():
    _assert(entitlements.for_plan(0, True).profile == features.NONE, "no plan, paid before: none")
    _assert(entitlements.for_plan(3, False).profile == features.TRIAL, "a plan nobody paid for: the trial")
    _assert(entitlements.for_plan(1, False).trial, "whatever its level")
    paid = entitlements.for_plan(2, True, 200)
    _assert(paid.profile == features.level_key(2) and paid.running and not paid.trial and paid.price == 200,
            "a plan paid for: its level's profile")


def _database(path):
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER);
        CREATE TABLE tariffs (id INTEGER PRIMARY KEY, level INTEGER, price INTEGER);
        CREATE TABLE user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER, tariff_id INTEGER,
            balance INTEGER, time_left INTEGER, notify_count INTEGER);
        CREATE TABLE payment_history (user_id INTEGER, status TEXT);
        CREATE TABLE payment_service_user_data (user_id INTEGER, last_replenishment TEXT);
        INSERT INTO tariffs VALUES (1, 1, 100), (2, 2, 200), (3, 3, 500), (9, 99, 900);
        INSERT INTO users VALUES (1, 3001), (2, 3002), (3, 3003), (4, 3004), (5, 3005), (6, 3006);
        INSERT INTO user_tariff_cs VALUES (1, 1, 0, 0, 0, 0), (2, 2, 3, 0, 300, 10), (3, 3, 2, 0, 300, 10),
            (4, 4, 1, 0, 0, 0), (5, 5, 1, 0, 300, 10), (6, 6, 9, 0, 300, 10);
        INSERT INTO payment_history VALUES (3, 'paid'), (4, 'paid'), (6, 'paid'), (2, 'refunded');
        INSERT INTO payment_service_user_data VALUES (5, '2026-10-01');
    """)
    c.commit()
    c.close()


def test_of(db):
    _database(db)
    _assert(entitlements.of(NONE_CHAT, db).profile == features.NONE, "no plan running: none")
    _assert(entitlements.of(TRIAL_CHAT, db).profile == features.TRIAL, "Relay nobody paid for (a refund is no payment)")
    paid = entitlements.of(PAID_CHAT, db)
    _assert(paid.profile == features.level_key(2) and paid.price == 200, "Silver paid for, its price")
    lapsed = entitlements.of(LAPSED_CHAT, db)
    _assert(lapsed.profile == features.NONE and lapsed.paid and not lapsed.running,
            "a plan that ended: none, and it paid before")
    _assert(entitlements.of(PATRON_CHAT, db).profile == features.level_key(1), "a Patreon credit is paying")
    _assert(entitlements.of(777, db).profile == features.NONE, "no such chat: none")


def test_readers_follow_the_profile(db):
    """The constructor's promise: a profile's numbers are what the quota and the limit apply."""
    from app.service.ai import quota
    from app.service.record import free_limit
    saved = features.profiles
    edited = features.defaults()
    edited[features.TRIAL] = dict(edited[features.TRIAL], ai_hours=1, ai_questions_day=2, clicks=1)
    edited[features.level_key(2)] = dict(edited[features.level_key(2)], ai=False)
    features.profiles = lambda: edited
    try:
        _assert(quota.check(TRIAL_CHAT, 60, database=db).limit == 3600, "a trial's hours from its profile")
        _assert(quota.questions(TRIAL_CHAT, database=db).limit == 2, "a trial's questions from its profile")
        _assert(not quota.check(PAID_CHAT, 60, database=db).allowed and quota.questions(PAID_CHAT, database=db).limit == 0,
                "a profile without AI: no summaries, no questions")
        now = time.time()
        from db import usage
        usage.record_deliveries([TRIAL_CHAT], 'rec', 'https://cdn/one.mp3', database=db, at=now - 60)
        hit = free_limit.limit_hit(TRIAL_CHAT, 'https://cdn/two.mp3', (), now=now, database=db)
        _assert(hit is not None and hit.limit == 'trial' and hit.count == 1, "a trial's clicks from its profile")
        _assert(free_limit.limit_hit(PAID_CHAT, 'https://cdn/two.mp3', (), now=now, database=db) is None,
                "a paid profile without a click limit")
    finally:
        features.profiles = saved
    _assert(quota.check(ODD_CHAT, 60, database=db).limit == 0, "a paid level without values: no AI hours")


def main():
    test_defaults()
    test_for_plan()
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, 'plan.sqlite')
        test_of(db)
        test_readers_follow_the_profile(db)
    print("all entitlements tests passed")


if __name__ == '__main__':
    main()
