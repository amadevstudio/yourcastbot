# -*- coding: utf-8 -*-
"""Read-only "which episodes did a chat miss" reports. DB and updater logs.

Served by GET /api/diag/* (admin API, separate read-only token). Nothing
here writes: the DB is opened with mode=ro.

Who got an episode comes from the updater log, not from send_outbox: the
sender rewrites a circle row's chat_ids to the chats still waiting, so a
done row lists nobody. The log line "Sending automatically ... to {...}"
is written when the episode is queued and names every recipient. Logs keep
3 days; rec rows (a chat tapped an episode) keep their chat for 7.

report(): one chat and one server-local hour. An episode is missed when it
was queued in that hour for other chats of a podcast this chat follows with
notifications on, and no queue line in the kept logs nor a rec row gave it
to this chat. Podcasts processed in that hour without a send are listed
with dates: if the chat is their only payer there is nobody to compare with.

audit(): paying users whose current period began since LOSSY_SINCE. Until
3c52606 every renewal left a payer an hour at time_left = 0, and since
7830e35 a nosub flag in that hour moves the cursor past the new episode.
New users start on the welcome Relay (tariff_new_user_period), not on a
renewal, and registration writes nosub_digest_sent_at: neither is a gap.

refetches(): full refetches after a 304 (paid_targets_behind), per channel.
One per feed version is expected; more means the guard is not working.

feed_probe(): GET a channel's stored feed as the updater does and show the
XML the parser sees (what rss.__parse_rss_root took and now takes as the
channel, the items it finds). The only diag call that touches the network; no writes.

DB timestamps are UTC; logs and the reported hours are server-local.
"""
import ast
import datetime
import hmac
import json
import os
import re
import sqlite3

import config

LOSSY_SINCE = datetime.datetime(2026, 9, 3)  # 7830e35: the nosub flag moves the cursor
OUTBOX_KEEP = datetime.timedelta(days=7)
LOG_KEEP = datetime.timedelta(days=3)
MIN_TOKEN_LENGTH = 32

LOG_ENTRY = re.compile(r"^\[(\d\d:\d\d:\d\d \d\d\.\d\d\.\d\d\d\d)\] ")
CHANNEL_IN_LOG = re.compile(
    r"(?:Processig channel|Channel id:|for channel) (\d+)")
SENDING = re.compile(r"Sending automatically\.\.\.\s+(b(['\"]).*\2)\s*$", re.S)
SENDING_HEAD = re.compile(r"Channel id: (\d+), '(.*)' \(itunes id:", re.S)
REFETCH = re.compile(
    r"Feed not modified for channel (\d+) ; paid listeners behind: \[([^\]]*)\] ; refetching")


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


def payload_info(row):
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except (TypeError, ValueError):
        payload = {}
    params = payload.get("func_params", payload) or {}
    info = params.get("podcastInfo") or {}
    chats = {str(chat) for chat in (params.get("chat_ids") or {})}
    return info, chats


def _quiet(*_args):
    pass


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


def parse_sending(text):
    """(channel_id, title, recipient ids as str) from a 'Sending automatically' entry."""
    match = SENDING.search(text)
    if not match:
        return None
    try:
        body = ast.literal_eval(match.group(1)).decode("utf-8", "replace")
    except (ValueError, SyntaxError, AttributeError):
        return None
    head, sep, rest = body.partition(" to {")
    head_match = SENDING_HEAD.match(head)
    if not sep or not head_match:
        return None
    try:
        recipients = ast.literal_eval("{" + rest.split(" ___ link: ", 1)[0])
    except (ValueError, SyntaxError):
        return None
    if not isinstance(recipients, dict):
        return None
    return int(head_match.group(1)), head_match.group(2), {str(k) for k in recipients}


def sends(channel_ids, start, end, work_dir=None):
    """Episodes queued for these podcasts in [start, end), from the updater log."""
    found = []
    wanted = set(channel_ids)
    for stamp, text in log_entries(start, end, work_dir=work_dir, out=_quiet):
        parsed = parse_sending(text)
        if parsed and parsed[0] in wanted:
            found.append({"stamp": stamp, "channel": parsed[0], "title": parsed[1],
                          "chats": parsed[2]})
    return found


