"""Persistent private collections. Starting freezes membership and reserves the whole batch atomically.

Recordings retain the existing AI queue's FIFO, leases and per-recording audio ledger. A final
request follows their individual requests; retries never resend already completed children.
No AI requests (or quota charges) exist while a collection is still being assembled.
"""
import secrets
import time

from db import ai

MAX_BATCH_BYTES = 200 * 1024 * 1024
MAX_BATCH_SECONDS = 6 * 3600
DRAFT_SECONDS = 86400
KEEP_SECONDS = 7 * 86400
PART, FINISH, SUMMARY_ALL, TEXT_ALL = 'voice_part', 'voice_finish', 'voice_summary_all', 'voice_text_all'
FINAL_KINDS = (FINISH, SUMMARY_ALL, TEXT_ALL)


class BatchChanged(Exception):
    pass


class BatchLimit(Exception):
    pass


def batch(ref, chat_id, database=None):
    return ai._one(database, 'SELECT * FROM voice_batches WHERE ref=? AND chat_id=? AND expires_at>?',
                   (ref, int(chat_id), time.time()))


def items(ref, database=None):
    c = ai.connect(database)
    try:
        return [dict(row) for row in c.execute('SELECT * FROM voice_items WHERE batch=? ORDER BY message_id', (ref,))]
    finally:
        c.close()


def stage(chat_id, ref, message_id, seconds, size, database=None):
    """Register an arrival from what Telegram says (`seconds` is a claim, measured after the start):
    it is a member at once, so Start cannot silently omit it, and nothing is downloaded."""
    c = ai.connect(database)
    try:
        with c:
            c.execute('BEGIN IMMEDIATE')
            c.execute("UPDATE voice_batches SET state='expired' WHERE chat_id=? AND state='collecting' AND expires_at<=?",
                      (int(chat_id), time.time()))
            row = c.execute("SELECT * FROM voice_batches WHERE chat_id=? AND state='collecting'", (int(chat_id),)).fetchone()
            if row is None:
                batch_ref = 'b_' + secrets.token_hex(10)
                c.execute('INSERT INTO voice_batches (ref,chat_id,created_at,expires_at) VALUES (?,?,?,?)',
                          (batch_ref, int(chat_id), time.time(), time.time() + DRAFT_SECONDS))
            else:
                batch_ref = row['ref']
            old = c.execute('SELECT id FROM voice_items WHERE batch=? AND message_id=?', (batch_ref, message_id)).fetchone()
            if old:
                return batch_ref, old[0], False
            total = c.execute('SELECT COALESCE(SUM(seconds),0),COALESCE(SUM(bytes),0) FROM voice_items WHERE batch=?',
                              (batch_ref,)).fetchone()
            if total[0] + seconds > MAX_BATCH_SECONDS or total[1] + size > MAX_BATCH_BYTES:
                raise BatchLimit()
            item = c.execute("INSERT INTO voice_items (batch,ref,message_id,seconds,bytes,status) VALUES (?,?,?,?,?,'ready')",
                             (batch_ref, ref, message_id, seconds, size)).lastrowid
            c.execute('UPDATE voice_batches SET revision=revision+1 WHERE ref=?', (batch_ref,))
            return batch_ref, item, True
    finally:
        c.close()


def ready(item, seconds, database=None):
    c = ai.connect(database)
    try:
        with c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT batch, seconds FROM voice_items WHERE id=?', (item,)).fetchone()
            total = c.execute('SELECT SUM(seconds) FROM voice_items WHERE batch=?', (row['batch'],)).fetchone()[0]
            if total - row['seconds'] + seconds > MAX_BATCH_SECONDS:
                raise BatchLimit()
            c.execute("UPDATE voice_items SET status='ready',seconds=? WHERE id=?", (seconds, item))
            c.execute('UPDATE voice_batches SET revision=revision+1 WHERE ref=?', (row['batch'],))
    finally:
        c.close()


def discard_item(item, database=None):
    c = ai.connect(database)
    try:
        with c:
            c.execute('UPDATE voice_batches SET revision=revision+1 WHERE ref IN (SELECT batch FROM voice_items WHERE id=?)', (item,))
            c.execute('DELETE FROM voice_items WHERE id=?', (item,))
    finally:
        c.close()


def select(ref, chat_id, output, database=None):
    if output not in (None, 'summary', 'transcript'):
        raise ValueError('invalid voice output')
    ai._write(database, 'UPDATE voice_batches SET selected=? WHERE ref=? AND chat_id=? AND expires_at>?',
              (output, ref, int(chat_id), time.time()))


def set_message(ref, message_id, database=None):
    ai._write(database, 'UPDATE voice_batches SET message_id=? WHERE ref=?', (message_id, ref))


def _needed(c, chat_id, rows):
    needed, seen = [], set()
    for row in rows:
        ref = row['ref']
        cached = c.execute('SELECT 1 FROM ai_transcripts WHERE ref=?', (ref,)).fetchone()
        paid = c.execute("SELECT 1 FROM ai_requests WHERE ref=? AND chat_id=? AND seconds>0 "
                         "AND status IN ('uploading','pending','working','done') LIMIT 1", (ref, int(chat_id))).fetchone()
        seconds = 0 if ref in seen or (cached and paid) else row['seconds']
        needed.append(seconds)
        seen.add(ref)
    return needed


