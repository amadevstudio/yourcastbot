# -*- coding: utf-8 -*-
"""Durable send_outbox: rec/update jobs survive a process restart.

Uses a temporary file DB only — never opens production databases.
Run from the repo root: python db/test_send_outbox.py
"""
import json
import os
import sys
import tempfile
import threading

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db.sqliteAdapter import SQLighter  # noqa: E402
from app.core.sender import outbox  # noqa: E402


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _assert_true(got, label):
    if not got:
        raise AssertionError("%s: expected truthy, got %r" % (label, got))
    print("ok  %s" % label)


def _rec_job(chat_id=1001, link="https://example.com/ep.mp3"):
    return {
        'action': 'rec',
        'user_id': chat_id,
        'func_params': {
            'link': link,
            'chat_ids': {chat_id: {}},
            'utglangs': {chat_id: 'en'},
            'bitratestg': {chat_id: 64},
            'podcastInfo': {
                'id': 7,
                'title': 'Episode',
                'chName': 'Show',
            },
        },
    }


def _simulate_restart(db_path):
    """New SQLighter like a fresh process, then reclaim leased rows."""
    import db.sqliteAdapter as sqlite_adapter
    sqlite_adapter._send_outbox_ready.clear()
    sqlite_adapter._runtime_kv_ready.clear()
    sqlite_adapter._digest_outbox_ready.clear()
    sqlite_adapter._users_digest_ready.clear()
    sqlite_adapter._users_deleted_at_checked = False
    sqlite_adapter._channel_http_validators_checked = False
    outbox.clear_in_flight()
    db = SQLighter(db_path)
    try:
        tables = [
            row[0] for row in db.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        _assert_true('send_outbox' in tables, "restart SQLighter sees send_outbox")
    finally:
        db.close()
    return outbox.reclaim(database=db_path, force=True)


def test_dispatch_without_balancer_stays_pending(db_path):
    recs_name = 'app.controller.builders.recsModule'
    _assert_true(
        recs_name not in sys.modules,
        "recsModule must not be imported by outbox tests")
    outbox_id = outbox.enqueue(
        _rec_job(chat_id=8008), database=db_path, dispatch=True)
    _assert_true(
        recs_name not in sys.modules,
        "dispatch=True must not import recsModule")
    row = outbox.get_row(outbox_id, database=db_path)
    _assert_eq(row['status'], 'pending', "no balancer: row stays pending")


def test_sqlighter_creates_table(db_path):
    db = SQLighter(db_path)
    try:
        names = [
            row[0] for row in db.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        _assert_true('send_outbox' in names, "SQLighter creates send_outbox")
        _assert_true(
            'bot_runtime_kv' in names, "SQLighter creates bot_runtime_kv")
        _assert_true(
            'digest_outbox' in names, "SQLighter creates digest_outbox")
        columns = [
            row[1] for row in db.connection.execute(
                "PRAGMA table_info(send_outbox)").fetchall()]
        for required in (
                'id', 'created_at', 'action', 'user_id', 'payload_json',
                'status', 'attempts', 'leased_until', 'available_at'):
            _assert_true(required in columns, "column %s" % required)
    finally:
        db.close()


def test_enqueue_survives_restart(db_path):
    job = _rec_job(chat_id=1001, link="https://example.com/ep.mp3")
    outbox_id = outbox.enqueue(job, database=db_path, dispatch=False)
    _assert_true(outbox_id >= 1, "enqueue returned id")
    row = outbox.get_row(outbox_id, database=db_path)
    _assert_eq(row['status'], 'pending', "stored status before restart")
    _assert_eq(row['action'], 'rec', "stored action")

    _simulate_restart(db_path)
    claimed = outbox.claim(database=db_path)
    _assert_true(claimed is not None, "claim after restart returned a job")
    _assert_eq(claimed['outbox_id'], outbox_id, "same outbox id after restart")
    _assert_eq(claimed['action'], 'rec', "action after restart")
    _assert_eq(
        claimed['func_params']['link'], "https://example.com/ep.mp3",
        "link after restart")
    _assert_eq(
        claimed['func_params']['chat_ids'][1001], {},
        "chat_id map after restart")


def test_claim_done_not_claimed_again(db_path):
    outbox.enqueue(_rec_job(chat_id=2002), database=db_path, dispatch=False)
    first = outbox.claim(database=db_path)
    _assert_true(first is not None, "first claim")
    second = outbox.claim(database=db_path)
    _assert_eq(second, None, "leased row is not claimed again")

    outbox.mark_done(
        first['outbox_id'], database=db_path,
        attempts=first['outbox_attempts'])
    row = outbox.get_row(first['outbox_id'], database=db_path)
    _assert_eq(row['status'], 'done', "status after success")
    third = outbox.claim(database=db_path)
    _assert_eq(third, None, "done row is not claimed again")


def test_fail_or_retry_skips_done_row(db_path):
    """Crash after Telegram ACK but during file delete must not resend."""
    outbox_id = outbox.enqueue(
        _rec_job(chat_id=2102), database=db_path, dispatch=False)
    claimed = outbox.claim(database=db_path, outbox_id=outbox_id)
    outbox.mark_done(
        claimed['outbox_id'], database=db_path,
        attempts=claimed['outbox_attempts'])
    outcome = outbox.fail_or_retry(
        claimed['outbox_id'], error=RuntimeError("cleanup"),
        database=db_path, attempts=claimed['outbox_attempts'], dispatch=False)
    _assert_eq(outcome, 'skipped', "fail_or_retry ignores a done receipt")
    row = outbox.get_row(outbox_id, database=db_path)
    _assert_eq(row['status'], 'done', "stays done after cleanup crash")
    _assert_eq(outbox.claim(database=db_path), None, "done is not claimed")
    outbox.mark_done(
        claimed['outbox_id'], database=db_path,
        attempts=claimed['outbox_attempts'])
    row = outbox.get_row(outbox_id, database=db_path)
    _assert_eq(row['status'], 'done', "second mark_done is a no-op")


def test_crash_after_lease_reclaim(db_path):
    outbox_id = outbox.enqueue(
        _rec_job(chat_id=3003), database=db_path, dispatch=False)
    leased = outbox.claim(database=db_path, outbox_id=outbox_id)
    _assert_true(leased is not None, "claimed before crash")
    row = outbox.get_row(outbox_id, database=db_path)
    _assert_eq(row['status'], 'leased', "status after claim")

    # Lease still in the future: expired-only reclaim must leave it leased.
    expired_only = outbox.reclaim(database=db_path, force=False)
    _assert_eq(expired_only, 0, "unexpired lease is not reclaimed")
    row = outbox.get_row(outbox_id, database=db_path)
    _assert_eq(row['status'], 'leased', "still leased before expiry")

    db = SQLighter(db_path)
    try:
        db.cursor.execute(
            "UPDATE send_outbox SET leased_until = ? WHERE id = ?",
            ("2000-01-01T00:00:00Z", outbox_id))
        db.connection.commit()
    finally:
        db.close()

    # Live process still holds the job: do not reclaim even if the clock expired.
    skipped = outbox.reclaim(database=db_path, force=False)
    _assert_eq(skipped, 0, "in-flight expired lease is not reclaimed")
    row = outbox.get_row(outbox_id, database=db_path)
    _assert_eq(row['status'], 'leased', "still leased while in-flight")

    # Crash: in-memory set is gone, expired lease can be retried (at-least-once).
    outbox.clear_in_flight()
    n = outbox.reclaim(database=db_path, force=False)
    _assert_true(n >= 1, "expired lease reclaimed after crash")
    row = outbox.get_row(outbox_id, database=db_path)
    _assert_eq(row['status'], 'pending', "reclaim makes it pending again")

    claimed = outbox.claim(database=db_path)
    _assert_eq(claimed['outbox_id'], outbox_id, "reclaimed job can be claimed")


def test_heartbeat_renews_in_flight_lease(db_path):
    outbox_id = outbox.enqueue(
        _rec_job(chat_id=9009), database=db_path, dispatch=False)
    claimed = outbox.claim(database=db_path, outbox_id=outbox_id)
    _assert_true(claimed is not None, "claimed for heartbeat")
    db = SQLighter(db_path)
    try:
        db.cursor.execute(
            "UPDATE send_outbox SET leased_until = ? WHERE id = ?",
            ("2000-01-01T00:00:00Z", outbox_id))
        db.connection.commit()
    finally:
        db.close()
    n = outbox.heartbeat(database=db_path)
    _assert_true(n >= 1, "heartbeat renewed in-flight row")
    row = outbox.get_row(outbox_id, database=db_path)
    _assert_true(
        row['leased_until'] > "2000-01-01T00:00:00Z",
        "leased_until moved into the future")
    skipped = outbox.reclaim(database=db_path, force=False)
    _assert_eq(skipped, 0, "renewed lease is not reclaimed")
    outbox.mark_done(
        outbox_id, database=db_path, attempts=claimed['outbox_attempts'])


def test_payload_json_round_trip(db_path):
    chat_id = 4004
    link = "https://cdn.example.com/audio.mp3"
    outbox_id = outbox.enqueue(
        _rec_job(chat_id=chat_id, link=link),
        database=db_path, dispatch=False)
    row = outbox.get_row(outbox_id, database=db_path)
    payload = json.loads(row['payload_json'])
    _assert_eq(payload['func_params']['link'], link, "stored link")
    _assert_true(
        str(chat_id) in payload['func_params']['chat_ids'],
        "stored chat_ids uses JSON string keys")

    claimed = outbox.claim(database=db_path, outbox_id=outbox_id)
    _assert_eq(claimed['func_params']['link'], link, "round-trip link")
    _assert_eq(
        claimed['user_id'], chat_id, "round-trip user_id as int")
    _assert_eq(
        claimed['func_params']['chat_ids'][chat_id], {},
        "round-trip chat_id key as int")
    _assert_eq(
        claimed['func_params']['utglangs'][chat_id], 'en',
        "round-trip utglangs")


def test_update_payload_drops_telegram_objects(db_path):
    class FakeCallback(object):
        def __init__(self):
            self.id = "cb"

    chat_id = 5005
    outbox_id = outbox.enqueue({
        'action': 'update',
        'user_id': chat_id,
        'bot': object(),
        'func_params': {
            'data': {
                'chat_id': chat_id,
                'language_code': 'ru',
                'callback': FakeCallback(),
                'message': FakeCallback(),
                'go_back_action': lambda: None,
            },
            'is_user_have_bot_subscription': True,
        },
    }, database=db_path, dispatch=False)
    row = outbox.get_row(outbox_id, database=db_path)
    payload = json.loads(row['payload_json'])
    stored = payload['func_params']
    _assert_eq(stored['chat_id'], chat_id, "update chat_id")
    _assert_eq(stored['language_code'], 'ru', "update language_code")
    _assert_eq(
        stored['is_user_have_bot_subscription'], True,
        "update subscription flag")
    _assert_true('callback' not in stored, "callback not persisted")
    _assert_true('data' not in stored, "ControllerParams not persisted")

    claimed = outbox.claim(database=db_path, outbox_id=outbox_id)
    data = claimed['func_params']['data']
    _assert_eq(data['chat_id'], chat_id, "reconstructed chat_id")
    _assert_eq(data['language_code'], 'ru', "reconstructed language_code")
    _assert_eq(data['callback'], None, "callback is None after dequeue")
    _assert_eq(
        claimed['func_params']['is_user_have_bot_subscription'], True,
        "reconstructed subscription flag")


def test_claim_is_exclusive(db_path):
    outbox.enqueue(_rec_job(chat_id=6006), database=db_path, dispatch=False)
    results = [None, None]
    barrier = threading.Barrier(2)

    def worker(index):
        barrier.wait(timeout=5)
        results[index] = outbox.claim(database=db_path)

    threads = [
        threading.Thread(target=worker, args=(0,)),
        threading.Thread(target=worker, args=(1,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        if thread.is_alive():
            raise AssertionError("claim thread did not finish")
    got = [item for item in results if item is not None]
    _assert_eq(len(got), 1, "exactly one claim wins")


def test_max_attempts_marks_failed(db_path):
    outbox_id = outbox.enqueue(
        _rec_job(chat_id=7007), database=db_path, dispatch=False)
    last_outcome = None
    for _ in range(outbox.MAX_ATTEMPTS):
        claimed = outbox.claim(database=db_path, outbox_id=outbox_id)
        _assert_true(claimed is not None, "claim before max attempts")
        last_outcome = outbox.fail_or_retry(
            outbox_id, error=RuntimeError("boom"),
            database=db_path, attempts=claimed['outbox_attempts'],
            dispatch=False)
        if last_outcome == 'pending':
            # backoff is in the future; the next claim in this test should not wait
            db = SQLighter(db_path)
            try:
                db.cursor.execute(
                    "UPDATE send_outbox SET available_at = ? WHERE id = ?",
                    ("2000-01-01T00:00:00Z", outbox_id))
                db.connection.commit()
            finally:
                db.close()
    _assert_eq(last_outcome, 'failed', "failed after max attempts")
    row = outbox.get_row(outbox_id, database=db_path)
    _assert_eq(row['status'], 'failed', "row status failed")
    _assert_eq(
        outbox.claim(database=db_path, outbox_id=outbox_id), None,
        "failed row is not claimed")


def test_heartbeat_extends_lease(db_path):
    outbox_id = outbox.enqueue(
        _rec_job(chat_id=9009), database=db_path, dispatch=False)
    claimed = outbox.claim(database=db_path, outbox_id=outbox_id)
    _assert_true(claimed is not None, "claimed for heartbeat")
    before = outbox.get_row(outbox_id, database=db_path)['leased_until']
    n = outbox.heartbeat(database=db_path)
    _assert_true(n >= 1, "heartbeat renewed at least one lease")
    after = outbox.get_row(outbox_id, database=db_path)['leased_until']
    _assert_true(after >= before, "leased_until did not go backwards")
    outbox.mark_done(outbox_id, database=db_path, attempts=claimed['outbox_attempts'])


def test_lease_is_short(_db_path=None):
    _assert_true(
        outbox.LEASE_SECONDS <= 5 * 60, "lease is at most 5 minutes")
    _assert_true(
        outbox.HEARTBEAT_SECONDS < outbox.LEASE_SECONDS,
        "heartbeat is faster than the lease")
    _assert_true(
        outbox.TOUCH_MIN_INTERVAL_SECONDS < outbox.HEARTBEAT_SECONDS,
        "touch from the worker is at least as frequent as the belt loop")


def test_flood_wait_seconds(_db_path=None):
    _assert_eq(
        outbox.flood_wait_seconds(
            RuntimeError("Too Many Requests: retry after 37")),
        38, "bot api retry-after plus one")
    _assert_eq(
        outbox.flood_wait_seconds(
            RuntimeError("A wait of 10 seconds is required")),
        11, "telethon flood wait plus one")
    wrapped = outbox.OutboxRetryableError(
        RuntimeError("Too Many Requests: retry after 12"))
    _assert_eq(
        outbox.flood_wait_seconds(wrapped), 13,
        "OutboxRetryableError unwraps cause")
    _assert_eq(
        outbox.flood_wait_seconds(RuntimeError("chat not found")),
        None, "non-flood is None")


def test_touch_renews_one_lease(db_path):
    first_id = outbox.enqueue(
        _rec_job(chat_id=9101), database=db_path, dispatch=False)
    second_id = outbox.enqueue(
        _rec_job(chat_id=9102), database=db_path, dispatch=False)
    first = outbox.claim(database=db_path, outbox_id=first_id)
    second = outbox.claim(database=db_path, outbox_id=second_id)
    db = SQLighter(db_path)
    try:
        db.cursor.execute(
            "UPDATE send_outbox SET leased_until = ? WHERE id IN (?, ?)",
            ("2000-01-01T00:00:00Z", first_id, second_id))
        db.connection.commit()
    finally:
        db.close()
    n = outbox.touch(
        first_id, database=db_path, attempts=first['outbox_attempts'])
    _assert_eq(n, 1, "touch updated one row")
    first_row = outbox.get_row(first_id, database=db_path)
    second_row = outbox.get_row(second_id, database=db_path)
    _assert_true(
        first_row['leased_until'] > "2000-01-01T00:00:00Z",
        "touched row moved into the future")
    _assert_eq(
        second_row['leased_until'], "2000-01-01T00:00:00Z",
        "untouched row stayed expired")
    outbox.mark_done(
        first_id, database=db_path, attempts=first['outbox_attempts'])
    n = outbox.touch(
        first_id, database=db_path, attempts=first['outbox_attempts'])
    _assert_eq(n, 0, "touch of a done row is a no-op")
    outbox.mark_done(
        second_id, database=db_path, attempts=second['outbox_attempts'])


def test_fail_or_retry_uses_telegram_retry_after(db_path):
    outbox_id = outbox.enqueue(
        _rec_job(chat_id=9202), database=db_path, dispatch=False)
    claimed = outbox.claim(database=db_path, outbox_id=outbox_id)
    before = outbox.now_iso()
    outcome = outbox.fail_or_retry(
        outbox_id,
        error=RuntimeError("Too Many Requests: retry after 37"),
        database=db_path, attempts=claimed['outbox_attempts'],
        dispatch=False)
    _assert_eq(outcome, 'pending', "429 goes back to pending")
    row = outbox.get_row(outbox_id, database=db_path)
    _assert_eq(row['status'], 'pending', "row is pending")
    _assert_true(
        row['available_at'] > before,
        "available_at is in the future")
    claimed_early = outbox.claim(database=db_path, outbox_id=outbox_id)
    _assert_eq(claimed_early, None, "not claimable before retry-after")


def test_force_reclaim_after_restart(db_path):
    outbox_id = outbox.enqueue(
        _rec_job(chat_id=9010), database=db_path, dispatch=False)
    outbox.claim(database=db_path, outbox_id=outbox_id)
    _simulate_restart(db_path)
    row = outbox.get_row(outbox_id, database=db_path)
    _assert_eq(row['status'], 'pending', "force reclaim on restart")
    claimed = outbox.claim(database=db_path)
    _assert_eq(claimed['outbox_id'], outbox_id, "restarted job is claimable")


def main():
    tmpdir = tempfile.mkdtemp(prefix="yourcast_send_outbox_")
    cases = (
        test_dispatch_without_balancer_stays_pending,
        test_sqlighter_creates_table,
        test_enqueue_survives_restart,
        test_claim_done_not_claimed_again,
        test_fail_or_retry_skips_done_row,
        test_crash_after_lease_reclaim,
        test_heartbeat_renews_in_flight_lease,
        test_payload_json_round_trip,
        test_update_payload_drops_telegram_objects,
        test_claim_is_exclusive,
        test_max_attempts_marks_failed,
        test_heartbeat_extends_lease,
        test_lease_is_short,
        test_flood_wait_seconds,
        test_touch_renews_one_lease,
        test_fail_or_retry_uses_telegram_retry_after,
        test_force_reclaim_after_restart,
    )
    for index, case in enumerate(cases):
        path = os.path.join(tmpdir, "case_%d.db" % index)
        print("-- %s" % case.__name__)
        # Guard: tests must never point at the production database file.
        if os.path.abspath(path) == os.path.abspath(os.path.join(
                _ROOT, "db", "yourcast.db")):
            raise AssertionError("refusing to use production yourcast.db")
        case(path)
    print("all send_outbox checks passed")


if __name__ == "__main__":
    main()
