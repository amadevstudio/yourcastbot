# -*- coding: utf-8 -*-
"""A plan given for something other than money (db/plan_grants.py).

- It starts only for a chat without a plan running, puts its plan on the row (HOLD_HOURS, the
  tariff's deliveries) and keeps the balance; held, the days go back to HOLD_HOURS and the deliveries
  are renewed each period; ended, the plan it replaced comes back with no days.
- Money never renews it: the tick's lists, its renewal and D-3 leave the holder out.
- What is bought replaces it: a plan's invoice that pays for the plan (a top-up, or money short of
  it, leaves it running); the change of the row's plan or days by any other writer; a refund takes
  none of its days; the survey's week replaces it with Relay; a referral award counts from none.
- A check that comes after something else replaced it never writes the row back.
- What it gives is its profile: no AI, whoever holds it, paid before or not; buying sees no plan.

Run from the repo root: python db/test_plan_grants.py
"""
import datetime
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.payment.test_referral_award import _temp_db  # noqa: E402
from app.service.plan import entitlements, features  # noqa: E402
from config import tariff_period  # noqa: E402
from db import plan_grants  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402

BRONZE, RELAY = 1, 3  # the fixture's tariffs: Bronze 50 cents and 30 deliveries, Relay 500 and unlimited
FREE, PAID, HOLDER, RICH = 5001, 5002, 5003, 5004
NOW = 1_800_000_000.0


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _db():
    path = _temp_db()
    db = SQLighter(path)
    db.connection.executescript("""
        CREATE TABLE IF NOT EXISTS payment_history (user_id integer NOT NULL, service_type text NOT NULL,
            invoice_id text, invoice_hash text, status text, amount integer, datetime text,
            PRIMARY KEY (user_id, service_type, invoice_id));
    """)
    db.connection.commit()
    db.close()
    return path


def _user(path, telegram_id, tariff_id=0, time_left=0, balance=0, notify=0):
    db = SQLighter(path)
    try:
        db.register_new_user(telegram_id, 'en')
        uid = db.connection.execute("SELECT id FROM users WHERE telegramId = ?", (telegram_id,)).fetchone()[0]
        db.connection.execute("DELETE FROM user_tariff_cs WHERE uid = ?", (uid,))
        db.connection.execute("INSERT INTO user_tariff_cs (uid, tariff_id, balance, notify_count, time_left) "
                              "VALUES (?, ?, ?, ?, ?)", (uid, tariff_id, balance, notify, time_left))
        db.connection.commit()
        return uid
    finally:
        db.close()


def _row(path, telegram_id):
    db = SQLighter(path)
    try:
        row = db.getUserSubscriptionByTg(telegram_id)
        return (row['tariff_id'], row['time_left'], row['notify_count'], row['balance'])
    finally:
        db.close()


def _set(path, telegram_id, **values):
    db = SQLighter(path)
    try:
        sets = ', '.join('%s = ?' % k for k in values)
        db.connection.execute("UPDATE user_tariff_cs SET %s WHERE uid = (SELECT id FROM users WHERE telegramId = ?)"
                              % sets, (*values.values(), telegram_id))
        db.connection.commit()
    finally:
        db.close()


def _pay(path, telegram_id, charge, cents, plan=None, plan_price=None):
    db = SQLighter(path)
    try:
        return db.applyPaymentReplenishmentOnce(
            db.get_user_by_tg(telegram_id), 'telegramStars', charge, datetime.datetime.now(), cents,
            tariff_period, status='paid', planId=plan, planPrice=plan_price)
    finally:
        db.close()


def _grant(path, telegram_id):
    return plan_grants.active_kind(telegram_id, path)


def test_start_hold_end(path):
    _user(path, FREE, tariff_id=RELAY, balance=30)  # a Relay that ended, 30 cents left
    _user(path, PAID, tariff_id=RELAY, time_left=100, balance=0, notify=-1)
    _assert(plan_grants.start(PAID, features.CHANNELS, 1, NOW, path) == plan_grants.BUSY,
            "another plan running: busy, nothing changes")
    _assert(_row(path, PAID) == (RELAY, 100, -1, 0) and _grant(path, PAID) is None, "its plan as it was")
    _assert(plan_grants.start(FREE, features.CHANNELS, 1, NOW, path) == plan_grants.STARTED, "no plan: started")
    _assert(_row(path, FREE) == (BRONZE, plan_grants.HOLD_HOURS, 30, 30) and _grant(path, FREE) == 'channels',
            "Bronze on the row for a week, its deliveries, the balance kept")
    _assert(plan_grants.start(FREE, features.CHANNELS, 1, NOW, path) == plan_grants.HELD, "again: held")
    _set(path, FREE, time_left=3, notify_count=2)
    uid = SQLighter(path).get_user_by_tg(FREE)['id']
    _assert(plan_grants.hold(uid, NOW + 3600, path), "held")
    _assert(_row(path, FREE)[:3] == (BRONZE, plan_grants.HOLD_HOURS, 2), "a week again, deliveries as they were")
    plan_grants.hold(uid, NOW + tariff_period * 3600 + 1, path)
    _assert(_row(path, FREE)[2] == 30, "a new period: the deliveries renewed")
    _set(path, FREE, time_left=0)
    plan_grants.hold(uid, NOW + tariff_period * 3600 + 7200, path)
    _assert(_row(path, FREE)[1] == plan_grants.HOLD_HOURS, "run out on the clock (no check): the next check holds it")
    _assert(plan_grants.end_now(uid, 'unsubscribed', database=path), "ended")
    _assert(_row(path, FREE) == (RELAY, 0, 0, 30) and _grant(path, FREE) is None,
            "the plan it replaced back, no days, the balance kept")
    _assert(not plan_grants.hold(uid, NOW, path) and not plan_grants.end_now(uid, 'again', database=path),
            "nothing to hold or end after")
    _assert(plan_grants.start(FREE, features.CHANNELS, 1, NOW, path) == plan_grants.STARTED, "and it starts again")