def rec_titles(conn, tg, since_utc):
    """(channel id, title) of episodes this chat tapped (rec rows keep the chat)."""
    rows = conn.execute(
        "SELECT payload_json FROM send_outbox WHERE action = 'rec' AND user_id = ? "
        "AND created_at >= ? AND status != 'failed'", (str(tg), since_utc)).fetchall()
    return {(payload_info(r)[0].get("id"), payload_info(r)[0].get("title")) for r in rows}


def missed_in(conn, tg, channel_ids, start, end, now=None, work_dir=None):
    """Episodes queued in [start, end) for others and never for this chat.

    Returns (missed, in_window) or (None, None) when that hour's log is gone.
    """
    now = datetime.datetime.now() if now is None else now
    if now - start > LOG_KEEP:
        return None, None
    kept = sends(channel_ids, now - LOG_KEEP, now + datetime.timedelta(minutes=1),
                 work_dir=work_dir)
    got = {(s["channel"], s["title"]) for s in kept if str(tg) in s["chats"]}
    got |= rec_titles(conn, tg, local_to_utc_text(now - OUTBOX_KEEP))
    in_window = [s for s in kept if start <= s["stamp"] < end]
    missed = [s for s in in_window
              if str(tg) not in s["chats"] and (s["channel"], s["title"]) not in got]
    return missed, in_window


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


def period_start(tick, time_left, period):
    """Local start of a period of `period` hours that has time_left left now."""
    # old tick: grant/renew, then -1 at the next tick; +-1 h either way
    return tick - datetime.timedelta(hours=period - 1 - time_left)


def audit(conn, out=print, now=None, work_dir=None):
    now = datetime.datetime.now() if now is None else now
    tick = now.replace(minute=0, second=0, microsecond=0)
    near_hours = datetime.timedelta(hours=2)
    rows = conn.execute(
        "SELECT u.id, u.telegramId, u.created_at, u.nosub_digest_sent_at AS sent, "
        "utc.time_left, d.created_at AS flagged FROM user_tariff_cs utc "
        "INNER JOIN users u ON u.id = utc.uid "
        "LEFT JOIN digest_outbox d ON d.user_telegram_id = u.telegramId "
        "WHERE utc.tariff_id > 0 AND utc.time_left > 0 AND u.deleted_at IS NULL "
        "ORDER BY utc.time_left DESC").fetchall()
    out("== Paying users whose period began since %s (server-local, +-1h)" % LOSSY_SINCE.date())
    counts = {}

    def count(key):
        counts[key] = counts.get(key, 0) + 1

    for row in rows:
        tg = row["telegramId"]
        created = utc_to_local(row["created_at"])
        trial = None
        for period in (config.tariff_new_user_period, config.tariff_secret_start_cmd_period):
            start = period_start(tick, row["time_left"], period)
            if created is not None and abs(start - created) <= near_hours:
                trial = (period, start)
        if trial is not None:
            count("welcome")
            out("  %s  welcome Relay (%dh) from %s: no renewal yet" % (
                tg, trial[0], created.strftime("%Y-%m-%d %H:%M")))
            continue
        started = period_start(tick, row["time_left"], config.tariff_period)
        if started < LOSSY_SINCE:
            continue
        # registration writes nosub_digest_sent_at: that is not a digest
        marks = [t for t in (utc_to_local(row["flagged"]), utc_to_local(row["sent"]))
                 if t and not (created and abs(t - created) <= datetime.timedelta(minutes=5))]
        near = sorted(t for t in marks
                      if started - datetime.timedelta(hours=3) <= t < started + datetime.timedelta(hours=1))
        if near and paid_on(conn, row["id"], tg, started.date()):
            verdict = "bought: flag, then a payment that day (they were free: by design)"
        elif near:
            verdict = "GAP: flagged in the hour before renewal"
        elif now - started < OUTBOX_KEEP:
            verdict = "clean: no flag around renewal"
        else:
            verdict = "unknown: flags older than 7 days are purged"
        count(verdict.split(":")[0])
        out("  %s  period from ~%s  flags %s  %s" % (
            tg, started.strftime("%Y-%m-%d %H:00"),
            [t.strftime("%m-%d %H:%M") for t in marks], verdict))
        if not verdict.startswith("GAP"):
            continue
        names = followed(conn, tg)
        hour = near[0].replace(minute=0, second=0)
        missed, _ = missed_in(conn, tg, names, hour, hour + datetime.timedelta(hours=1, minutes=1),
                              now=now, work_dir=work_dir)
        if missed is None:
            out("      log of that hour is purged (3 days); episodes unknown")
            continue
        for item in missed:
            out("      MISSED: #%s %s | %s | queued %s for %d chats" % (
                item["channel"], names.get(item["channel"], ""), item["title"],
                item["stamp"].strftime("%m-%d %H:%M"), len(item["chats"])))
        if not missed:
            out("      nobody else got an episode of its podcasts then; see the per-chat report")
    out("  totals: %s" % counts)


