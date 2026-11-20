# -*- coding: utf-8 -*-
"""Packs of episodes by click (db/click_packs.py): credited once per charge, a payment that opens no
plan's rights, an episode taken per click past the limit and given back when its click fails, the
last one never taken twice, the free week never eats a pack, a refund takes the pack and nothing else.

Run from the repo root: python db/test_click_packs.py
"""
import concurrent.futures
import os
import sqlite3
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.record import free_limit  # noqa: E402
from db import click_packs, stars_refund, tariff_rows, usage  # noqa: E402

BUYER, OTHER = 7101, 7102


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _schema(db):
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER UNIQUE, lang TEXT);
        CREATE TABLE tariffs (id INTEGER PRIMARY KEY, level INTEGER, price INTEGER, notify_count INTEGER);
        CREATE TABLE user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER, tariff_id INTEGER,
                                     balance INTEGER, notify_count INTEGER, time_left INTEGER);
        CREATE TABLE payment_history (user_id INTEGER NOT NULL, service_type TEXT NOT NULL, invoice_id TEXT,
                                      invoice_hash TEXT, status TEXT, amount INTEGER, datetime TEXT,
                                      PRIMARY KEY (user_id, service_type, invoice_id));
        INSERT INTO tariffs VALUES (1, 1, 100, 60), (3, 3, 500, -1);
        INSERT INTO users VALUES (1, %d, 'en'), (2, %d, 'en');
        INSERT INTO user_tariff_cs VALUES (1, 1, 0, 300, 0, 0), (2, 2, 0, 0, 0, 0);
    """ % (BUYER, OTHER))
    c.commit()
    c.close()


def _deliver(db, chat, links, at):
    for link in links:
        usage.record_deliveries([chat], 'rec', link, database=db, at=at)


def _credit_once(db):
    _assert(click_packs.credit(BUYER, 'ch-1', 30, 65, 'p:1300:', database=db), "a pack is credited")
    _assert(not click_packs.credit(BUYER, 'ch-1', 30, 65, 'p:1300:', database=db),
            "the same charge again credits nothing (a retried update)")
    _assert(not click_packs.credit(999999, 'ch-x', 30, 65, database=db), "no such user: nothing written")
    c = sqlite3.connect(db)
    rows = c.execute("SELECT service_type, status, amount, charged FROM payment_history").fetchall()
    c.close()
    _assert(rows == [(click_packs.SERVICE_TYPE, 'paid', 65, 65)],
            "one payment row: a pack's service type, paid, amount and charged its price (revenue sees it)")
    _assert(click_packs.left(BUYER, database=db) == 30, "30 episodes left")
    _assert(click_packs.episodes_of('ch-1', database=db) == 30 and click_packs.episodes_of('nope', database=db) == 0,
            "the pack of a charge is known, a charge that is no pack has none")


def _no_plan_rights(db):
    _assert(not tariff_rows.ever_paid(BUYER, db) and not tariff_rows.paid_for_days(BUYER, db),
            "a pack is not a payment for a plan: no paid plan's AI, models, refund of days or offer change")
    c = sqlite3.connect(db)
    c.execute("INSERT INTO payment_history (user_id, service_type, invoice_id, invoice_hash, status, amount, datetime) "
              "VALUES (2, 'telegramStars', 'ch-plan', '', 'paid', 500, '2026-11-20')")
    c.commit()
    c.close()
    _assert(tariff_rows.ever_paid(OTHER, db), "a plan's payment still is one")


def _uses(db):
    now = time.time()
    a, b = 'https://cdn/a.mp3', 'https://cdn/b.mp3'
    _assert(click_packs.use(BUYER, a, now=now, database=db), "a click past the limit takes an episode")
    _assert(click_packs.left(BUYER, now=now, database=db) == 29, "29 left while it is on its way")
    _assert(click_packs.use(BUYER, a, now=now + 1, database=db) and click_packs.left(BUYER, now=now + 1, database=db) == 29,
            "the same episode again is free")
    later = now + click_packs.USE_GRACE_SECONDS + 60
    _assert(click_packs.left(BUYER, open_links={a}, now=later, database=db) == 29, "still waiting in the outbox: counted")
    _assert(click_packs.left(BUYER, now=later, database=db) == 30,
            "neither waiting nor delivered (the download failed): the episode comes back by itself")
    _deliver(db, BUYER, [a], now + 5)
    _assert(click_packs.left(BUYER, now=later, database=db) == 29, "delivered: counted for good")
    _assert(click_packs.use(BUYER, b, now=later, database=db), "another episode")
    _assert(click_packs.counting_refs(BUYER, now=later, database=db) == {usage.episode_ref(a), usage.episode_ref(b)},
            "the episodes a pack pays for are known to the free window")
    _assert(not click_packs.use(OTHER, a, now=later, database=db), "a chat with no pack takes nothing")


def _last_episode_once(db):
    c = sqlite3.connect(db)
    c.execute("INSERT INTO users VALUES (3, 7103, 'en')")
    c.commit()
    c.close()
    click_packs.credit(7103, 'ch-small', 1, 65, database=db)
    now = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        taken = list(pool.map(lambda link: click_packs.use(7103, link, now=now, database=db),
                              ['https://cdn/x.mp3', 'https://cdn/y.mp3']))
    _assert(sorted(taken) == [False, True], "two taps at once never take the last episode twice")


def _limit_hit(db):
    """A chat with no plan at its week: a pack pays for the click, the quiet newest episode leaves it."""
    now = time.time()
    c = sqlite3.connect(db)
    c.execute("INSERT INTO users VALUES (4, 7104, 'en')")
    c.execute("INSERT INTO user_tariff_cs VALUES (4, 4, 0, 0, 0, 0)")
    c.commit()
    c.close()
    week = ['https://cdn/w%d.mp3' % i for i in range(10)]
    _deliver(db, 7104, week, now - 3600)
    hit = free_limit.limit_hit(7104, 'https://cdn/new1.mp3', (), now=now, database=db)
    _assert(hit is not None and hit.limit == 'week', "no pack: the 11th episode is stopped")
    click_packs.credit(7104, 'ch-4', 2, 65, database=db)
    _assert(free_limit.limit_hit(7104, 'https://cdn/new1.mp3', (), now=now, database=db, use_pack=False) is not None,
            "the quiet newest episode after a subscription does not spend a pack")
    _assert(free_limit.limit_hit(7104, 'https://cdn/new1.mp3', (), now=now, database=db) is None,
            "a pack pays for the click past the week")
    _deliver(db, 7104, ['https://cdn/new1.mp3'], now + 1)
    _assert(free_limit.limit_hit(7104, 'https://cdn/new2.mp3', (), now=now + 2, database=db) is None
            and click_packs.left(7104, now=now + 2, database=db) == 0, "the second episode, the pack is empty")
    _assert(free_limit.limit_hit(7104, 'https://cdn/new3.mp3', (), now=now + 3, database=db) is not None,
            "an empty pack: stopped again")
    # a week later the free episodes are back and the pack's are not counted among them
    _deliver(db, 7104, ['https://cdn/new2.mp3'], now + 4)
    later = now + 7 * 86400
    fresh = ['https://cdn/f%d.mp3' % i for i in range(9)]
    _deliver(db, 7104, fresh, later - 60)
    _assert(free_limit.limit_hit(7104, 'https://cdn/f9.mp3', (), now=later, database=db, use_pack=False) is None,
            "the pack's episodes are not the week's: the 10th free one goes")
    _assert(free_limit.limit_hit(7104, 'https://cdn/new1.mp3', (), now=later, database=db, use_pack=False) is None,
            "an episode the pack paid for goes again without taking a free one")


def _failed_then_free(db):
    """A pack's click that failed, the same episode fetched free a week later: the week's, not the pack's."""
    now = time.time()
    c = sqlite3.connect(db)
    c.execute("INSERT INTO users VALUES (5, 7105, 'en')")
    c.execute("INSERT INTO user_tariff_cs VALUES (5, 5, 0, 0, 0, 0)")
    c.commit()
    c.close()
    click_packs.credit(7105, 'ch-5', 3, 65, database=db)
    lost = 'https://cdn/lost.mp3'
    _assert(click_packs.use(7105, lost, now=now, database=db), "a pack's click is queued")
    later = now + 7 * 86400
    _assert(click_packs.left(7105, now=later, database=db) == 3, "its download failed: the episode is back")
    _assert(free_limit.limit_hit(7105, lost, (), now=later, database=db) is None, "a week later it goes free")
    _deliver(db, 7105, [lost], later + 5)
    _assert(click_packs.left(7105, now=later + 10, database=db) == 3, "the pack is not charged for it")
    week = ['https://cdn/v%d.mp3' % i for i in range(9)]
    _deliver(db, 7105, week, later + 20)
    hit = free_limit.limit_hit(7105, 'https://cdn/v9.mp3', (), now=later + 30, database=db, use_pack=False)
    _assert(hit is not None, "and it took one of the week's ten: 9 more and the week is used")


