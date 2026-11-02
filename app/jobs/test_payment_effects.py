# -*- coding: utf-8 -*-
"""What a payment sets off (db/payment_effects.py, app/jobs/payment_effects.py) and the better AI
models it turns on (app/service/ai/paid_models.py).

- The effect rows are written with the payment, once: Stars/CryptoBot/Robokassa
  (applyPaymentReplenishmentOnce) and Patreon (credit_month); a retried webhook,
  a pledge of nothing or a payment not 'paid' sets nothing off.
- An effect runs after the payment, is retried, and fails loudly after
  MAX_ATTEMPTS; a lease that ran out is claimed again; the payment is never touched.
- The models: on by a payment unless the user turned them off; the notice once,
  only with a plan running; who gets which model and which line, for every case
  (no plan, trial, paid and on, paid and off, paid before and lapsed).

Run from the repo root: python app/jobs/test_payment_effects.py
"""
import datetime
import os
import sys
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.i18n.messages import get_message  # noqa: E402
from app.jobs import payment_effects as job  # noqa: E402
from app.service.ai import paid_models  # noqa: E402
from app.service.payment.test_referral_award import _temp_db  # noqa: E402
from db import payment_effects, patreon  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402

GROK, SONNET, HAIKU, WHISPER = 'x-ai/grok-stt-1.0', 'paid/strong', 'base/model', 'base/whisper'


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _db():
    path = _temp_db()
    db = SQLighter(path)
    db.connection.execute(
        "CREATE TABLE IF NOT EXISTS payment_history (user_id integer NOT NULL, service_type text NOT NULL, "
        "invoice_id text, invoice_hash text, status text, amount integer, datetime text, "
        "PRIMARY KEY (user_id, service_type, invoice_id))")
    db.connection.execute(
        "CREATE TABLE payment_service_user_data (user_id integer NOT NULL, service_type text NOT NULL, "
        "email text NOT NULL, last_replenishment text, active integer NOT NULL, "
        "PRIMARY KEY (user_id, service_type))")
    db.connection.commit()
    db.close()
    return path


def _user(path, telegram_id, tariff_id=3, time_left=100, flags=None):
    db = SQLighter(path)
    try:
        db.register_new_user(telegram_id, 'en')
        db.connection.execute("DELETE FROM user_tariff_cs WHERE uid = (SELECT id FROM users WHERE telegramId = ?)",
                              (telegram_id,))
        uid = db.connection.execute("SELECT id FROM users WHERE telegramId = ?", (telegram_id,)).fetchone()[0]
        db.connection.execute("INSERT INTO user_tariff_cs (uid, tariff_id, balance, notify_count, time_left) "
                              "VALUES (?, ?, 0, -1, ?)", (uid, tariff_id, time_left))
        if flags is not None:
            db.connection.execute("UPDATE users SET flags = ? WHERE id = ?", (flags, uid))
        db.connection.commit()
        return uid
    finally:
        db.close()


def _pay(path, telegram_id, invoice, status='paid'):
    db = SQLighter(path)
    try:
        return db.applyPaymentReplenishmentOnce(db.get_user_by_tg(telegram_id), 'stars', invoice,
                                                datetime.datetime.now(), 500, 720, status=status)
    finally:
        db.close()


def _rows(path):
    db = SQLighter(path)
    try:
        return [tuple(row) for row in db.connection.execute(
            "SELECT payment, user_id, effect, status, attempts FROM payment_effects ORDER BY id")]
    finally:
        db.close()


def _flag(path, telegram_id):
    db = SQLighter(path)
    try:
        return db.get_user_flag(telegram_id, paid_models.FLAG)
    finally:
        db.close()


