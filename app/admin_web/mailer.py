# -*- coding: utf-8 -*-
"""Admin broadcast worker. Own thread in the jobs role — not rec/circle/send."""
from __future__ import annotations

import json
import time
from typing import Callable, Optional

import config
from app.admin_web import mail_jobs
from db.sqliteAdapter import SQLighter
from lib.tools.logger import logger

SEND_BATCH_SIZE = 50
SEND_BATCH_SLEEP_SECONDS = 1
FLOOD_RETRIES = 5

SendFn = Callable[[int, str, str, list, str], tuple[bool, Optional[str]]]


def _db_path(database=None):
    return config.db_path if database is None else database


def is_channel_identifier(tgid) -> bool:
    try:
        return str(int(tgid)).startswith("-100")
    except Exception:
        return False


def mailer_loop(database=None, send_fn: Optional[SendFn] = None, stop_after: int = 0):
    mail_jobs.recover_interrupted(database=database)
    processed = 0
    while True:
        try:
            job = mail_jobs.claim_next(database=database)
            if job is None:
                if stop_after:
                    return
                time.sleep(1)
                continue
            process_job(job, database=database, send_fn=send_fn)
            processed += 1
            if stop_after and processed >= stop_after:
                return
        except Exception as e:
            logger.err("admin mailer loop:", e)
            if stop_after:
                raise
            time.sleep(2)


def process_job(job: dict, database=None, send_fn: Optional[SendFn] = None):
    job_id = int(job["id"])
    send = send_fn or telegram_send
    recipients = _frozen_recipients(job, database=database)
    mail_jobs.update_progress(job_id, total=len(recipients), database=database)
    parse_mode = job.get("parse_mode") or ""
    attachment_type = job.get("attachment_type") or ""
    attachments = job.get("attachments") or []
    message = job.get("message") or ""
    cursor = int(job.get("cursor_index") or 0)
    sent = int(job.get("sent") or 0)
    failed = int(job.get("failed") or 0)
    skipped = int(job.get("skipped") or 0)

    if cursor <= 0:
        send(config.creatorId, "Start sending messages to %s" % len(recipients),
             "", [], "")

    file_ids = []
    if send_fn is None and attachments and attachment_type:
        file_ids = _cache_file_ids(attachments, attachment_type)

    i = cursor
    while i < len(recipients):
        if mail_jobs.is_cancel_requested(job_id, database=database):
            mail_jobs.update_progress(
                job_id, sent=sent, failed=failed, skipped=skipped,
                cursor_index=i, last_error="paused", database=database)
            mail_jobs.finish(
                job_id, mail_jobs.STATUS_PAUSED, "paused", database=database)
            return
        if (i + 1) % SEND_BATCH_SIZE == 0:
            time.sleep(SEND_BATCH_SLEEP_SECONDS)
        tgid = recipients[i]
        if is_channel_identifier(tgid):
            skipped += 1
            mail_jobs.record_event(
                job_id, tgid, "skipped", database=database)
        else:
            if send_fn is None and file_ids:
                ok, error = telegram_send(
                    int(tgid), message, parse_mode, attachments,
                    attachment_type, file_ids=file_ids)
            else:
                ok, error = send(
                    int(tgid), message, parse_mode, attachments, attachment_type)
            if ok:
                sent += 1
                mail_jobs.record_event(job_id, tgid, "sent", database=database)
            else:
                failed += 1
                mail_jobs.record_event(
                    job_id, tgid, "failed", error, database=database)
                mail_jobs.update_progress(
                    job_id, last_error=error, database=database)
        i += 1
        mail_jobs.update_progress(
            job_id, sent=sent, failed=failed, skipped=skipped,
            cursor_index=i, database=database)

    mail_jobs.update_progress(
        job_id, sent=sent, failed=failed, skipped=skipped,
        cursor_index=i, database=database)
    mail_jobs.finish(job_id, mail_jobs.STATUS_DONE, database=database)
    send(
        config.creatorId,
        "All messages sent. Sent: %s. Failed: %s. Skipped channels: %s."
        % (sent, failed, skipped),
        "", [], "")
    logger.log(
        "admin mail job", job_id, "done sent", sent, "failed", failed,
        "skipped", skipped)