def test_entitlements(path):
    rights = entitlements.of(FREE, path)
    _assert(rights.grant == 'channels' and rights.profile == features.grant_key('channels') and not rights.ai
            and rights.level == 1 and rights.purchase_level == 0, "a holder: the grant's profile, no AI; buying sees no plan")
    _assert(rights.get('clicks') == features.profile(features.TRIAL)['clicks'], "clicks as a trial's")
    _assert(entitlements.of(PAID, path).purchase_level == 3, "a plan running is one to buying")


def test_tick(path):
    _user(path, RICH, balance=10_000)
    plan_grants.start(RICH, features.CHANNELS, 1, NOW, path)
    _set(path, RICH, time_left=1)
    db = SQLighter(path)
    try:
        renew = [r['telegramId'] for r in db.get_users_who_can_be_prolonged()]
        ending = [r['telegramId'] for r in db.get_users_nearing_expiry(72)]
        off = [r['telegramId'] for r in db.get_users_who_cannot_be_prolonged()]
        db.prolong_users(tariff_period)
    finally:
        db.close()
    _assert(RICH not in renew and RICH not in ending and RICH not in off, "the tick's lists, D-3 and plan-off leave it out")
    _assert(_row(path, RICH)[1] == 1 and _row(path, RICH)[3] == 10_000, "never renewed from the balance")


def test_payment(path):
    _pay(path, RICH, 'top-up', 100)
    _assert(_grant(path, RICH) == 'channels' and _row(path, RICH)[3] == 10_100, "a top-up: the grant runs on")
    holder = 5010
    _user(path, holder)
    plan_grants.start(holder, features.CHANNELS, 1, NOW, path)
    _pay(path, holder, 'short', 100, plan=RELAY, plan_price=500)
    _assert(_grant(path, holder) == 'channels' and _row(path, holder)[3] == 100,
            "a plan's invoice short of the plan: the grant runs on, the money on the balance")
    result = _pay(path, holder, 'relay', 500, plan=RELAY, plan_price=500)
    _assert(_grant(path, holder) is None and _row(path, holder) == (RELAY, tariff_period, -1, 100)
            and result['result_mode'] == 2, "a plan's invoice that pays for it: Relay on in its place")


def test_other_writers(path):
    holder = 5020
    _user(path, holder)
    plan_grants.start(holder, features.CHANNELS, 1, NOW, path)
    db = SQLighter(path)
    try:
        db.subscribeUserToTariffByTg(holder, BRONZE, 700, plan_grants.HOLD_HOURS, 30)
    finally:
        db.close()
    _assert(_grant(path, holder) == 'channels', "a write of the balance only (a top-up by the admin): it runs on")
    db = SQLighter(path)
    try:
        db.subscribeUserToTariffByTg(holder, RELAY, 700, 48, -1)
    finally:
        db.close()
    _assert(_grant(path, holder) is None and _row(path, holder)[:2] == (RELAY, 48), "a write of another plan ends it")
    late = 5021
    uid = _user(path, late)
    plan_grants.start(late, features.CHANNELS, 1, NOW, path)
    _set(path, late, tariff_id=RELAY, time_left=720)  # replaced by a writer that did not end it
    _assert(not plan_grants.hold(uid, NOW, path) and _row(path, late)[:2] == (RELAY, 720) and _grant(path, late) is None,
            "a check after another plan took the row: the row is not written back, the grant ends")


def test_refund_and_survey(path):
    from db import stars_refund
    holder = 5030
    _user(path, holder, balance=0)
    _pay(path, holder, 'paid-before', 40)  # money on the balance, no plan
    plan_grants.start(holder, features.CHANNELS, 1, NOW, path)
    stars_refund.apply_refund('paid-before', database=path)
    _assert(_row(path, holder)[:2] == (BRONZE, plan_grants.HOLD_HOURS) and _row(path, holder)[3] == 0,
            "a refund takes back its money, none of the grant's days")
    from app.jobs import why_survey
    survey = 5031
    uid = _user(path, survey)
    plan_grants.start(survey, features.CHANNELS, 1, NOW, path)
    db = SQLighter(path)
    try:
        db.connection.execute("UPDATE users SET flags = json_set(COALESCE(flags, '{}'), '$.%s', 'sent') WHERE id = ?"
                              % why_survey.SURVEY_FLAG, (uid,))
        db.connection.commit()
    finally:
        db.close()
    _assert(why_survey.grant_week(survey, path, NOW) == why_survey.REWARD_HOURS, "the survey's week given")
    _assert(_grant(path, survey) is None and _row(path, survey)[:2] == (RELAY, why_survey.REWARD_HOURS),
            "in place of the grant: Relay for the week, not hours a check would take back")


def main():
    path = _db()
    try:
        test_start_hold_end(path)
        test_entitlements(path)
        test_tick(path)
        test_payment(path)
        test_other_writers(path)
        test_refund_and_survey(path)
    finally:
        os.unlink(path)
    print("all plan grant tests passed")


if __name__ == '__main__':
    main()