def test_rows_with_the_payment():
    path = _db()
    try:
        uid = _user(path, 7001)
        first = _pay(path, 7001, 'charge-1')
        again = _pay(path, 7001, 'charge-1')
        rows = _rows(path)
        _assert(not first['already_processed'] and again['already_processed'], "the second webhook credits nothing")
        _assert(len(rows) == 1 and rows[0][1:4] == (uid, payment_effects.PAID_MODELS, 'pending')
                and rows[0][0].startswith('ph:'), "one effect row per payment, written with it")
        _pay(path, 7001, 'charge-2', status='refunded')
        _assert(len(_rows(path)) == 1, "a payment that is not 'paid' sets nothing off")
        _pay(path, 7001, 'charge-3')
        _assert(len(_rows(path)) == 2, "the next payment sets it off again (the handler is idempotent)")

        uid2 = _user(path, 7002)
        _assert(patreon.credit_month(uid2, '2026-11', 500, 500, '2026-11-02', database=path), "a Patreon month")
        _assert(not patreon.credit_month(uid2, '2026-11', 500, 500, '2026-11-02', database=path), "once")
        patreon.credit_month(uid2, '2026-12', 0, 0, '2026-12-02', database=path)
        patreon_rows = [row for row in _rows(path) if row[1] == uid2]
        _assert(len(patreon_rows) == 1, "Patreon sets it off once a month; a pledge of nothing does not")
    finally:
        os.remove(path)


def test_runner():
    path = _db()
    try:
        _user(path, 7101)
        _pay(path, 7101, 'charge-1')
        calls, alerts = [], []
        t0 = 1_800_000_000.0

        def broken(user_id, database=None):
            calls.append(user_id)
            raise RuntimeError('down')

        _assert(job.run_due({payment_effects.PAID_MODELS: broken}, path, now=t0, notify=alerts.append) == 1,
                "a due effect runs")
        row = _rows(path)[0]
        _assert(row[3] == 'pending' and row[4] == 1, "a failure is tried again later")
        _assert(job.run_due({payment_effects.PAID_MODELS: broken}, path, now=t0 + 1) == 0,
                "not before its retry time")
        now = t0
        for attempt in range(2, payment_effects.MAX_ATTEMPTS + 1):
            now += payment_effects.RETRY_SECONDS * attempt + 1
            job.run_due({payment_effects.PAID_MODELS: broken}, path, now=now, notify=alerts.append)
        _assert(_rows(path)[0][3] == 'failed' and len(calls) == payment_effects.MAX_ATTEMPTS and len(alerts) == 1
                and 'failed %d times' % payment_effects.MAX_ATTEMPTS in alerts[0],
                "after MAX_ATTEMPTS it fails and the creator hears of it once")
        db = SQLighter(path)
        try:
            _assert(db.connection.execute("SELECT COUNT(*) FROM payment_history").fetchone()[0] == 1,
                    "the payment stays as it was")
        finally:
            db.close()

        _pay(path, 7101, 'charge-2')
        leased = payment_effects.claim(path, now=t0)
        _assert(leased is not None and payment_effects.claim(path, now=t0 + 1) is None,
                "a leased effect is not claimed twice")
        again = payment_effects.claim(path, now=t0 + payment_effects.LEASE_SECONDS + 1)
        _assert(again is not None and again['id'] == leased['id'] and again['attempts'] == 2,
                "a lease that ran out (its worker died) is claimed again")
        _assert(payment_effects.finish(again, None, path, now=t0) == 'done', "done")
    finally:
        os.remove(path)