def _frozen_recipients(job: dict, database=None) -> list:
    raw = job.get("recipients_json") or "[]"
    if not isinstance(raw, str):
        raw = json.dumps(raw)
    try:
        items = json.loads(raw)
    except ValueError:
        items = []
    if items:
        return [str(x) for x in items]
    built = _recipients(job, database=database)
    mail_jobs.set_recipients(job["id"], built, database=database)
    return [str(x) for x in built]


def _recipients(job: dict, database=None) -> list:
    if job.get("to_creator_only"):
        return [config.creatorId]
    raw = (job.get("recipients_text") or "").strip()
    if raw:
        items = []
        for part in raw.split(","):
            part = part.strip()
            if part:
                items.append(part)
        return items
    language = job.get("language") or None
    if language == "":
        language = None
    db = SQLighter(_db_path(database))
    try:
        users = db.get_all_users(language=language)
    finally:
        db.close()
    return [u["telegramId"] for u in users]


def _cache_file_ids(attachments: list, attachment_type: str) -> list:
    ids = []
    bot = _bot()
    for item in attachments:
        path = item["path"] if isinstance(item, dict) else item
        try:
            with open(path, "rb") as fh:
                if attachment_type == "audio":
                    msg = bot.send_audio(config.creatorId, fh)
                    audio = getattr(msg, "audio", None)
                    fid = getattr(audio, "file_id", None)
                else:
                    msg = bot.send_photo(config.creatorId, fh)
                    photos = getattr(msg, "photo", None) or []
                    fid = photos[-1].file_id if photos else None
            if fid:
                ids.append(fid)
        except Exception as e:
            logger.err("admin mail cache file_id:", e)
            return []
    return ids


def telegram_send(
        tgid: int, message: str, parse_mode: str, attachments: list,
        attachment_type: str, retries: int = FLOOD_RETRIES,
        file_ids: Optional[list] = None) -> tuple[bool, Optional[str]]:
    try:
        bot = _bot()
        mode = _parse_mode(parse_mode)
        kwargs = {}
        if mode:
            kwargs["parse_mode"] = mode
        if file_ids:
            caption = message or None
            for index, fid in enumerate(file_ids):
                extra = dict(kwargs)
                if index == 0 and caption:
                    extra["caption"] = caption
                if attachment_type == "audio":
                    bot.send_audio(tgid, fid, **extra)
                else:
                    bot.send_photo(tgid, fid, **extra)
            return True, None
        if not attachments or not attachment_type:
            bot.send_message(tgid, message, **kwargs)
            return True, None
        caption = message or None
        for index, item in enumerate(attachments):
            path = item["path"] if isinstance(item, dict) else item
            extra = dict(kwargs)
            if index == 0 and caption:
                extra["caption"] = caption
            with open(path, "rb") as fh:
                if attachment_type == "audio":
                    bot.send_audio(tgid, fh, **extra)
                else:
                    bot.send_photo(tgid, fh, **extra)
        return True, None
    except Exception as e:
        wait = getattr(e, "retry_after", None) or getattr(e, "seconds", None)
        if wait and retries > 0:
            time.sleep(int(wait) + 1)
            return telegram_send(
                tgid, message, parse_mode, attachments, attachment_type,
                retries=retries - 1, file_ids=file_ids)
        return False, "%s: %s" % (type(e).__name__, e)


_bot_singleton = None


def _bot():
    global _bot_singleton
    if _bot_singleton is None:
        import telebot
        _bot_singleton = telebot.TeleBot(config.token, threaded=False)
    return _bot_singleton


def _parse_mode(value: str) -> Optional[str]:
    if value in ("html", "HTML"):
        return "HTML"
    if value in ("mrkd", "markdown", "Markdown"):
        return "Markdown"
    return None
