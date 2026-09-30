# -*- coding: utf-8 -*-
"""Read-only "which episodes did a chat miss" reports. DB and updater logs.

Used by tools/debugging_utilities/missed_episodes.py (on the server) and by
GET /api/diag/* (admin API, separate read-only token). Nothing here writes:
the DB is opened with mode=ro.

report(): one chat and one server-local hour. An episode is missed when a
circle job for one of the chat's podcasts was queued in that hour for other
listeners and neither that job nor any rec job gave it to this chat.
Podcasts the updater processed in that hour without a circle job are listed
too: if the chat is their only payer there is no job to compare with.

audit(): paying users whose current period began since LOSSY_SINCE. Until
3c52606 every renewal left a payer an hour at time_left = 0, and since
7830e35 a nosub flag in that hour moves the cursor past the new episode.
A flag in the hours before the period start is the gap; a payment that day
means they probably bought after the digest (they were free: by design).
Traces expire: logs after 3 days, outbox and flags after 7.

DB timestamps are UTC; logs and the reported hours are server-local.
"""
import datetime
import hmac
import json
import os
import re
import sqlite3

import config

LOSSY_SINCE = datetime.datetime(2026, 9, 3)  # 7830e35: the nosub flag moves the cursor
OUTBOX_KEEP = datetime.timedelta(days=7)
MIN_TOKEN_LENGTH = 32

LOG_ENTRY = re.compile(r"^\[(\d\d:\d\d:\d\d \d\d\.\d\d\.\d\d\d\d)\] ")
CHANNEL_IN_LOG = re.compile(
    r"(?:Processig channel|Channel id:|for channel) (\d+)")


def token_ok(authorization, configured) -> bool:
    """'Bearer <token>' against the configured diag token. Off when unset or short."""
    if not configured or len(str(configured)) < MIN_TOKEN_LENGTH:
        return False
    if not authorization or not authorization.startswith("Bearer "):
        return False
    given = authorization[len("Bearer "):].strip()
    return hmac.compare_digest(given.encode("utf-8"), str(configured).encode("utf-8"))


def enabled(configured) -> bool:
    return bool(configured) and len(str(configured)) >= MIN_TOKEN_LENGTH