def test_paid_models_effect():
    path = _db()
    sent = []
    send = lambda chat_id, messages: sent.append((chat_id, messages[0]['text'])) or [{'id': 1}]  # noqa: E731
    try:
        with patch.object(paid_models, 'ai_paid_transcribe_model', GROK), \
                patch.object(paid_models, 'ai_paid_summary_model', SONNET):
            on = _user(path, 7201)
            _pay(path, 7201, 'c1')
            job.turn_on_paid_models(on, path, send=send)
            _assert(_flag(path, 7201) == 1 and len(sent) == 1 and sent[0][0] == 7201
                    and sent[0][1] == get_message('paidModelsOnNotice', 'en').format(
                        what=get_message('paidModelsWhatBoth', 'en')),
                    "a payment turns them on and says so once, with what they give")
            job.turn_on_paid_models(on, path, send=send)
            _assert(len(sent) == 1, "a renewal says nothing")

            chose = _user(path, 7202, flags='{"paid_models": 0}')
            _pay(path, 7202, 'c2')
            job.turn_on_paid_models(chose, path, send=send)
            _assert(_flag(path, 7202) == 0 and len(sent) == 1, "a user who turned them off keeps it off, in silence")

            topup = _user(path, 7203, tariff_id=0, time_left=0)
            _pay(path, 7203, 'c3')
            job.turn_on_paid_models(topup, path, send=send)
            _assert(_flag(path, 7203) == 1 and len(sent) == 1,
                    "a top-up with no plan running: on for when the plan runs, nothing announced")

            job.turn_on_paid_models(_user(path, 7204), path, send=lambda *a: [])
            _assert(_flag(path, 7204) == 1, "a notice Telegram did not take leaves them on")

            before = _user(path, 7205)
            db = SQLighter(path)
            try:  # paid before the effect existed: a payment row and no effect row
                db.connection.execute("INSERT INTO payment_history VALUES (?, 'stars', 'old', NULL, 'paid', 100, '')",
                                      (before,))
                db.connection.commit()
            finally:
                db.close()
            _user(path, 7206)  # a trial: no payment
            added = job.backfill(path)
            _assert(job.backfill(path) == 0 and added >= 1
                    and any(row[0] == 'backfill:%d' % before for row in _rows(path))
                    and not any(row[0] == 'backfill:%d' % 7206 for row in _rows(path)),
                    "chats that paid before get the effect once at start; a trial does not")
        with patch.object(paid_models, 'ai_paid_transcribe_model', ''), \
                patch.object(paid_models, 'ai_paid_summary_model', ''):
            none = _user(path, 7207)
            _pay(path, 7207, 'c7')
            job.turn_on_paid_models(none, path, send=send)
            _assert(_flag(path, 7207) is None and job.backfill(path) == 0,
                    "nothing configured: the effect does nothing (and is done)")
    finally:
        os.remove(path)