def followed(conn, tg):
    """{channel_id: name} this chat follows with notifications on."""
    return {r["channel_id"]: r["name"] for r in conn.execute(
        "SELECT ucc.channel_id, c.name FROM user_channel_cs ucc "
        "INNER JOIN channels c ON c.id = ucc.channel_id "
        "WHERE ucc.user_telegram_id = ? AND ucc.notify = 1", (str(tg),)).fetchall()}


def report(conn, tg, hour=None, out=print, work_dir=None, now=None):
    """One chat, one server-local hour (default: the hour of its last nosub digest)."""
    now = datetime.datetime.now() if now is None else now
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
    out("  nosub_digest_sent_at: %s UTC = %s server-local (registration writes it too)" % (
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
    on = [s for s in subs if s["notify"] == 1]
    names = {s["channel_id"]: s["name"] for s in on}
    out("\n== Subscriptions: %d, with notifications %d (cursor = what the updater "
        "thinks this chat has; channel = latest the bot saw)" % (len(subs), len(on)))
    for s in on:
        out("  #%s %s%s\n      cursor:  %s | %s\n      channel: %s | %s" % (
            s["channel_id"], s["name"],
            "" if s["last_guid"] == s["ch_guid"] else "  <-- cursor != channel latest",
            s["last_date"], s["last_guid"], s["ch_date"], s["ch_guid"]))

    out("\n== Updater log, %s .. %s (server-local), podcasts with notifications" % (start, end))
    processed = set()
    for _stamp, text in log_entries(start, end, work_dir=work_dir, out=out):
        ids = {int(x) for x in CHANNEL_IN_LOG.findall(text)} & set(names)
        if not ids:
            continue
        parsed = parse_sending(text)
        if parsed:
            out("  [%s] SENT #%s '%s' to %d chats, this chat %s" % (
                _stamp.strftime("%H:%M:%S"), parsed[0], parsed[1], len(parsed[2]),
                "INCLUDED" if str(tg) in parsed[2] else "not included"))
        else:
            out("  " + text.replace("\n", "\n    "))
        if "Processig channel" in text:
            processed |= ids

    out("\n== Verdict for %s .. %s" % (start, end))
    missed, in_window = missed_in(conn, tg, names, start, end, now=now, work_dir=work_dir)
    if missed is None:
        out("  log of that hour is purged (logs keep 3 days): cannot tell")
    else:
        for item in missed:
            out("  MISSED: #%s %s | %s | queued %s for %d other chats, never for this one" % (
                item["channel"], names.get(item["channel"], ""), item["title"],
                item["stamp"].strftime("%H:%M"), len(item["chats"])))
        if not missed:
            out("  no episode of these podcasts was queued for others and not for this chat")
        sent_channels = {item["channel"] for item in in_window}
        by_id = {s["channel_id"]: s for s in on}
        for cid in sorted(processed - sent_channels):
            s = by_id[cid]
            out("  processed, nothing sent: #%s %s | channel latest %s | cursor %s" % (
                cid, s["name"], s["ch_date"], s["last_date"]))

    since = local_to_utc_text(now - OUTBOX_KEEP)
    out("\n== Taps (rec rows keep the chat for 7 days)")
    for row in conn.execute(
            "SELECT created_at, status, payload_json FROM send_outbox "
            "WHERE action = 'rec' AND user_id = ? AND created_at >= ? ORDER BY id",
            (str(tg), since)).fetchall():
        info = payload_info(row)[0]
        out("  %s %-7s #%s %s | %s" % (
            utc_to_local(row["created_at"]), row["status"], info.get("id"),
            info.get("title"), info.get("pubDate")))


def refetches(conn, out=print, hours=24, now=None, work_dir=None):
    """Full refetches after a 304 per channel. One per feed version is expected."""
    now = datetime.datetime.now() if now is None else now
    start = now - datetime.timedelta(hours=hours)
    seen = {}
    for stamp, text in log_entries(start, now + datetime.timedelta(minutes=1),
                                   work_dir=work_dir, out=_quiet):
        match = REFETCH.search(text)
        if not match:
            continue
        cid = int(match.group(1))
        behind = len([x for x in match.group(2).split(",") if x.strip()])
        item = seen.setdefault(cid, {"count": 0, "first": stamp, "behind": behind})
        item["count"] += 1
        item["last"] = stamp
        item["behind"] = behind
    out("== Full refetches after 304, last %dh (server-local); >1 per channel "
        "without a new feed version means the guard is off" % hours)
    for cid, item in sorted(seen.items(), key=lambda kv: -kv[1]["count"]):
        row = conn.execute("SELECT name FROM channels WHERE id = ?", (cid,)).fetchone()
        out("  #%s %s: %d refetches, %s .. %s, %d payers behind" % (
            cid, row["name"] if row else "", item["count"],
            item["first"].strftime("%m-%d %H:%M"), item["last"].strftime("%m-%d %H:%M"),
            item["behind"]))
    out("  totals: %d channels, %d refetches" % (
        len(seen), sum(item["count"] for item in seen.values())))


def _node_kind(node):
    from lxml import etree
    if node.tag is etree.Comment:
        return "comment %r" % (node.text or "").strip()[:80]
    if node.tag is etree.PI:
        return "processing instruction %r" % str(node)[:80]
    return "element %s" % node.tag


def _local(node):
    from lxml import etree
    return etree.QName(node).localname if isinstance(node.tag, str) else None


def digest_stats(conn, out=print, hours=6, now=None):
    """Nosub digests queued/sent in the last hours, and empty cursors left.

    A wave of "new episodes are out" shows here first. Registration writes
    nosub_digest_sent_at too; those rows (equal to created_at) are not sends.
    """
    now = datetime.datetime.now() if now is None else now
    since = local_to_utc_text(now - datetime.timedelta(hours=hours))
    since_sql = since.replace("T", " ").rstrip("Z")
    out("== Nosub digests, last %dh (since %s UTC)" % (hours, since))
    try:
        rows = conn.execute(
            "SELECT status, count(*) AS n FROM digest_outbox WHERE created_at >= ? "
            "GROUP BY status", (since,)).fetchall()
        out("  queued (digest_outbox by status): %s" % {r["status"]: r["n"] for r in rows})
    except sqlite3.OperationalError as e:
        out("  digest_outbox: %s" % e)
    sent = conn.execute(
        "SELECT count(*) FROM users WHERE nosub_digest_sent_at >= ? "
        "AND (created_at IS NULL OR nosub_digest_sent_at != created_at)",
        (since_sql,)).fetchone()[0]
    out("  sent (users.nosub_digest_sent_at, registrations excluded): %d" % sent)
    rows = conn.execute(
        "SELECT ucc.channel_id, c.name, count(*) AS n FROM user_channel_cs ucc "
        "INNER JOIN channels c ON c.id = ucc.channel_id WHERE ucc.notify = 1 "
        "AND (ucc.last_guid IS NULL OR ucc.last_guid IN ('__', '', 'None')) "
        "GROUP BY ucc.channel_id ORDER BY n DESC").fetchall()
    out("\n== Empty cursors (\"__\") with notifications left: %d on %d channels" % (
        sum(r["n"] for r in rows), len(rows)))
    for r in rows[:10]:
        out("  #%s %s: %d" % (r["channel_id"], r["name"], r["n"]))


def outbox_stats(conn, out=print, hours=6, now=None):
    """send_outbox per pool: is each one draining? Aggregates only, no chats.

    pending and leased rows stay until a worker handles them: an old pending
    row, or a lease past leased_until, means a pool is stuck. Rows are
    counted by created_at (no completion time is stored).
    """
    now = datetime.datetime.now() if now is None else now
    now_utc = local_to_utc_text(now)
    since = local_to_utc_text(now - datetime.timedelta(hours=hours))
    out("== send_outbox rows created in the last %dh (since %s UTC), by status" % (
        hours, since))
    created = {}
    try:
        rows = conn.execute(
            "SELECT action, status, count(*) AS n FROM send_outbox "
            "WHERE created_at >= ? GROUP BY action, status ORDER BY action, status",
            (since,)).fetchall()
    except sqlite3.OperationalError as e:
        out("  send_outbox: %s" % e)
        return
    for r in rows:
        created.setdefault(r["action"], {})[r["status"]] = r["n"]
    for action in sorted(created):
        out("  %-6s %s" % (action, created[action]))
    if not created:
        out("  none")
    out("\n== Open rows (pending, leased), any age")
    rows = conn.execute(
        "SELECT action, status, count(*) AS n, min(created_at) AS oldest, "
        "max(attempts) AS attempts, "
        "sum(CASE WHEN status = 'pending' AND available_at > ? THEN 1 ELSE 0 END) "
        "AS backoff, "
        "sum(CASE WHEN status = 'leased' AND leased_until <= ? THEN 1 ELSE 0 END) "
        "AS expired "
        "FROM send_outbox WHERE status IN ('pending', 'leased') "
        "GROUP BY action, status ORDER BY action, status",
        (now_utc, now_utc)).fetchall()
    if not rows:
        out("  none: every pool is drained")
    for r in rows:
        oldest = utc_to_local(r["oldest"])
        line = "  %-6s %-7s %d, oldest created %s, max attempts %s" % (
            r["action"], r["status"], r["n"],
            oldest.strftime("%m-%d %H:%M") if oldest else r["oldest"], r["attempts"])
        if r["backoff"]:
            line += ", %d waiting for their retry time" % r["backoff"]
        if r["expired"]:
            line += ", %d with an expired lease (no worker renews it)" % r["expired"]
        out(line)


def _describe_feed(url, get, out):
    """GET url as the updater does (no validators) and show what it parses."""
    from lxml import etree
    try:
        response = get(url)
    except Exception as e:
        out("  GET failed: %s" % e)
        return
    redirects = [r.url for r in getattr(response, "history", [])]
    out("  HTTP %s, final URL %s, %s, %d bytes%s" % (
        response.status_code, response.url, response.headers.get("Content-Type"),
        len(response.content or b""), ", redirects %s" % redirects if redirects else ""))
    try:
        doc = etree.fromstring(response.content)
    except Exception as e:
        out("  not XML: %s; starts with %r" % (e, (response.content or b"")[:120]))
        return
    out("  root %s; its children in order:" % doc.tag)
    children = list(doc)
    for index, node in enumerate(children[:8]):
        out("    [%d] %s" % (index, _node_kind(node)))
    if not children:
        out("    (none)")
        return
    from app.service.podcast.feed_xml import channel_element
    old_pick = children[0]
    out("  before the fix, the updater took [0] as the channel: %s, items %d" % (
        _node_kind(old_pick), sum(1 for c in old_pick if c.tag == "item")))
    picked = channel_element(doc)
    out("  the updater now takes (feed_xml.channel_element): %s, items %d" % (
        "nothing" if picked is None else _node_kind(picked),
        0 if picked is None else sum(1 for c in picked if c.tag == "item")))
    channel = next((c for c in children if _local(c) == "channel"), None)
    if channel is None:
        out("  no <channel> element under the root")
        return
    items = [c for c in channel if _local(c) == "item"]
    title = next((c.text for c in channel if c.tag == "title"), None)
    out("  real <channel> at [%d]: tag %s, title %r, items %d (plain 'item' tags %d)" % (
        children.index(channel), channel.tag, title, len(items),
        sum(1 for c in items if c.tag == "item")))
    if items:
        fields = {c.tag: (c.attrib.get("url") if c.tag == "enclosure" else c.text)
                  for c in items[0] if c.tag in ("guid", "title", "pubDate", "enclosure")}
        out("  newest item as the updater reads its fields: %r" % fields)
        out("  newest item child tags: %s" % sorted({str(c.tag) for c in items[0]})[:15])


def feed_probe(conn, channel_id, out=print, get=None, itunes=None):
    """Fetch a channel's feed as the updater does; say why it parses or not.

    Read-only: a GET of the URL stored for the channel (and of the one
    iTunes lists for it, when it differs); nothing is written.
    """
    from app.service.podcast import rss
    if get is None:
        def get(url):
            return rss.feed_requester.get(url, timeout=rss.FEED_REQUEST_TIMEOUT)
    if itunes is None:
        def itunes(itunes_id):
            response = rss.requester.get(
                "https://itunes.apple.com/lookup",
                params={"entity": "podcast", "id": itunes_id}, timeout=(5, 10))
            for result in response.json().get("results", []):
                if result.get("feedUrl"):
                    return result["feedUrl"]
            return None
    row = conn.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    if row is None:
        out("no channel %s" % channel_id)
        return
    keys = row.keys()
    listeners = conn.execute(
        "SELECT count(*) FROM user_channel_cs WHERE channel_id = ? AND notify = 1",
        (channel_id,)).fetchone()[0]
    out("== Channel #%s %s (%d listeners with notifications)" % (row["id"], row["name"], listeners))
    out("  stored latest: %r | %r" % (row["last_guid"], row["last_date"]))
    if "http_etag" in keys:
        out("  stored validators: etag %r, last_modified %r" % (
            row["http_etag"], row["http_last_modified"]))
    rss_link = row["rss_link"] if "rss_link" in keys else None
    out("  rss_link: %s" % rss_link)
    itunes_url = None
    if row["itunes_id"]:
        try:
            itunes_url = itunes(row["itunes_id"])
        except Exception as e:
            out("  iTunes lookup failed: %s" % e)
        out("  iTunes feedUrl for %s: %s" % (row["itunes_id"], itunes_url))
    if rss_link:
        out("\n== rss_link, as the updater fetches it")
        _describe_feed(rss_link, get, out)
    if itunes_url and itunes_url.rstrip("/").split("://")[-1] != (rss_link or "").rstrip("/").split("://")[-1]:
        out("\n== iTunes feedUrl (differs from rss_link)")
        _describe_feed(itunes_url, get, out)

    rows = conn.execute(
        "SELECT c.id, c.name, count(ucc.id) AS listeners FROM channels c "
        "INNER JOIN user_channel_cs ucc ON ucc.channel_id = c.id AND ucc.notify = 1 "
        "WHERE c.last_guid IS NULL OR c.last_guid IN ('__', '', 'None') "
        "GROUP BY c.id ORDER BY listeners DESC").fetchall()
    out("\n== Channels with notifications whose latest id is empty: %d" % len(rows))
    for r in rows[:20]:
        out("  #%s %s: %d listeners" % (r["id"], r["name"], r["listeners"]))


def as_text(run, *args, **kwargs):
    """Run report/audit/refetches and return what it printed."""
    lines = []
    run(*args, out=lines.append, **kwargs)
    return "\n".join(lines) + "\n"