def quote(ref, chat_id, database=None):
    found = batch(ref, chat_id, database)
    if found is None:
        raise BatchChanged()
    c = ai.connect(database)
    try:
        rows = items(ref, database)
        return found, rows, sum(_needed(c, chat_id, rows))
    finally:
        c.close()


def launch(ref, chat_id, revision, output, mode, lang, limit, expected_seconds, title, database=None):
    """All children and final result in one transaction; stale previews and double taps cannot charge.

    `expected_seconds`: the quoted charge. A newer cache may reduce it, never increase it without
    showing the preview again. A batch already running cannot start another output concurrently.
    """
    if output not in ('summary', 'transcript') or mode not in ('each', 'all'):
        raise ValueError('invalid voice operation')
    c = ai.connect(database)
    try:
        with c:
            c.execute('BEGIN IMMEDIATE')
            b = c.execute('SELECT * FROM voice_batches WHERE ref=? AND chat_id=? AND expires_at>?',
                          (ref, int(chat_id), time.time())).fetchone()
            if b is None or b['revision'] != revision or b['selected'] != output:
                raise BatchChanged()
            running = c.execute("SELECT r.request_id FROM voice_runs r JOIN ai_requests a ON a.id=r.request_id "
                                "WHERE r.batch=? AND a.status IN ('uploading','pending','working')", (ref,)).fetchone()
            if running:
                return running[0], False
            rows = c.execute('SELECT * FROM voice_items WHERE batch=? ORDER BY message_id', (ref,)).fetchall()
            if not rows or any(row['status'] != 'ready' for row in rows):
                raise BatchChanged()
            needed = _needed(c, chat_id, rows)
            used = c.execute("SELECT COALESCE(SUM(seconds),0) FROM ai_requests WHERE chat_id=? AND created_at>=? "
                             "AND status IN ('uploading','pending','working','done')", (int(chat_id), time.time() - 30 * 86400)).fetchone()[0]
            if sum(needed) > expected_seconds or used + sum(needed) > limit:
                raise BatchChanged()
            # Keep each recording accessible for the lifetime of this frozen collection.
            expires = b['expires_at'] if b['state'] == 'frozen' else time.time() + KEEP_SECONDS
            c.execute("UPDATE voice_batches SET state='frozen',expires_at=? WHERE ref=?", (expires, ref))
            c.execute('INSERT OR IGNORE INTO ai_episodes (ref,link,title,show,seen_at,seconds,owner_chat,expires_at) '
                      "VALUES (?,'',?,'',?,0,?,?)", (ref, title, time.time(), int(chat_id), expires))
            children = []
            for row, seconds in zip(rows, needed):
                c.execute('UPDATE ai_episodes SET expires_at=MAX(expires_at,?) WHERE ref=? AND owner_chat=?',
                          (expires, row['ref'], int(chat_id)))
                kind = output if mode == 'each' else PART
                cursor = c.execute('INSERT INTO ai_requests (chat_id,ref,lang,status,created_at,seconds,reply_to,kind) '
                                   "VALUES (?,?,?,'uploading',?,?,?,?)",
                                   (int(chat_id), row['ref'], lang if output == 'summary' else '', time.time(), seconds,
                                    row['message_id'], kind))
                children.append((row['id'], cursor.lastrowid))
            kind = FINISH if mode == 'each' else SUMMARY_ALL if output == 'summary' else TEXT_ALL
            request_id = c.execute('INSERT INTO ai_requests (chat_id,ref,lang,status,created_at,seconds,reply_to,kind) '
                                   "VALUES (?,?,?,'uploading',?,0,?,?)",
                                   (int(chat_id), ref, lang, time.time(), b['message_id'], kind)).lastrowid
            c.execute('INSERT INTO voice_runs VALUES (?,?,?,?)', (request_id, ref, output, mode))
            c.executemany('INSERT INTO voice_run_items VALUES (?,?,?)', [(request_id, item, req) for item, req in children])
            return request_id, True
    finally:
        c.close()


_WAITING = ("SELECT a.id request_id, a.chat_id, a.seconds, a.ref, i.message_id, i.bytes, i.batch, u.lang ui_lang "
            "FROM ai_requests a JOIN voice_run_items r ON r.request_id=a.id JOIN voice_items i ON i.id=r.item "
            "LEFT JOIN users u ON u.telegramId=a.chat_id WHERE a.status='uploading'")


def uploading_chats(database=None):
    """Chats with recordings that wait for their audio (reserved at the start, not yet downloaded)."""
    c = ai.connect(database)
    try:
        return [row[0] for row in c.execute("SELECT DISTINCT a.chat_id FROM ai_requests a "
                                            "JOIN voice_run_items r ON r.request_id=a.id WHERE a.status='uploading'")]
    finally:
        c.close()