def test_who_gets_what():
    path = _db()
    try:
        with patch.object(paid_models, 'ai_paid_transcribe_model', ''), \
                patch.object(paid_models, 'ai_paid_summary_model', ''):
            _assert(paid_models.standing(1, path) is None and paid_models.pitch(1, 'en', path) == ''
                    and paid_models.transcript_note(1, 'whisper', 'en', path) == '',
                    "no paid model configured: no standing, no line")
        with patch.object(paid_models, 'ai_paid_transcribe_model', GROK), \
                patch.object(paid_models, 'ai_paid_summary_model', SONNET), \
                patch.object(paid_models, 'ai_summary_model', HAIKU), \
                patch.object(paid_models, 'ai_transcribe_model', WHISPER):
            _user(path, 7301, tariff_id=0, time_left=0)  # no plan, never paid
            _user(path, 7302)  # a trial
            _user(path, 7303, flags='{"paid_models": 1}')  # paid, on
            _user(path, 7304, flags='{"paid_models": 0}')  # paid, turned off
            _user(path, 7305, tariff_id=3, time_left=0, flags='{"paid_models": 1}')  # paid before, lapsed
            for chat, invoice in ((7303, 'a'), (7304, 'b'), (7305, 'c')):
                db = SQLighter(path)
                try:
                    uid = db.connection.execute("SELECT id FROM users WHERE telegramId = ?", (chat,)).fetchone()[0]
                    db.connection.execute("INSERT INTO payment_history VALUES (?, 'stars', ?, NULL, 'paid', 500, '')",
                                          (uid, invoice))
                    db.connection.commit()
                finally:
                    db.close()
            standing = {chat: paid_models.standing(chat, path) for chat in (7301, 7302, 7303, 7304, 7305)}
            _assert(standing == {7301: paid_models.NO_PLAN, 7302: paid_models.TRIAL, 7303: paid_models.ON,
                                 7304: paid_models.TURNED_OFF, 7305: paid_models.LAPSED}, "every standing")
            _assert([paid_models.summary_model(chat, path) for chat in (7301, 7302, 7303, 7304, 7305)]
                    == [HAIKU, HAIKU, SONNET, HAIKU, HAIKU], "only a paying chat with them on gets the paid model")
            _assert([paid_models.speakers(chat, path) for chat in (7302, 7303, 7304)] == [False, True, False]
                    and paid_models.transcribe_model(True) == GROK and paid_models.transcribe_model(False) == WHISPER,
                    "and its transcripts are made with speakers")
            what = get_message('paidModelsWhatBoth', 'en')
            _assert(paid_models.pitch(7301, 'en', path) == get_message('paidModelsNoPlan', 'en').format(what=what)
                    and paid_models.pitch(7302, 'en', path) == get_message('paidModelsTrial', 'en').format(what=what)
                    and paid_models.pitch(7305, 'en', path) == get_message('paidModelsLapsed', 'en').format(what=what)
                    and paid_models.pitch(7303, 'en', path) == '' and paid_models.pitch(7304, 'en', path) == '',
                    "the pitch: what a paid plan brings, what paying adds, what renewing brings back; "
                    "nothing to a payer")
            _assert(paid_models.ending_line(7303, 'en', path) == get_message('paidModelsEnding', 'en').format(what=what)
                    and paid_models.ending_line(7304, 'en', path) == ''
                    and paid_models.ending_line(7302, 'en', path) == '',
                    "D-3 tells a payer with them that they stop with the plan")
            notes = {chat: paid_models.transcript_note(chat, 'whisper', 'en', path)
                     for chat in (7301, 7302, 7303, 7304, 7305)}
            _assert(notes == {7301: get_message('paidTranscriptNoPlan', 'en'),
                              7302: get_message('paidTranscriptTrial', 'en'), 7303: '', 7304: '',
                              7305: get_message('paidTranscriptLapsed', 'en')},
                    "under Whisper's file: the line fits the chat, none to a payer")
            _assert(paid_models.transcript_note(7301, 'feed', 'en', path) == ''
                    and paid_models.transcript_note(7301, 'speakers', 'en', path) == '',
                    "the feed's transcript (the publisher's) or one with speakers: no promise")
            _assert(paid_models.transcript_note(7303, 'whisper', 'en', path, over_quota=True)
                    == get_message('paidTranscriptOverQuota', 'en'),
                    "a payer over its hours hears why the regular transcript came")
            help_text = paid_models.settings_help('en')
            _assert(get_message('paidModelsFeedNote', 'en') in help_text
                    and get_message('paidModelsCachedNote', 'en') in help_text,
                    "settings say what they do not change: the feed's transcript, a summary made before")
        with patch.object(paid_models, 'ai_paid_transcribe_model', GROK), \
                patch.object(paid_models, 'ai_paid_summary_model', ''):
            _assert(paid_models.what('en') == get_message('paidModelsWhatTranscript', 'en')
                    and get_message('paidModelsCachedNote', 'en') not in paid_models.settings_help('en'),
                    "only the transcription model: the copy names transcripts only")
            _assert(paid_models.summary_model(7303, path) == paid_models.ai_summary_model,
                    "and summaries keep the usual model")
        with patch.object(paid_models, 'ai_paid_transcribe_model', ''), \
                patch.object(paid_models, 'ai_paid_summary_model', SONNET):
            _assert(paid_models.what('en') == get_message('paidModelsWhatSummary', 'en')
                    and paid_models.transcript_note(7301, 'whisper', 'en', path) == ''
                    and not paid_models.speakers(7303, path),
                    "only the summary model: no word on transcripts, Whisper stays")
    finally:
        os.remove(path)


if __name__ == '__main__':
    test_rows_with_the_payment()
    test_runner()
    test_paid_models_effect()
    test_who_gets_what()
    print("all payment effect checks passed")
