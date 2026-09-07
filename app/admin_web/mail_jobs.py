# -*- coding: utf-8 -*-
"""Broadcast jobs in sqlite. Claimed by the jobs-role mailer, not send workers."""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Optional

from app.admin_web.dbutil import connect, row_to_dict

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
STATUS_CANCEL_REQUESTED = "cancel_requested"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS admin_mail_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by TEXT,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    parse_mode TEXT NOT NULL DEFAULT '',
    attachment_type TEXT NOT NULL DEFAULT '',
    attachments_json TEXT NOT NULL DEFAULT '[]',
    to_creator_only INTEGER NOT NULL DEFAULT 1,
    recipients_text TEXT NOT NULL DEFAULT '',
    language TEXT,
    total INTEGER NOT NULL DEFAULT 0,
    sent INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    started_at TEXT,
    finished_at TEXT
)
"""

_lock = threading.Lock()
_ready = set()


def ensure_table(database: Optional[str] = None) -> None:
    key = database or ""
    if key in _ready:
        return
    with _lock:
        if key in _ready:
            return
        conn = connect(database)
        try:
            conn.execute(CREATE_SQL)
            conn.commit()
            _ready.add(key)
        finally:
            conn.close()


def attachments_dir(job_id: int, work_dir: str) -> str:
    path = os.path.join(work_dir, "tmp", "admin_mail", str(job_id))
    os.makedirs(path, exist_ok=True)
    return path


def enqueue(
        message: str,
        parse_mode: str = "",
        attachment_type: str = "",
        attachments: Optional[list] = None,
        to_creator_only: bool = True,
        recipients_text: str = "",
        language: Optional[str] = None,
        created_by: Optional[str] = None,
        database: Optional[str] = None) -> dict[str, Any]:
    ensure_table(database)
    conn = connect(database)
    try:
        cur = conn.execute(
            "INSERT INTO admin_mail_jobs ("
            "status, message, parse_mode, attachment_type, attachments_json, "
            "to_creator_only, recipients_text, language, created_by"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                STATUS_QUEUED,
                message,
                parse_mode or "",
                attachment_type or "",
                json.dumps(attachments or []),
                1 if to_creator_only else 0,
                recipients_text or "",
                language or None,
                created_by,
            ),
        )
        conn.commit()
        job_id = int(cur.lastrowid)
        return get_job(job_id, database=database)
    finally:
        conn.close()


def set_attachments(job_id: int, attachments: list, database: Optional[str] = None) -> dict:
    ensure_table(database)
    conn = connect(database)
    try:
        conn.execute(
            "UPDATE admin_mail_jobs SET attachments_json = ? WHERE id = ?",
            (json.dumps(attachments or []), int(job_id)),
        )
        conn.commit()
        return get_job(job_id, database=database)
    finally:
        conn.close()


def get_job(job_id: int, database: Optional[str] = None) -> Optional[dict[str, Any]]:
    ensure_table(database)
    conn = connect(database)
    try:
        row = conn.execute(
            "SELECT * FROM admin_mail_jobs WHERE id = ?", (int(job_id),)
        ).fetchone()
        return _present(row)
    finally:
        conn.close()


def list_jobs(limit: int = 20, database: Optional[str] = None) -> list[dict[str, Any]]:
    ensure_table(database)
    conn = connect(database)
    try:
        rows = conn.execute(
            "SELECT * FROM admin_mail_jobs ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [_present(row) for row in rows]
    finally:
        conn.close()


def claim_next(database: Optional[str] = None) -> Optional[dict[str, Any]]:
    ensure_table(database)
    conn = connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM admin_mail_jobs WHERE status = ? ORDER BY id ASC LIMIT 1",
            (STATUS_QUEUED,),
        ).fetchone()
        if row is None:
            conn.execute("COMMIT")
            return None
        conn.execute(
            "UPDATE admin_mail_jobs SET status = ?, started_at = datetime('now') "
            "WHERE id = ? AND status = ?",
            (STATUS_RUNNING, row["id"], STATUS_QUEUED),
        )
        conn.execute("COMMIT")
        return get_job(int(row["id"]), database=database)
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()


def request_cancel(job_id: int, database: Optional[str] = None) -> Optional[dict[str, Any]]:
    conn = connect(database)
    try:
        conn.execute(
            "UPDATE admin_mail_jobs SET status = ? "
            "WHERE id = ? AND status IN (?, ?)",
            (STATUS_CANCEL_REQUESTED, int(job_id), STATUS_QUEUED, STATUS_RUNNING),
        )
        conn.commit()
        return get_job(job_id, database=database)
    finally:
        conn.close()


def is_cancel_requested(job_id: int, database: Optional[str] = None) -> bool:
    conn = connect(database)
    try:
        row = conn.execute(
            "SELECT status FROM admin_mail_jobs WHERE id = ?", (int(job_id),)
        ).fetchone()
        return bool(row) and row["status"] == STATUS_CANCEL_REQUESTED
    finally:
        conn.close()


def update_progress(
        job_id: int,
        total: Optional[int] = None,
        sent: Optional[int] = None,
        failed: Optional[int] = None,
        skipped: Optional[int] = None,
        last_error: Optional[str] = None,
        database: Optional[str] = None) -> None:
    fields = []
    values: list[Any] = []
    if total is not None:
        fields.append("total = ?")
        values.append(int(total))
    if sent is not None:
        fields.append("sent = ?")
        values.append(int(sent))
    if failed is not None:
        fields.append("failed = ?")
        values.append(int(failed))
    if skipped is not None:
        fields.append("skipped = ?")
        values.append(int(skipped))
    if last_error is not None:
        fields.append("last_error = ?")
        values.append(last_error)
    if not fields:
        return
    values.append(int(job_id))
    conn = connect(database)
    try:
        conn.execute(
            "UPDATE admin_mail_jobs SET " + ", ".join(fields) + " WHERE id = ?",
            values,
        )
        conn.commit()
    finally:
        conn.close()


def finish(
        job_id: int,
        status: str,
        last_error: Optional[str] = None,
        database: Optional[str] = None) -> None:
    conn = connect(database)
    try:
        conn.execute(
            "UPDATE admin_mail_jobs SET status = ?, finished_at = datetime('now'), "
            "last_error = COALESCE(?, last_error) WHERE id = ?",
            (status, last_error, int(job_id)),
        )
        conn.commit()
    finally:
        conn.close()


def _present(row) -> Optional[dict[str, Any]]:
    data = row_to_dict(row)
    if data is None:
        return None
    try:
        data["attachments"] = json.loads(data.get("attachments_json") or "[]")
    except ValueError:
        data["attachments"] = []
    data["to_creator_only"] = bool(data.get("to_creator_only"))
    data["progress"] = _progress(data)
    return data


def _progress(data: dict[str, Any]) -> float:
    total = int(data.get("total") or 0)
    if total <= 0:
        return 0.0
    done = int(data.get("sent") or 0) + int(data.get("failed") or 0) + int(
        data.get("skipped") or 0)
    return round(min(1.0, done / float(total)), 4)