def connect_ro(path=None):
    conn = sqlite3.connect(
        "file:%s?mode=ro" % (config.db_path if path is None else path), uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def utc_to_local(value):
    """'2026-09-30T05:06:01Z' or '2026-09-30 05:06:01' (UTC) -> naive local."""
    if not value:
        return None
    text = str(value).strip().replace("T", " ").rstrip("Z")[:19]
    try:
        parsed = datetime.datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return parsed.replace(tzinfo=datetime.timezone.utc).astimezone().replace(tzinfo=None)


def local_to_utc_text(value):
    return value.astimezone().astimezone(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def parse_hour(text):
    """'YYYY-MM-DD HH' (server-local) -> datetime; ValueError otherwise."""
    return datetime.datetime.strptime(str(text).strip(), "%Y-%m-%d %H")


def short(record_uniq_id, width=70):
    text = str(record_uniq_id or "")
    return text if len(text) <= width else "..." + text[-width:]


def payload_info(row):
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except (TypeError, ValueError):
        payload = {}
    params = payload.get("func_params", payload) or {}
    info = params.get("podcastInfo") or {}
    chats = {str(chat) for chat in (params.get("chat_ids") or {})}
    return info, chats


def payload_link(row):
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except (TypeError, ValueError):
        return None
    return (payload.get("func_params", payload) or {}).get("link")


def log_entries(start, end, work_dir=None, out=print):
    """Updater log entries (with continuation lines) in [start, end)."""
    base = config.work_dir if work_dir is None else work_dir
    day = start.date()
    while day <= end.date():
        path = os.path.join(base, "log", "updater_%s.log" % day.strftime("%d_%m_%Y"))
        if not os.path.exists(path):
            out("  (no log file updater_%s.log; logs keep 3 days)" % day.strftime("%d_%m_%Y"))
            day += datetime.timedelta(days=1)
            continue
        entry = None
        with open(path, encoding="utf-8", errors="replace") as log_file:
            for line in log_file:
                match = LOG_ENTRY.match(line)
                if match:
                    if entry is not None:
                        yield entry
                    stamp = datetime.datetime.strptime(match.group(1), "%H:%M:%S %d.%m.%Y")
                    entry = [stamp, line.rstrip("\n")] if start <= stamp < end else None
                elif entry is not None:
                    entry[1] += "\n" + line.rstrip("\n")
        if entry is not None:
            yield entry
        day += datetime.timedelta(days=1)


def load_jobs(conn, tg, channel_ids, since_utc):
    """rec jobs of this chat and circle jobs of these podcasts, oldest first."""
    circle_users = ["c%s" % cid for cid in channel_ids]
    return conn.execute(
        "SELECT id, created_at, action, user_id, payload_json, status FROM send_outbox "
        "WHERE created_at >= ? AND ((action = 'rec' AND user_id = ?) OR "
        "(action = 'circle' AND user_id IN (%s))) ORDER BY id" % ",".join("?" * len(circle_users)),
        [since_utc, str(tg)] + circle_users).fetchall()


def chat_got(job, tg):
    return (job["action"] == "rec") or (str(tg) in payload_info(job)[1])


def missed_in(jobs, tg, start, end):
    """Circle jobs queued in [start, end) that no job ever gave this chat."""
    delivered = {
        payload_info(job)[0].get("recordUniqId") for job in jobs
        if chat_got(job, tg) and job["status"] != "failed"}
    missed = []
    for job in jobs:
        info = payload_info(job)[0]
        created = utc_to_local(job["created_at"])
        if job["action"] == "circle" and created is not None and start <= created < end \
                and not chat_got(job, tg) and info.get("recordUniqId") not in delivered:
            missed.append((job, info))
    return missed, delivered


def paid_on(conn, user_id, tg, day):
    """True if payment_history has a row for this user dated that day."""
    rows = conn.execute(
        "SELECT datetime FROM payment_history WHERE user_id IN (?, ?)",
        (str(user_id), str(tg))).fetchall()
    for row in rows:
        text = str(row["datetime"] or "")
        try:
            stamp = datetime.datetime.fromtimestamp(float(text))
        except ValueError:
            stamp = utc_to_local(text[:19])
        if stamp is not None and stamp.date() == day:
            return True
    return False


def audit(conn, out=print, now=None):
    now = datetime.datetime.now() if now is None else now
    tick = now.replace(minute=0, second=0, microsecond=0)
    rows = conn.execute(
        "SELECT u.id, u.telegramId, u.nosub_digest_sent_at AS sent, utc.time_left, "
        "d.created_at AS flagged FROM user_tariff_cs utc "
        "INNER JOIN users u ON u.id = utc.uid "
        "LEFT JOIN digest_outbox d ON d.user_telegram_id = u.telegramId "
        "WHERE utc.tariff_id > 0 AND utc.time_left > 0 AND u.deleted_at IS NULL "
        "ORDER BY utc.time_left DESC").fetchall()
    out("== Paying users whose period began since %s (server-local, +-1h)" % LOSSY_SINCE.date())
    counts = {}
    for row in rows:
        # old tick: renew 0 -> period, then -1; so time_left = period - 1 - hours since
        started = tick - datetime.timedelta(hours=config.tariff_period - 1 - row["time_left"])
        if started < LOSSY_SINCE:
            continue
        tg = row["telegramId"]
        marks = [t for t in (utc_to_local(row["flagged"]), utc_to_local(row["sent"])) if t]
        near = sorted(t for t in marks
                      if started - datetime.timedelta(hours=3) <= t < started + datetime.timedelta(hours=1))
        if near and paid_on(conn, row["id"], tg, started.date()):
            verdict = "flag, then a payment that day: probably bought after the digest"
        elif near:
            verdict = "GAP: flagged in the hour before renewal"
        elif now - started < OUTBOX_KEEP:
            verdict = "clean: no flag around renewal"
        else:
            verdict = "unknown: traces older than 7 days are purged"
        key = verdict.split(":")[0]
        counts[key] = counts.get(key, 0) + 1
        out("  %s  period from ~%s  flags %s  %s" % (
            tg, started.strftime("%Y-%m-%d %H:00"),
            [t.strftime("%m-%d %H:%M") for t in marks], verdict))
        if not verdict.startswith("GAP"):
            continue
        start = near[0].replace(minute=0, second=0)
        names = {r["channel_id"]: r["name"] for r in conn.execute(
            "SELECT ucc.channel_id, c.name FROM user_channel_cs ucc "
            "INNER JOIN channels c ON c.id = ucc.channel_id "
            "WHERE ucc.user_telegram_id = ?", (str(tg),)).fetchall()}
        if now - start > OUTBOX_KEEP:
            out("      outbox for that hour is purged; episodes unknown")
            continue
        jobs = load_jobs(conn, tg, names, local_to_utc_text(start - datetime.timedelta(days=2)))
        missed, _ = missed_in(jobs, tg, start, start + datetime.timedelta(hours=1, minutes=1))
        for _job, info in missed:
            out("      MISSED: #%s %s | %s | %s" % (
                info.get("id"), names.get(info.get("id"), ""), info.get("title"),
                info.get("pubDate")))
        if not missed:
            out("      no other payer got an episode then; run the per-chat report "
                "(logs keep 3 days)")
    out("  totals: %s" % counts)


def report(conn, tg, hour=None, out=print, work_dir=None):
    """One chat, one server-local hour (default: the hour of its last nosub digest)."""
    user = conn.execute(
        "SELECT * FROM users WHERE telegramId = ?", (str(tg),)).fetchone()
    if user is None:
        out("no user %s" % tg)
        return
    digest_sent = user["nosub_digest_sent_at"] if "nosub_digest_sent_at" in user.keys() else None
    if hour is not None:
        start = hour
    else:
        sent_local = utc_to_local(digest_sent)
        if sent_local is None:
            out("no nosub_digest_sent_at; pass the hour: YYYY-MM-DD HH")
            return
        start = sent_local.replace(minute=0, second=0)
    end = start + datetime.timedelta(hours=1, minutes=1)

    out("== Tariff now")
    tariff = conn.execute(
        "SELECT utc.*, t.price, t.level FROM user_tariff_cs utc "
        "LEFT JOIN tariffs t ON t.id = utc.tariff_id WHERE utc.uid = ?",
        (user["id"],)).fetchone()
    if tariff is None:
        out("  no user_tariff_cs row")
    else:
        stuck = (tariff["tariff_id"] or 0) > 0 and tariff["time_left"] == 0 \
            and tariff["price"] is not None and tariff["balance"] >= tariff["price"]
        out("  tariff_id=%s level=%s price=%s balance=%s time_left=%sh notify_count=%s%s" % (
            tariff["tariff_id"], tariff["level"], tariff["price"], tariff["balance"],
            tariff["time_left"], tariff["notify_count"],
            "  <-- paid but time_left = 0" if stuck else ""))

    out("\n== Paying users sitting at time_left = 0 (must be 0 after the first tick past the fix)")
    rows = conn.execute(
        "SELECT u.telegramId FROM user_tariff_cs utc "
        "INNER JOIN tariffs t ON t.id = utc.tariff_id "
        "INNER JOIN users u ON u.id = utc.uid "
        "WHERE utc.tariff_id > 0 AND utc.time_left = 0 "
        "AND utc.balance >= t.price AND u.deleted_at IS NULL").fetchall()
    out("  %d %s" % (len(rows), [r["telegramId"] for r in rows[:20]]))

    out("\n== Digest")
    out("  nosub_digest_sent_at: %s UTC = %s server-local" % (
        digest_sent, utc_to_local(digest_sent)))
    try:
        row = conn.execute(
            "SELECT * FROM digest_outbox WHERE user_telegram_id = ?", (tg,)).fetchone()
        out("  digest_outbox: %s" % (dict(row) if row else None))
    except sqlite3.OperationalError as e:
        out("  digest_outbox: %s" % e)

    subs = conn.execute(
        "SELECT ucc.channel_id, ucc.notify, ucc.last_guid, ucc.last_date, "
        "c.name, c.last_guid AS ch_guid, c.last_date AS ch_date "
        "FROM user_channel_cs ucc INNER JOIN channels c ON c.id = ucc.channel_id "
        "WHERE ucc.user_telegram_id = ? ORDER BY ucc.channel_id", (str(tg),)).fetchall()
    names = {s["channel_id"]: s["name"] for s in subs}
    out("\n== Subscriptions (%d); cursor = what the updater thinks this chat has" % len(subs))
    for s in subs:
        out("  #%s %s notify=%s%s\n      cursor:  %s\n      channel: %s" % (
            s["channel_id"], s["name"], s["notify"],
            "" if s["last_guid"] == s["ch_guid"] else "  <-- cursor != channel latest",
            short(s["last_guid"]), short(s["ch_guid"])))

    out("\n== Updater log, %s .. %s (server-local), this chat's podcasts" % (start, end))
    processed = set()
    previous_matched = False
    for _stamp, text in log_entries(start, end, work_dir=work_dir, out=out):
        ids = {int(x) for x in CHANNEL_IN_LOG.findall(text)} & set(names)
        if ids or (previous_matched and "ENQUEUED AUTOMATICALLY" in text):
            out("  " + text.replace("\n", "\n    "))
            if "Processig channel" in text:
                processed |= ids
        previous_matched = bool(ids)

    since = local_to_utc_text(start - datetime.timedelta(days=2))
    jobs = load_jobs(conn, tg, names, since)
    missed, delivered = missed_in(jobs, tg, start, end)

    out("\n== send_outbox for these podcasts since %s UTC" % since)
    queued_in_hour = set()
    for job in jobs:
        info, chats = payload_info(job)
        created = utc_to_local(job["created_at"])
        if job["action"] == "circle" and created is not None and start <= created < end:
            queued_in_hour.add(info.get("id"))
        mark = "got it" if chat_got(job, tg) else (
            "got it by another job" if info.get("recordUniqId") in delivered else "NOT this chat")
        out("  %s  %-6s %-7s #%s %s | %s | %s | %d chats | %s" % (
            created, job["action"], job["status"], info.get("id"),
            names.get(info.get("id"), ""), info.get("title"), info.get("pubDate"),
            len(chats), mark))

    out("\n== Verdict for %s .. %s" % (start, end))
    if missed:
        for job, info in missed:
            out("  MISSED: #%s %s | %s | %s\n          %s" % (
                info.get("id"), names.get(info.get("id"), ""), info.get("title"),
                info.get("pubDate"), payload_link(job)))
    else:
        out("  no circle job in that hour skipped this chat")
    for cid in sorted(processed - queued_in_hour):
        last = [j for j in jobs if payload_info(j)[0].get("id") == cid and chat_got(j, tg)]
        last_uid = payload_info(last[-1])[0].get("recordUniqId") if last else None
        channel_latest = next(s["ch_guid"] for s in subs if s["channel_id"] == cid)
        out("  processed, no circle job: #%s %s\n      podcast latest:    %s\n"
            "      last sent to chat: %s%s" % (
                cid, names[cid], short(channel_latest), short(last_uid),
                "" if last_uid == channel_latest else "  <-- check this one"))


def as_text(run, *args, **kwargs):
    """Run report/audit and return what it printed."""
    lines = []
    run(*args, out=lines.append, **kwargs)
    return "\n".join(lines) + "\n"
