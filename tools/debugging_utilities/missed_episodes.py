# -*- coding: utf-8 -*-
"""Which episodes a chat missed in one hour. Read-only: DB and logs.

Run on the server from the repo root:

    venv/bin/python tools/debugging_utilities/missed_episodes.py <telegram_id> [YYYY-MM-DD HH]

The hour is server-local, like the logs. Without it the hour of the chat's
last nosub digest is used (users.nosub_digest_sent_at is UTC).

An episode is reported missed when a circle job for one of the chat's
podcasts was queued in that hour for other listeners, and neither that
job nor any rec job gave it to this chat. Podcasts the updater processed
in that hour without a circle job are listed too: if the chat is their
only paying listener, there is no job to compare, so compare the chat's
last delivered episode with the podcast's latest by eye.
"""
import datetime
import json
import os
import re
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config  # noqa: E402

LOG_ENTRY = re.compile(r"^\[(\d\d:\d\d:\d\d \d\d\.\d\d\.\d\d\d\d)\] ")
CHANNEL_IN_LOG = re.compile(
    r"(?:Processig channel|Channel id:|for channel) (\d+)")


def connect_ro(path):
    conn = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
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
    aware = value.astimezone()  # naive -> server local
    return aware.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def log_entries(start, end):
    """Updater log entries (with continuation lines) in [start, end)."""
    day = start.date()
    while day <= end.date():
        path = os.path.join(
            config.work_dir, "log", "updater_%s.log" % day.strftime("%d_%m_%Y"))
        if not os.path.exists(path):
            print("  (no log file %s)" % path)
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


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    tg = int(sys.argv[1])
    conn = connect_ro(config.db_path)

    user = conn.execute(
        "SELECT * FROM users WHERE telegramId = ?", (str(tg),)).fetchone()
    if user is None:
        print("no user", tg)
        sys.exit(1)
    keys = user.keys()
    digest_sent = user["nosub_digest_sent_at"] if "nosub_digest_sent_at" in keys else None

    if len(sys.argv) >= 3:
        start = datetime.datetime.strptime(" ".join(sys.argv[2:4]), "%Y-%m-%d %H")
    else:
        sent_local = utc_to_local(digest_sent)
        if sent_local is None:
            print("no nosub_digest_sent_at; pass the hour: YYYY-MM-DD HH")
            sys.exit(2)
        start = sent_local.replace(minute=0, second=0)
    end = start + datetime.timedelta(hours=1, minutes=1)

    print("== Tariff now")
    tariff = conn.execute(
        "SELECT utc.*, t.price, t.level FROM user_tariff_cs utc "
        "LEFT JOIN tariffs t ON t.id = utc.tariff_id WHERE utc.uid = ?",
        (user["id"],)).fetchone()
    if tariff is None:
        print("  no user_tariff_cs row")
    else:
        stuck = (tariff["tariff_id"] or 0) > 0 and tariff["time_left"] == 0 \
            and tariff["price"] is not None and tariff["balance"] >= tariff["price"]
        print("  tariff_id=%s level=%s price=%s balance=%s time_left=%sh notify_count=%s%s" % (
            tariff["tariff_id"], tariff["level"], tariff["price"], tariff["balance"],
            tariff["time_left"], tariff["notify_count"],
            "  <-- paid but time_left = 0" if stuck else ""))

    print("\n== Paying users sitting at time_left = 0 (must be 0 after the first tick past the fix)")
    rows = conn.execute(
        "SELECT u.telegramId FROM user_tariff_cs utc "
        "INNER JOIN tariffs t ON t.id = utc.tariff_id "
        "INNER JOIN users u ON u.id = utc.uid "
        "WHERE utc.tariff_id > 0 AND utc.time_left = 0 "
        "AND utc.balance >= t.price AND u.deleted_at IS NULL").fetchall()
    print("  %d %s" % (len(rows), [r["telegramId"] for r in rows[:20]]))

    print("\n== Digest")
    print("  nosub_digest_sent_at: %s UTC = %s server-local" % (
        digest_sent, utc_to_local(digest_sent)))
    try:
        row = conn.execute(
            "SELECT * FROM digest_outbox WHERE user_telegram_id = ?", (tg,)).fetchone()
        print("  digest_outbox: %s" % (dict(row) if row else None))
    except sqlite3.OperationalError as e:
        print("  digest_outbox: %s" % e)

    subs = conn.execute(
        "SELECT ucc.channel_id, ucc.notify, ucc.last_guid, ucc.last_date, "
        "c.name, c.last_guid AS ch_guid, c.last_date AS ch_date "
        "FROM user_channel_cs ucc INNER JOIN channels c ON c.id = ucc.channel_id "
        "WHERE ucc.user_telegram_id = ? ORDER BY ucc.channel_id", (str(tg),)).fetchall()
    names = {s["channel_id"]: s["name"] for s in subs}
    print("\n== Subscriptions (%d); cursor = what the updater thinks this chat has" % len(subs))
    for s in subs:
        print("  #%s %s notify=%s%s\n      cursor:  %s\n      channel: %s" % (
            s["channel_id"], s["name"], s["notify"],
            "" if s["last_guid"] == s["ch_guid"] else "  <-- cursor != channel latest",
            short(s["last_guid"]), short(s["ch_guid"])))

    print("\n== Updater log, %s .. %s (server-local), this chat's podcasts" % (start, end))
    processed = set()
    previous_matched = False
    for stamp, text in log_entries(start, end):
        ids = {int(x) for x in CHANNEL_IN_LOG.findall(text)} & set(names)
        if ids or (previous_matched and "ENQUEUED AUTOMATICALLY" in text):
            print("  " + text.replace("\n", "\n    "))
            if "Processig channel" in text:
                processed |= ids
        previous_matched = bool(ids)

    since = local_to_utc_text(start - datetime.timedelta(days=2))
    circle_users = ["c%s" % cid for cid in names]
    jobs = conn.execute(
        "SELECT id, created_at, action, user_id, payload_json, status FROM send_outbox "
        "WHERE created_at >= ? AND ((action = 'rec' AND user_id = ?) OR "
        "(action = 'circle' AND user_id IN (%s))) ORDER BY id" % ",".join("?" * len(circle_users)),
        [since, str(tg)] + circle_users).fetchall()

    delivered = {}
    for job in jobs:
        info, chats = payload_info(job)
        got = (job["action"] == "rec") or (str(tg) in chats)
        if got and job["status"] != "failed":
            delivered[info.get("recordUniqId")] = job

    print("\n== send_outbox for these podcasts since %s UTC" % since)
    missed = []
    queued_in_hour = set()
    for job in jobs:
        info, chats = payload_info(job)
        created = utc_to_local(job["created_at"])
        uid = info.get("recordUniqId")
        got = (job["action"] == "rec") or (str(tg) in chats)
        in_hour = created is not None and start <= created < end
        if in_hour and job["action"] == "circle":
            queued_in_hour.add(info.get("id"))
        mark = "got it" if got else ("got it by another job" if uid in delivered else "NOT this chat")
        print("  %s  %-6s %-7s #%s %s | %s | %s | %d chats | %s" % (
            created, job["action"], job["status"], info.get("id"),
            names.get(info.get("id"), ""), info.get("title"), info.get("pubDate"),
            len(chats), mark))
        if in_hour and not got and uid not in delivered:
            missed.append((job, info))

    print("\n== Verdict for %s .. %s" % (start, end))
    if missed:
        for job, info in missed:
            print("  MISSED: #%s %s | %s | %s\n          %s" % (
                info.get("id"), names.get(info.get("id"), ""), info.get("title"),
                info.get("pubDate"), json.loads(job["payload_json"]).get(
                    "func_params", {}).get("link")))
    else:
        print("  no circle job in that hour skipped this chat")
    for cid in sorted(processed - queued_in_hour):
        last = [j for j in jobs if payload_info(j)[0].get("id") == cid
                and ((j["action"] == "rec") or str(tg) in payload_info(j)[1])]
        last_uid = payload_info(last[-1])[0].get("recordUniqId") if last else None
        channel_latest = next(s["ch_guid"] for s in subs if s["channel_id"] == cid)
        print("  processed, no circle job: #%s %s\n      podcast latest:    %s\n"
              "      last sent to chat: %s%s" % (
                  cid, names[cid], short(channel_latest), short(last_uid),
                  "" if last_uid == channel_latest else "  <-- check this one"))


if __name__ == "__main__":
    main()