def _refund(db):
    _assert('ch-1' in stars_refund.paid_charge_ids(db), "the daily refund check knows a pack's charge")
    c = sqlite3.connect(db)
    before = c.execute("SELECT balance, time_left FROM user_tariff_cs WHERE uid = 1").fetchone()
    c.close()
    refund = stars_refund.apply_refund('ch-1', db)
    _assert(refund is not None and refund['pack'] == 30 and refund['amount'] == 0 and refund['charged'] == 65,
            "a pack's refund names the pack and takes no balance")
    c = sqlite3.connect(db)
    after = c.execute("SELECT balance, time_left FROM user_tariff_cs WHERE uid = 1").fetchone()
    status = c.execute("SELECT status FROM payment_history WHERE invoice_id = 'ch-1'").fetchone()[0]
    c.close()
    _assert(after == before and status == 'refunded', "the balance and the plan stay; the payment is refunded")
    _assert(click_packs.left(BUYER, database=db) == 0, "the pack's episodes go with it")
    _assert(stars_refund.apply_refund('ch-1', db) is None, "taken back once")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, 'packs.sqlite')
        _schema(db)
        _credit_once(db)
        _no_plan_rights(db)
        _uses(db)
        _last_episode_once(db)
        _limit_hit(db)
        _failed_then_free(db)
        _refund(db)
    print("all click pack checks passed")


if __name__ == "__main__":
    main()
