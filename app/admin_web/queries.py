# -*- coding: utf-8 -*-
"""Admin reads/writes for the operator UI."""
from __future__ import annotations

from typing import Any, Optional

import config
from app.admin_web import auth
from app.admin_web.dbutil import connect, row_to_dict
from app.jobs.circle_health import format_status_lines
from app.repository.storage import storage
from db.sqliteAdapter import SQLighter


LIVE_BOT_SUB = (
    "utc.tariff_id > 0 AND utc.time_left > 0 AND utc.notify_count != 0"
)


def _db_path(database=None):
    return config.db_path if database is None else database


def find_admin(mail: str, password: str, database: Optional[str] = None):
    conn = connect(database)
    try:
        row = conn.execute(
            "SELECT id, mail, password FROM admins WHERE mail = ?",
            (mail,),
        ).fetchone()
        if row is None:
            return None
        ok, upgraded = auth.verify_password(password, row["password"] or "")
        if not ok:
            return None
        if upgraded:
            conn.execute(
                "UPDATE admins SET password = ? WHERE id = ?",
                (upgraded, row["id"]),
            )
            conn.commit()
        return {"id": row["id"], "mail": row["mail"]}
    finally:
        conn.close()


def stats(database: Optional[str] = None) -> dict[str, Any]:
    db = SQLighter(_db_path(database))
    try:
        total = db.count_users()
        with_subs = db.count_users(True)
        with_subs_notify = db.count_users(with_subs_active=True)
        with_bot_sub = db.count_users(payed=True)
        receive_episodes = db.count_users(receive_episodes=True)
        digest_reminder = db.count_users(digest_reminder=True)
        blocked = db.count_users(deleted=True)
        last_channel_row = db.get_last_channel_id()
        max_channel_id = int(last_channel_row["id"]) if last_channel_row else 0
    finally:
        db.close()

    conn = connect(database)
    try:
        lang_rows = conn.execute(
            "SELECT lang, COUNT(*) AS count FROM users "
            "WHERE deleted_at IS NULL GROUP BY lang ORDER BY count DESC"
        ).fetchall()
        by_lang = [
            {"lang": row["lang"] or "—", "count": int(row["count"])}
            for row in lang_rows
        ]
    finally:
        conn.close()

    extra = ""
    try:
        extra = format_status_lines(database=database)
    except Exception:
        extra = ""

    return {
        "total": total,
        "with_subs": with_subs,
        "with_subs_notify": with_subs_notify,
        "with_bot_sub": with_bot_sub,
        "receive_episodes": receive_episodes,
        "digest_reminder": digest_reminder,
        "blocked": blocked,
        "by_lang": by_lang,
        "updater_channel_id": storage.get_last_channel_id(),
        "max_channel_id": max_channel_id,
        "circle_status": extra,
    }


def list_users(
        page: int = 1,
        per_page: int = 100,
        tgid: Optional[str] = None,
        database: Optional[str] = None) -> dict[str, Any]:
    page = max(int(page or 1), 1)
    per_page = min(max(int(per_page or 100), 1), 200)
    offset = (page - 1) * per_page
    conn = connect(database)
    try:
        if tgid:
            where = "WHERE u.telegramId = ?"
            params: tuple = (str(tgid),)
            count = conn.execute(
                "SELECT COUNT(*) FROM users u " + where, params
            ).fetchone()[0]
            rows = conn.execute(
                _users_select() + where + " GROUP BY u.id",
                params,
            ).fetchall()
        else:
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            rows = conn.execute(
                _users_select()
                + " GROUP BY u.id ORDER BY "
                + "CASE WHEN (" + LIVE_BOT_SUB + ") THEN 1 ELSE 0 END DESC, "
                + "channels_count DESC LIMIT ? OFFSET ?",
                (per_page, offset),
            ).fetchall()
        users = [_user_row(row) for row in rows]
        ids = [str(u["telegramId"]) for u in users]
        subs_map = _subs_for(conn, ids)
        for user in users:
            user["subs"] = subs_map.get(str(user["telegramId"]), [])
        pages = max(int((int(count) + per_page - 1) / per_page), 1) if count else 1
        return {
            "users": users,
            "page": page,
            "per_page": per_page,
            "total": int(count),
            "pages": pages,
        }
    finally:
        conn.close()


def list_tariffs(database: Optional[str] = None) -> list[dict[str, Any]]:
    conn = connect(database)
    try:
        rows = conn.execute(
            "SELECT id, level, price, notify_count, compression, channel_control "
            "FROM tariffs ORDER BY level ASC"
        ).fetchall()
        return [_tariff_row(row) for row in rows]
    finally:
        conn.close()


def update_tariff(
        tariff_id: int,
        level: int,
        price: int,
        notify_count: int,
        compression: int,
        channel_control: int,
        database: Optional[str] = None) -> Optional[dict[str, Any]]:
    conn = connect(database)
    try:
        conn.execute(
            "UPDATE tariffs SET price = ?, notify_count = ?, compression = ?, "
            "channel_control = ? WHERE id = ? AND level = ?",
            (
                int(price), int(notify_count), int(compression),
                int(channel_control), int(tariff_id), int(level),
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, level, price, notify_count, compression, channel_control "
            "FROM tariffs WHERE id = ? AND level = ?",
            (int(tariff_id), int(level)),
        ).fetchone()
        return _tariff_row(row) if row else None
    finally:
        conn.close()


def _users_select() -> str:
    return (
        "SELECT u.id, u.telegramId, u.lang, u.deleted_at, "
        "utc.tariff_id, utc.balance, utc.time_left, utc.notify_count, "
        "(SELECT COUNT(*) FROM user_channel_cs ucc "
        "WHERE ucc.user_telegram_id = u.telegramId) AS channels_count "
        "FROM users AS u "
        "LEFT JOIN user_tariff_cs AS utc ON utc.uid = u.id "
    )


def _user_row(row) -> dict[str, Any]:
    tariff_id = row["tariff_id"]
    time_left = row["time_left"]
    notify_count = row["notify_count"]
    receives = bool(
        tariff_id is not None
        and int(tariff_id) > 0
        and time_left is not None
        and int(time_left) > 0
        and notify_count is not None
        and int(notify_count) != 0
    )
    return {
        "id": row["id"],
        "telegramId": row["telegramId"],
        "lang": row["lang"],
        "deleted": bool(row["deleted_at"]),
        "channels_count": int(row["channels_count"] or 0),
        "tariff_id": tariff_id,
        "balance": row["balance"],
        "time_left": time_left,
        "time_left_days": (float(time_left) / 24.0) if time_left is not None else None,
        "notify_count": notify_count,
        "receives_episodes": receives,
    }


def _subs_for(conn, telegram_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not telegram_ids:
        return {}
    placeholders = ",".join("?" * len(telegram_ids))
    rows = conn.execute(
        "SELECT ucc.user_telegram_id AS tgid, channels.name AS name, ucc.notify "
        "FROM user_channel_cs ucc "
        "LEFT JOIN channels ON channels.id = ucc.channel_id "
        "WHERE ucc.user_telegram_id IN (" + placeholders + ")",
        telegram_ids,
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["tgid"]), []).append({
            "name": row["name"] or "—",
            "notify": int(row["notify"] or 0) == 1,
        })
    return grouped


def _tariff_row(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "level": row["level"],
        "price": row["price"],
        "notify_count": row["notify_count"],
        "compression": row["compression"],
        "channel_control": row["channel_control"],
    }