def uploading(chat_id, database=None):
    c = ai.connect(database)
    try:
        return [dict(row) for row in c.execute(_WAITING + ' AND a.chat_id=? ORDER BY a.id', (int(chat_id),))]
    finally:
        c.close()


def release(request_id, measured=None, charged=None, database=None):
    """The audio is here: the request can be claimed. `measured`: its real length; `charged`: what
    it takes from the plan's hours now (a request that was free stays free)."""
    c = ai.connect(database)
    try:
        with c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT a.ref, a.chat_id FROM ai_requests a WHERE a.id=? AND a.status=?',
                            (request_id, 'uploading')).fetchone()
            if row is None:
                return
            if measured is not None:
                c.execute('UPDATE voice_items SET seconds=? WHERE id IN (SELECT item FROM voice_run_items WHERE request_id=?)',
                          (measured, request_id))
                c.execute('UPDATE ai_episodes SET seconds=? WHERE ref=? AND owner_chat=?',
                          (measured, row['ref'], row['chat_id']))
            c.execute("UPDATE ai_requests SET status='pending',seconds=COALESCE(?,seconds) WHERE id=?",
                      (charged, request_id))
    finally:
        c.close()


def fail_child(request_id, database=None):
    ai._write(database, "UPDATE ai_requests SET status='failed',leased_until=NULL WHERE id=? AND status='uploading'", (request_id,))


def settle(database=None, now=None):
    """Runs whose recordings all left `uploading` start their final request, or end it when one failed.
    Requests that waited over an hour for audio that never came fail too (their hours go back).
    Returns [{final, batch, chat_id, ui_lang, failed}] for the runs settled."""
    now = time.time() if now is None else now
    c = ai.connect(database)
    try:
        with c:
            c.execute('BEGIN IMMEDIATE')
            c.execute("UPDATE ai_requests SET status='failed' WHERE status='uploading' AND created_at<?", (now - 3600,))
            settled = []
            for final in c.execute("SELECT r.request_id, r.batch, a.chat_id, u.lang FROM voice_runs r "
                                   "JOIN ai_requests a ON a.id=r.request_id LEFT JOIN users u ON u.telegramId=a.chat_id "
                                   "WHERE a.status='uploading'").fetchall():
                states = [row[0] for row in c.execute(
                    'SELECT a.status FROM voice_run_items r JOIN ai_requests a ON a.id=r.request_id WHERE r.run=?',
                    (final['request_id'],))]
                if 'uploading' in states:
                    continue
                failed = 'failed' in states
                c.execute('UPDATE ai_requests SET status=? WHERE id=?', ('failed' if failed else 'pending', final['request_id']))
                settled.append({'final': final['request_id'], 'batch': final['batch'], 'chat_id': final['chat_id'],
                                'ui_lang': final['lang'], 'failed': failed})
            return settled
    finally:
        c.close()


def progress(ref, database=None):
    """{status: n} of the recordings of the batch's latest run."""
    c = ai.connect(database)
    try:
        run = c.execute('SELECT request_id FROM voice_runs WHERE batch=? ORDER BY request_id DESC LIMIT 1', (ref,)).fetchone()
        if run is None:
            return {}
        return {row[0]: row[1] for row in c.execute(
            'SELECT a.status, COUNT(*) FROM voice_run_items r JOIN ai_requests a ON a.id=r.request_id '
            'WHERE r.run=? GROUP BY a.status', (run[0],))}
    finally:
        c.close()


def batch_of_request(request_id, database=None):
    row = ai._one(database, 'SELECT i.batch FROM voice_run_items r JOIN voice_items i ON i.id=r.item '
                            'WHERE r.request_id=? LIMIT 1', (request_id,))
    return row['batch'] if row else None


def run_items(request_id, database=None):
    c = ai.connect(database)
    try:
        return [dict(row) for row in c.execute('SELECT i.*, a.status request_status FROM voice_run_items r '
                    'JOIN voice_items i ON i.id=r.item JOIN ai_requests a ON a.id=r.request_id '
                    'WHERE r.run=? ORDER BY i.message_id', (request_id,))]
    finally:
        c.close()


def cleanup(database=None, now=None):
    now = time.time() if now is None else now
    c = ai.connect(database)
    try:
        with c:
            c.execute('DELETE FROM voice_run_items WHERE run IN (SELECT r.request_id FROM voice_runs r '
                      'JOIN voice_batches b ON b.ref=r.batch WHERE b.expires_at<=?)', (now,))
            c.execute('DELETE FROM voice_runs WHERE batch IN (SELECT ref FROM voice_batches WHERE expires_at<=?)', (now,))
            c.execute('DELETE FROM voice_items WHERE batch IN (SELECT ref FROM voice_batches WHERE expires_at<=?)', (now,))
            c.execute('DELETE FROM voice_batches WHERE expires_at<=?', (now,))
            # An interrupted download is never silently included in a confirmed batch.
            c.execute("UPDATE voice_items SET status='failed' WHERE status='downloading' AND batch IN "
                      '(SELECT ref FROM voice_batches WHERE created_at<?)', (now - 3600,))
    finally:
        c.close()
