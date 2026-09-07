# -*- coding: utf-8 -*-
"""Admin broadcast worker. Own thread in the jobs role — not rec/circle/send."""
from __future__ import annotations

import time
from typing import Callable, Optional

import config
from app.admin_web import mail_jobs
from db.sqliteAdapter import SQLighter
from lib.tools.logger import logger

SEND_BATCH_SIZE = 50
SEND_BATCH_SLEEP_SECONDS = 1
PROGRESS_EVERY = 25

SendFn = Callable[[int, str, str, list, str], tuple[bool, Optional[str]]]


def _db_path(database=None):
    return config.db_path if database is None else database


def is_channel_identifier(tgid) -> bool:
    try:
        return str(int(tgid)).startswith("-100")
    except Exception:
        return False


def mailer_loop(database=None, send_fn: Optional[SendFn] = None, stop_after: int = 0):
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
    recipients = _recipients(job, database=database)
    mail_jobs.update_progress(job_id, total=len(recipients), database=database)
    parse_mode = job.get("parse_mode") or ""
    attachment_type = job.get("attachment_type") or ""
    attachments = job.get("attachments") or []
    message = job.get("message") or ""

    send(config.creatorId, "Start sending messages to %s" % len(recipients),
         "", [], "")

    sent = failed = skipped = 0
    for index, tgid in enumerate(recipients, start=1):
        if mail_jobs.is_cancel_requested(job_id, database=database):
            mail_jobs.update_progress(
                job_id, sent=sent, failed=failed, skipped=skipped,
                last_error="cancelled", database=database)
            mail_jobs.finish(
                job_id, mail_jobs.STATUS_CANCELLED, "cancelled",
                database=database)
            send(
                config.creatorId,
                "Mailing cancelled. Sent: %s. Failed: %s. Skipped: %s."
                % (sent, failed, skipped),
                "", [], "")
            return
        if index % SEND_BATCH_SIZE == 0:
            time.sleep(SEND_BATCH_SLEEP_SECONDS)
        if is_channel_identifier(tgid):
            skipped += 1
            continue
        ok, error = send(
            int(tgid), message, parse_mode, attachments, attachment_type)
        if ok:
            sent += 1
        else:
            failed += 1
            mail_jobs.update_progress(
                job_id, last_error=error, database=database)
        if index % PROGRESS_EVERY == 0 or index == len(recipients):
            mail_jobs.update_progress(
                job_id, sent=sent, failed=failed, skipped=skipped,
                database=database)

    mail_jobs.update_progress(
        job_id, sent=sent, failed=failed, skipped=skipped, database=database)
    mail_jobs.finish(job_id, mail_jobs.STATUS_DONE, database=database)
    send(
        config.creatorId,
        "All messages sent. Sent: %s. Failed: %s. Skipped channels: %s."
        % (sent, failed, skipped),
        "", [], "")
    logger.log(
        "admin mail job", job_id, "done sent", sent, "failed", failed,
        "skipped", skipped)


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


def telegram_send(
        tgid: int, message: str, parse_mode: str, attachments: list,
        attachment_type: str, retries: int = 1) -> tuple[bool, Optional[str]]:
    try:
        bot = _bot()
        mode = _parse_mode(parse_mode)
        kwargs = {}
        if mode:
            kwargs["parse_mode"] = mode
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
                retries=retries - 1)
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
