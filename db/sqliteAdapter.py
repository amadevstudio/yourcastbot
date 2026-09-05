# -*- coding: utf-8 -*-
import datetime
import sqlite3
import re
import threading
from typing import Any, cast as typing_cast

from app.i18n.messages import routed_messages, get_message_rtd
from config import (
    max_subscriptions_without_tariff)

from db.connection import connect_sqlite
from db.dbTypes import UserDBType
from db.hot_indexes import ensure_hot_path_indexes

from lib.tools.logger import logger


_users_deleted_at_lock = threading.Lock()
_users_deleted_at_checked = False

_channel_http_validators_lock = threading.Lock()
_channel_http_validators_checked = False

_send_outbox_lock = threading.Lock()
_send_outbox_ready = set()

_runtime_kv_lock = threading.Lock()
_runtime_kv_ready = set()

_users_digest_lock = threading.Lock()
_users_digest_ready = set()

_digest_outbox_lock = threading.Lock()
_digest_outbox_ready = set()


def _ensure_channel_http_validators_columns(connection: sqlite3.Connection) -> None:
    # db/migrations/00012_channel_http_validators.py adds ETag/Last-Modified
    # columns, but migrations are applied by hand while deploy only git-pulls
    # and restarts. The updater reads these on every circle, so create them
    # here as well, once per process, to survive a deploy ahead of the migration.
    global _channel_http_validators_checked
    if _channel_http_validators_checked:
        return

    with _channel_http_validators_lock:
        if _channel_http_validators_checked:
            return
        try:
            columns = [
                row[1] for row in
                connection.execute("PRAGMA table_info(channels)").fetchall()]
            if len(columns) > 0:
                if 'http_etag' not in columns:
                    connection.execute(
                        "ALTER TABLE channels ADD COLUMN http_etag TEXT")
                    connection.commit()
                    logger.warn(
                        "channels.http_etag was missing and has been created")
                if 'http_last_modified' not in columns:
                    connection.execute(
                        "ALTER TABLE channels ADD COLUMN http_last_modified TEXT")
                    connection.commit()
                    logger.warn(
                        "channels.http_last_modified was missing "
                        "and has been created")
        except Exception as e:
            logger.err(
                "Could not ensure channels HTTP validator columns:", e)
        finally:
            _channel_http_validators_checked = True



def _ensure_users_deleted_at_column(connection: sqlite3.Connection) -> None:
    # db/migrations/00011_users_deleted_at.py adds users.deleted_at, but migrations are applied
    # by hand while the deploy restarts the bot on its own. Every recipient query below reads the
    # column, so it is created here as well, once per process, to survive a deploy that runs
    # ahead of the migration.
    global _users_deleted_at_checked
    if _users_deleted_at_checked:
        return

    with _users_deleted_at_lock:
        if _users_deleted_at_checked:
            return
        try:
            columns = [
                row[1] for row in
                connection.execute("PRAGMA table_info(users)").fetchall()]
            if len(columns) > 0 and 'deleted_at' not in columns:
                connection.execute("ALTER TABLE users ADD COLUMN deleted_at text")
                connection.commit()
                logger.warn("users.deleted_at was missing and has been created")
        except Exception as e:
            logger.err("Could not ensure users.deleted_at column:", e)
        finally:
            _users_deleted_at_checked = True


def ensure_send_outbox_table(connection: sqlite3.Connection, database=None) -> None:
    # db/migrations/00013_send_outbox.py creates send_outbox, but migrations
    # are applied by hand while the deploy restarts the bot on its own.
    # Rec/update jobs must survive a restart, so the table is created here
    # as well, once per database path.
    key = database
    if key is not None and key in _send_outbox_ready:
        return

    with _send_outbox_lock:
        if key is not None and key in _send_outbox_ready:
            return
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS send_outbox ("
                "id INTEGER PRIMARY KEY, "
                "created_at TEXT, "
                "action TEXT NOT NULL, "
                "user_id TEXT NOT NULL, "
                "payload_json TEXT NOT NULL, "
                "status TEXT NOT NULL, "
                "attempts INTEGER NOT NULL DEFAULT 0, "
                "leased_until TEXT NULL, "
                "available_at TEXT NOT NULL)")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS send_outbox_claim_idx "
                "ON send_outbox (status, available_at, id)")
            connection.commit()
            if key is not None:
                _send_outbox_ready.add(key)
        except Exception as e:
            logger.err("Could not ensure send_outbox table:", e)


def ensure_bot_runtime_kv_table(connection: sqlite3.Connection, database=None) -> None:
    key = database
    if key is not None and key in _runtime_kv_ready:
        return

    with _runtime_kv_lock:
        if key is not None and key in _runtime_kv_ready:
            return
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS bot_runtime_kv ("
                "key TEXT PRIMARY KEY, "
                "value TEXT NOT NULL)")
            connection.commit()
            if key is not None:
                _runtime_kv_ready.add(key)
        except Exception as e:
            logger.err("Could not ensure bot_runtime_kv table:", e)


def ensure_digest_outbox_table(connection: sqlite3.Connection, database=None) -> None:
    # Jobs drain this table; updater only inserts user ids. Created here
    # because deploy restarts without running migrations by hand.
    key = database
    if key is not None and key in _digest_outbox_ready:
        return

    with _digest_outbox_lock:
        if key is not None and key in _digest_outbox_ready:
            return
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS digest_outbox ("
                "user_telegram_id INTEGER PRIMARY KEY, "
                "created_at TEXT NOT NULL)")
            connection.commit()
            if key is not None:
                _digest_outbox_ready.add(key)
        except Exception as e:
            logger.err("Could not ensure digest_outbox table:", e)


def _pragma_user_columns(connection: sqlite3.Connection) -> list[str]:
    return [
        row[1] for row in
        connection.execute("PRAGMA table_info(users)").fetchall()]


def _add_users_column(connection: sqlite3.Connection, sql: str) -> bool:
    try:
        connection.execute(sql)
        connection.commit()
        return True
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            return False
        raise


def ensure_users_nosub_digest_columns(connection: sqlite3.Connection, database=None) -> None:
    # Per-user digest opt-out and last-sent live on users, not in Redis/runtime_kv:
    # they must survive restarts and be readable from bot, updater, and jobs.
    # Deploy git-pulls and restarts without running migrations, so the columns
    # are created here as well. Existing rows are stamped with now so the first
    # digest waits a week.
    key = database
    if key is not None and key in _users_digest_ready:
        return

    with _users_digest_lock:
        if key is not None and key in _users_digest_ready:
            return
        try:
            columns = _pragma_user_columns(connection)
            if not columns:
                return
            if 'nosub_digest_enabled' not in columns:
                if _add_users_column(
                        connection,
                        "ALTER TABLE users ADD COLUMN "
                        "nosub_digest_enabled INTEGER NOT NULL DEFAULT 1"):
                    logger.warn(
                        "users.nosub_digest_enabled was missing "
                        "and has been created")
            if 'nosub_digest_sent_at' not in columns:
                if _add_users_column(
                        connection,
                        "ALTER TABLE users ADD COLUMN "
                        "nosub_digest_sent_at TEXT"):
                    logger.warn(
                        "users.nosub_digest_sent_at was missing "
                        "and has been created")
            # ALTER cannot use datetime('now') as a default on this SQLite.
            # Existing rows stay NULL until the UPDATE below stamps them.
            if 'nosub_digest_sent_at' in _pragma_user_columns(connection):
                has_null = connection.execute(
                    "SELECT 1 FROM users WHERE nosub_digest_sent_at IS NULL "
                    "LIMIT 1").fetchone()
                if has_null is not None:
                    connection.execute(
                        "UPDATE users SET nosub_digest_sent_at = datetime('now') "
                        "WHERE nosub_digest_sent_at IS NULL")
                    connection.commit()
                    logger.warn(
                        "users.nosub_digest_sent_at NULLs backfilled to now")
            if key is not None:
                _users_digest_ready.add(key)
        except Exception as e:
            logger.err("Could not ensure users nosub digest columns:", e)


def helper_remove_proto_from_link(link):
    link_tester = re.compile(r'(?:https?)?:\/\/((?:[a-z0-9-_\.]+)*\/.*)')
    reg_result = link_tester.match(link)
    if reg_result is None or len(reg_result.groups()) != 1:
        return link
    else:
        return "http://%s" % reg_result.group(1)


# class SQLighter(metaclass=SingletonWithInit):
class SQLighter:

    def __init__(self, database):
        self.connection = connect_sqlite(database)
        self.connection.create_function("LOWER_UNICODE", 1, self.__lower_unicode)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
        _ensure_users_deleted_at_column(self.connection)
        _ensure_channel_http_validators_columns(self.connection)
        ensure_users_nosub_digest_columns(self.connection, database)
        ensure_send_outbox_table(self.connection, database)
        ensure_bot_runtime_kv_table(self.connection, database)
        ensure_digest_outbox_table(self.connection, database)
        ensure_hot_path_indexes(self.connection, database)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def __lower_unicode(self, string):
        return str(string).lower()

    def select_users_subs_count(self, telegram_id, search_string=None):
        with self.connection:
            params = (str(telegram_id),)
            if search_string is not None:
                params += ("%" + search_string + "%",)
                searchQuery = " AND LOWER_UNICODE(channels.name) LIKE LOWER_UNICODE(?)"
            else:
                searchQuery = ""
            return self.cursor.execute(
                """
                    SELECT COUNT(*) AS count
                    FROM user_channel_cs
                    LEFT JOIN channels
                        ON user_channel_cs.channel_id = channels.id
                    WHERE user_channel_cs.user_telegram_id = ?
                        %s
                """ % searchQuery,
                params).fetchone()[0]

    def select_users_subs_name_noty(
            self, telegram_id, search_string=None, order: str | None = None, limit: int = 5, offset: int = 0):
        with self.connection:
            params = (str(telegram_id),)

            limit_offset = ""
            if limit is not None:
                limit_offset += f"LIMIT {limit}"
                if offset is not None:
                    limit_offset += f" OFFSET {offset}"

            if search_string is not None:
                params += ("%" + search_string + "%",)
                search_query = " AND LOWER_UNICODE(channels.name) LIKE LOWER_UNICODE(?)"
            else:
                search_query = ""

            query = """SELECT
                channels.id as id,
                channels.itunes_id as itunes_id,
                channels.name as name,
                user_channel_cs.notify as notify,
                -- есть новые выпуски?
                CASE WHEN
                    (channels.last_guid IS NOT NULL
                        AND channels.last_date IS NOT NULL
                        AND (
                            channels.last_guid
                                != user_channel_cs.last_guid
                            AND channels.last_date
                                > user_channel_cs.last_date))
                    THEN 1 ELSE 0 END AS have_new_episodes
                FROM user_channel_cs
                LEFT JOIN channels
                ON user_channel_cs.channel_id = channels.id
                WHERE user_channel_cs.user_telegram_id = ?
                %s %s %s
            """ % (search_query, order if order is not None else '', limit_offset)

            uccs = self.cursor.execute(
                query,
                params).fetchall()
            return uccs

    # есть ли вообще новые выпуски у пользователя
    def is_user_have_new_episodes(self, telegramId):
        with self.connection:
            row = self.cursor.execute(
                """
                    SELECT 1
                    FROM user_channel_cs
                    INNER JOIN channels
                        ON user_channel_cs.channel_id = channels.id
                    WHERE user_channel_cs.user_telegram_id = ?
                        AND channels.last_guid IS NOT NULL
                        AND channels.last_date IS NOT NULL
                        AND channels.last_guid != user_channel_cs.last_guid
                        AND channels.last_date > user_channel_cs.last_date
                    LIMIT 1
                """,
                (telegramId,)).fetchone()
            return row is not None

    def select_users_subs(self, telegramId, sql=""):
        with self.connection:
            if sql != "":
                sql = " " + sql
            uccs = self.cursor.execute(
                """SELECT
                    channels.itunes_id as itunes_id,
                    user_channel_cs.last_guid as last_guid,
                    user_channel_cs.last_date as last_date,
                    channels.name as name,
                    user_channel_cs.notify as notify
                    FROM user_channel_cs
                    LEFT JOIN channels
                    ON user_channel_cs.channel_id = channels.id
                    WHERE user_channel_cs.user_telegram_id = ?%s""" % sql,
                (str(telegramId),)).fetchall()
            return uccs

    def get_channel(self, channel_id) -> Any | None:
        with self.connection:
            uccs = self.cursor.execute(
                "SELECT * FROM channels WHERE id = ?",
                (str(channel_id),)).fetchone()
            return uccs

    def get_channel_by_service(
            self, ch_service_id, service_name="itunes"):
        with self.connection:
            if service_name == "itunes":
                where_query = "itunes_id = ?"
            elif service_name == "rss":
                where_query = "rss_link = ?"

            channel = self.cursor.execute(
                """SELECT id, itunes_id,
                        name, rss_link
                    FROM channels
                    WHERE %s""" % where_query,
                (str(ch_service_id),)).fetchone()
            return channel

    def get_channel_by_service_tg(
            self, utgid, ch_service_id, service_name="itunes"):
        with self.connection:
            if service_name == "itunes":
                where_query = "channels.itunes_id = ?"
            elif service_name == 'rss':
                where_query = "channels.rss_link = ?"

            uccs = self.cursor.execute(
                """SELECT channels.id, channels.itunes_id AS service_id,
                        channels.name, channels.rss_link
                    FROM channels
                    LEFT JOIN user_channel_cs
                    ON user_channel_cs.channel_id = channels.id
                    WHERE user_channel_cs.user_telegram_id = ?
                        AND %s""" % where_query,
                (str(utgid), str(ch_service_id),)).fetchone()
            return uccs

    def get_full_channel_by_service_tg(
            self, utgid, ch_service_id, service_name="itunes"):
        with self.connection:
            if service_name == "itunes":
                uccs = self.cursor.execute(
                    """SELECT
                        channels.id as id,
                        channels.itunes_id as itunes_id,
                        user_channel_cs.last_guid as last_guid,
                        user_channel_cs.last_date as last_date,
                        channels.name as name,
                        user_channel_cs.notify as notify
                        FROM user_channel_cs
                        LEFT JOIN channels
                        ON user_channel_cs.channel_id = channels.id
                        WHERE user_channel_cs.user_telegram_id = ? \
                        AND channels.itunes_id = ?""",
                    (str(utgid), str(ch_service_id),)).fetchone()
                return uccs

    def get_all_channels(self):
        with self.connection:
            return self.cursor.execute("SELECT * FROM channels").fetchall()

    def get_next_channel(self, channel_id):
        with self.connection:
            return self.cursor.execute(
                "SELECT * FROM channels WHERE id > ? LIMIT 1",
                (str(channel_id),)).fetchone()

    def get_channels_with_users_subscription(self):
        with self.connection:
            return self.cursor.execute(
                """
                    SELECT DISTINCT c.id FROM channels c
                    INNER JOIN user_channel_cs ucc ON (ucc.channel_id = c.id)
                    INNER JOIN users u ON (u.telegramId = ucc.user_telegram_id)
                    INNER JOIN user_tariff_cs utc ON (utc.uid = u.id)
                    WHERE utc.tariff_id > 0
                        AND utc.time_left > 0 AND utc.notify_count != 0
                """).fetchall()

    def is_user_have_bot_subscription(self, telegramId):
        with self.connection:
            user_subscription = self.cursor.execute(
                """
                    SELECT u.id FROM user_tariff_cs utc
                    INNER JOIN users u ON (u.id = utc.uid)
                    WHERE u.telegramId = ? AND utc.tariff_id > 0
                        AND utc.time_left > 0 AND utc.notify_count != 0
                """,
                (str(telegramId),)).fetchone()
            if user_subscription is None:
                return False
            else:
                return True

    def get_channel_or_next(self, channel_id, channel_set=None):
        with self.connection:
            if not channel_set:
                return self.cursor.execute(
                    "SELECT * FROM channels WHERE id >= ? LIMIT 1",
                    (str(channel_id),)).fetchone()
            else:
                return self.cursor.execute(
                    "SELECT * FROM channels WHERE id >= ? \
                    AND id IN (" + ','.join(channel_set) + ")\
                    LIMIT 1",
                    (str(channel_id),)).fetchone()

    def _live_notify_recipient_exists_sql(self):
        # Same joins as get_uccs_by_channel / getTgChannelSubConnectionsByPodcast:
        # notify=1 on a live user (paid or not), or an active tg-channel
        # connection whose owner has channel_control. No CAST on telegram ids.
        return """
            (
                EXISTS (
                    SELECT 1
                    FROM user_channel_cs uc
                    WHERE uc.channel_id = c.id
                        AND uc.notify = 1
                        AND NOT EXISTS (
                            SELECT 1 FROM users du
                            WHERE du.telegramId = uc.user_telegram_id
                                AND du.deleted_at IS NOT NULL
                        )
                )
                OR EXISTS (
                    SELECT 1
                    FROM user_channel_cs AS uc
                    INNER JOIN subscription_to_tg_channel_cs AS sttcc
                        ON (sttcc.user_channel_cs_id = uc.id)
                    INNER JOIN tg_channels AS tc
                        ON (tc.id = sttcc.tg_channel_id)
                    LEFT JOIN user_tariff_cs AS ut ON ut.uid = (SELECT id
                        FROM users AS u
                        WHERE u.telegramId = uc.user_telegram_id)
                    LEFT JOIN tariffs AS t ON t.id = ut.tariff_id
                    WHERE uc.channel_id = c.id
                        AND tc.active = 1
                        AND ut.notify_count != 0
                        AND ut.time_left > 0
                        AND t.channel_control = 1
                )
            )
        """

    def get_next_channel_to_poll(self, channel_id):
        return self._get_channel_to_poll(channel_id, inclusive=False)

    def get_channel_or_next_to_poll(self, channel_id):
        return self._get_channel_to_poll(channel_id, inclusive=True)

    def _get_channel_to_poll(self, channel_id, inclusive=True):
        with self.connection:
            op = ">=" if inclusive else ">"
            sql = (
                "SELECT c.* FROM channels c "
                "WHERE c.id %s ? AND %s "
                "ORDER BY c.id ASC LIMIT 1"
            ) % (op, self._live_notify_recipient_exists_sql())
            return self.cursor.execute(sql, (str(channel_id),)).fetchone()

    def get_last_channel_id(self):
        with self.connection:
            return self.cursor.execute(
                "SELECT id FROM channels ORDER BY id DESC LIMIT 1").fetchone()

    def update_channel_last_guid_date(
            self, podcastId, lastGuid, lastDate):
        with self.connection:
            self.cursor.execute(
                'UPDATE channels SET last_guid = ?, last_date = ? \
                WHERE id = ?',
                (
                    str(lastGuid), str(lastDate), str(podcastId),))
            self.connection.commit()

    def update_channel_http_validators(
            self, podcastId, etag, last_modified):
        with self.connection:
            self.cursor.execute(
                'UPDATE channels SET http_etag = ?, http_last_modified = ? \
                WHERE id = ?',
                (etag, last_modified, str(podcastId),))
            self.connection.commit()

    def get_uccs_by_channel(
            self, channel_id,
            notifications_enabled=None, have_subscription=None,
            include_deleted_users=False):
        with self.connection:
            query = "SELECT uc.*, ut.notify_count \
                    FROM user_channel_cs uc \
                    LEFT JOIN user_tariff_cs ut ON ut.uid = (SELECT id \
                        FROM users u \
                        WHERE u.telegramId = uc.user_telegram_id) \
                    WHERE channel_id = ?"
            # пользователи, помеченные удалёнными (заблокировали бота), сохраняют подписки,
            # но ничего не получают
            if not include_deleted_users:
                query += " AND NOT EXISTS (SELECT 1 FROM users du \
                    WHERE du.telegramId = uc.user_telegram_id \
                        AND du.deleted_at IS NOT NULL)"
            if have_subscription is not None:
                if have_subscription:
                    query += " AND (\
                        ut.notify_count != 0 \
                            AND ut.time_left > 0 \
                            AND ut.tariff_id > 0)"
                else:
                    query += " AND (\
                        ut.notify_count = 0 \
                            OR ut.time_left = 0 \
                            OR ut.tariff_id = 0)"
            if notifications_enabled is not None:
                if notifications_enabled:
                    query += " AND uc.notify = 1"
                else:
                    query += " AND uc.notify = 0"
            return self.cursor.execute(query, (str(channel_id),)).fetchall()

    def get_uccs_by_tg(
            self, telegramId,
            notifications_enabled=True, is_user_have_bot_subscription=True):
        with self.connection:
            query = "SELECT uc.*, ut.notify_count \
                    FROM user_channel_cs uc \
                    LEFT JOIN user_tariff_cs ut ON ut.uid = (SELECT id \
                        FROM users u \
                        WHERE u.telegramId = uc.user_telegram_id) \
                    WHERE user_telegram_id = ?"
            if notifications_enabled:
                query += " AND uc.notify = 1"
            if not is_user_have_bot_subscription:
                query += " LIMIT " + str(max_subscriptions_without_tariff)
            return self.cursor.execute(query, (str(telegramId),)).fetchall()

    def get_uccs_count_by_tg(self, telegramId):
        with self.connection:
            count = self.cursor.execute("SELECT count(*) \
                    FROM user_channel_cs \
                    WHERE user_telegram_id = ?", (str(telegramId),)).fetchone()
            return count[0]

    def add_sub(
            self, telegramId, podcastId, podcastServiceId, rss_link, pcName,
            lastGuid, lastDate, notify=True, serviceName='itunes'):
        with self.connection:
            notify = 1 if notify else 0
            rss_link = helper_remove_proto_from_link(rss_link)

            # получение канала
            if podcastId is not None and podcastId != 0:
                channel = self.cursor.execute(
                    'SELECT id, name FROM channels WHERE id = ?',
                    (str(podcastId),)).fetchone()
            else:
                if serviceName == 'itunes':
                    channel = self.cursor.execute(
                        'SELECT id, name FROM channels \
                        WHERE itunes_id = ? OR rss_link = ?',
                        (str(podcastServiceId), str(rss_link),)).fetchone()
                elif serviceName == 'rss':
                    channel = self.cursor.execute(
                        'SELECT id, name FROM channels WHERE rss_link = ?',
                        (str(podcastServiceId),)).fetchone()

            if channel is None:
                # если нет — создание и получение
                if serviceName == 'itunes':
                    self.cursor.execute(
                        'INSERT INTO channels \
                            (itunes_id, name, rss_link, last_guid, last_date) \
                        VALUES (?, ?, ?, ?, ?)',
                        (str(podcastServiceId), str(pcName), str(rss_link),
                         str(lastGuid), str(lastDate),))
                    self.connection.commit()
                    channel = self.cursor.execute(
                        'SELECT id, name FROM channels \
                        WHERE itunes_id = ? AND name = ? AND rss_link = ?',
                        (
                            str(podcastServiceId),
                            str(pcName), str(rss_link),)).fetchone()

                elif serviceName == 'rss':
                    self.cursor.execute(
                        'INSERT INTO channels \
                            (name, rss_link, last_guid, last_date) \
                            VALUES (?, ?, ?, ?)',
                        (str(pcName), str(podcastServiceId),
                         str(lastGuid), str(lastDate),))
                    # new_channel_id = self.cursor.lastrowid
                    self.connection.commit()
                    channel = self.cursor.execute(
                        'SELECT id, name \
                        FROM channels \
                        WHERE rss_link = ? AND name = ?',
                        (str(podcastServiceId), str(pcName),)).fetchone()

            else:
                # если есть и имя отличается — обновление имени
                if serviceName == 'itunes':
                    self.cursor.execute(
                        'UPDATE channels \
                        SET itunes_id = ?, name = ?, rss_link = ?, \
                            last_guid = ?, last_date = ? \
                        WHERE id = ?',
                        (
                            str(podcastServiceId), str(pcName), str(rss_link),
                            str(lastGuid), str(lastDate),
                            str(channel['id'])))
                elif serviceName == 'rss':
                    self.cursor.execute(
                        'UPDATE channels \
                        SET name = ?, last_guid = ?, last_date = ? \
                        WHERE id = ?',
                        (str(pcName), str(lastGuid), str(lastDate),
                         str(channel['id'])))
                self.connection.commit()

            # поиск связи
            ucc = self.cursor.execute(
                'SELECT id FROM user_channel_cs \
                WHERE channel_id = ? AND user_telegram_id = ?',
                (str(channel['id']), str(telegramId))).fetchone()
            if ucc is None:
                # если нет — создание
                self.cursor.execute(
                    'INSERT INTO user_channel_cs (\
                    user_telegram_id, channel_id, \
                    last_guid, last_date, notify) \
                    VALUES (?, ?, ?, ?, ?)',
                    (
                        str(telegramId), str(channel['id']),
                        str(lastGuid), lastDate, str(notify)))
            else:
                # если есть — обновление
                self.cursor.execute(
                    'UPDATE user_channel_cs SET \
                    last_guid = ?, last_date = ?, notify = ? \
                    WHERE user_telegram_id = ? AND channel_id = ?',
                    (
                        str(lastGuid), lastDate, str(notify),
                        str(telegramId), str(channel['id']),))
            self.connection.commit()

    def remove_sub(
            self, telegramId, podcastId,
            podcastServiceId, serviceName="itunes"):
        with self.connection:
            # получение канала
            if podcastId is not None and podcastId != 0:
                channel = self.cursor.execute(
                    'SELECT id, name FROM channels WHERE id = ?',
                    (str(podcastId),)).fetchone()
            else:
                if serviceName == 'itunes':
                    channel = self.cursor.execute(
                        'SELECT id, name FROM channels WHERE itunes_id = ?',
                        (str(podcastServiceId),)).fetchone()
                elif serviceName == 'rss':
                    channel = self.cursor.execute(
                        'SELECT id, name FROM channels WHERE rss_link = ?',
                        (str(podcastServiceId),)).fetchone()
                else:
                    logger.warn('Unknown service')
                    return

            if channel is None:
                logger.warn("SQLITE remove sub, Channel is None", telegramId, podcastId, podcastServiceId, serviceName)
                return

            # удаление связей с tg каналом
            self.cursor.execute(
                'DELETE FROM subscription_to_tg_channel_cs \
                WHERE user_channel_cs_id IN \
                (SELECT id FROM user_channel_cs \
                WHERE user_telegram_id = ? AND channel_id = ?)',
                (str(telegramId), str(channel['id']),))
            self.connection.commit()

            # удаление связи
            self.cursor.execute(
                'DELETE FROM user_channel_cs WHERE \
                user_telegram_id = ? AND channel_id = ?',
                (str(telegramId), str(channel['id']),))
            self.connection.commit()

            # удаление канала, если нет связей
            cc = self.cursor.execute(
                'SELECT count(*) FROM user_channel_cs \
                WHERE channel_id = ?',
                (str(channel['id']),)).fetchone()
            if cc[0] == 0:
                self.cursor.execute(
                    "DELETE FROM genre_to_podcast WHERE podcast_id = ?",
                    (str(channel['id']),))
                self.cursor.execute(
                    'DELETE FROM channels WHERE id = ?',
                    (str(channel['id']),))
                self.connection.commit()

            return channel['name']

    def check_subscription(self, telegramId, podcastId):
        with self.connection:
            channel = self.cursor.execute(
                'SELECT id FROM channels WHERE id = ?',
                (str(podcastId),)).fetchone()
            if channel is None:
                return False

            cc = self.cursor.execute(
                'SELECT count(*) FROM user_channel_cs \
                WHERE channel_id = ? AND user_telegram_id = ?',
                (str(channel['id']), str(telegramId),)).fetchone()
            if cc[0] > 0:
                if cc[0] > 1:
                    print(
                        "TOO BIG CONNECTIONS (sub?)!, user_tg: ",
                        telegramId, "pc_it: ", podcastId, flush=True)
                return True
            else:
                return False

    def check_notify(self, telegramId, podcastId):
        with self.connection:
            channel = self.cursor.execute(
                'SELECT id FROM channels WHERE id = ?',
                (str(podcastId),)).fetchone()
            if channel is None:
                return False

            cc = self.cursor.execute(
                'SELECT count(*) FROM user_channel_cs \
                WHERE channel_id = ? AND notify = 1 AND user_telegram_id',
                (str(channel['id']), str(telegramId))).fetchone()
            if cc[0] > 0:
                if cc[0] > 1:
                    print(
                        "TOO BIG CONNECTIONS (noty?)!, user_tg: ",
                        telegramId, "pc_it: ", podcastId, flush=True)
                return True
            else:
                return False

    def get_user_related_podcast_info(
            self, telegram_id, podcast_id):
        with self.connection:
            data = {
                'subscribed': False, 'notify': False, 'rate': None,
                'have_new_episodes': False,
                'rating': {'value': None, 'count': 0},
                'last_date': None, 'last_guid': None}

            if podcast_id is None:
                return data

            ntf, rate = False, None
            cc = self.cursor.execute(
                """
                    SELECT notify, rate,
                        user_channel_cs.last_date, user_channel_cs.last_guid,
                        -- есть новые выпуски?
                        CASE WHEN
                            (channels.last_guid IS NOT NULL
                                AND channels.last_date IS NOT NULL
                                AND (
                                    channels.last_guid
                                        != user_channel_cs.last_guid
                                    AND channels.last_date
                                        > user_channel_cs.last_date))
                        THEN 1 ELSE 0 END AS have_new_episodes
                    FROM user_channel_cs
                    INNER JOIN channels ON (
                        channels.id = user_channel_cs.channel_id)
                    WHERE channel_id = ? AND user_telegram_id = ?
                """,
                (str(podcast_id), str(telegram_id))).fetchone()

            if cc is None:
                return data

            data['last_date'] = cc['last_date']
            data['last_guid'] = cc['last_guid']

            have_new_episodes = (cc['have_new_episodes'] == 1)
            if cc['notify']:
                ntf = True
            if cc['rate']:
                rate = int(cc['rate'])

            data['subscribed'] = True
            data['notify'] = ntf
            data['rate'] = rate
            data['have_new_episodes'] = have_new_episodes

            rating_result = self.cursor.execute("""
                SELECT AVG(rate) AS rate, COUNT(*) AS count
                FROM user_channel_cs
                WHERE channel_id = ? AND rate IS NOT NULL
            """, (str(podcast_id),)).fetchone()
            if rating_result['rate'] is not None:
                data['rating']['value'] = rating_result['rate']
                data['rating']['count'] = rating_result['count']

            return data

    def complete_itunes_data(
            self, podcastId, rss_link=None,
            service_id=None, service_name='itunes'):
        with self.connection:
            if rss_link is not None:
                rss_link = helper_remove_proto_from_link(rss_link)

            if service_name == 'itunes':
                channel = self.cursor.execute(
                    'SELECT id, itunes_id, rss_link FROM channels \
                        WHERE id = ? OR itunes_id = ? OR rss_link = ?',
                    (str(podcastId), str(service_id), str(rss_link),)
                ).fetchone()

                if channel is None:
                    return None

                # дополняем данные о канале
                update = []
                params = ()
                if channel['itunes_id'] is None and service_id is not None:
                    update.append("itunes_id = ?")
                    params += (str(service_id),)
                if channel['rss_link'] is None and rss_link is not None:
                    update.append("rss_link = ?")
                    params += (str(rss_link),)
                if len(update) > 0:
                    self.cursor.execute(
                        'UPDATE channels SET %s \
                        WHERE id = ?' % (', '.join(update)),
                        params + (str(channel['id']),))
                    self.connection.commit()

    def catchGenres(self, podcastId, podcastGenres):
        with self.connection:
            if podcastId is None:
                return

            currentGenres = self.cursor.execute(
                'SELECT * FROM genre_to_podcast WHERE podcast_id = ?',
                (str(podcastId),)).fetchall()
            currentGenresIds = []
            for curr_genre in currentGenres:
                currentGenresIds.append(curr_genre['genre_id'])

            for genreData in podcastGenres:
                genreName = genreData['name'].lower()

                genre = self.cursor.execute(
                    'SELECT * FROM genres WHERE name = ?',
                    (str(genreName),)).fetchone()

                if genre is None:
                    connection = None
                    # добавление жанра, получение
                    self.cursor.execute(
                        'INSERT INTO genres (name) \
                        VALUES (?)',
                        (str(genreName),))
                    self.connection.commit()
                    genre = self.cursor.execute(
                        'SELECT * FROM genres WHERE name = ?',
                        (str(genreName),)).fetchone()
                else:
                    connection = self.cursor.execute(
                        'SELECT * FROM genre_to_podcast \
                        WHERE podcast_id = ? AND genre_id = ?',
                        (str(podcastId), str(genre['id']),)).fetchone()
                # добавление связи
                isMain = 1 if genreData['isMain'] else 0
                if connection is None:
                    self.cursor.execute(
                        'INSERT INTO genre_to_podcast \
                        (podcast_id, genre_id, is_main) \
                        VALUES (?, ?, ?)',
                        (str(podcastId), str(genre['id']),
                         str(isMain),))
                    self.connection.commit()
                else:
                    self.cursor.execute(
                        'UPDATE genre_to_podcast SET is_main = ?\
                        WHERE podcast_id = ? AND genre_id = ?',
                        (str(isMain), str(podcastId), str(genre['id'])))
                    self.connection.commit()
                    # убираем добавленную связь из текущих
                    if genre['id'] in currentGenresIds:
                        currentGenresIds.remove(genre['id'])

            # удаляем те связи, которые больше не нужны
            if len(currentGenresIds) > 0:
                self.cursor.execute(
                    'DELETE FROM genre_to_podcast \
                    WHERE podcast_id = ? AND genre_id IN (?)',
                    (str(podcastId),
                     str(", ".join(map(str, currentGenresIds))),))
                self.connection.commit()

    def rate_podcast(self, telegramId, podcastId, mark):
        with self.connection:
            try:
                mark = int(mark) % 6
                if mark == 0:
                    mark = None
            except Exception:
                mark = None

            self.cursor.execute(
                'UPDATE user_channel_cs SET rate = ? \
                WHERE user_telegram_id = ? AND channel_id = ?',
                (mark, str(telegramId), str(podcastId),))
            self.connection.commit()

    def turn_notify_tg(self, telegramId, podcastId, value):
        with self.connection:
            value = 1 if value else 0
            self.cursor.execute(
                'UPDATE user_channel_cs SET notify = ? \
                WHERE user_telegram_id = ? AND channel_id = ?',
                (str(value), str(telegramId), str(podcastId),))
            self.connection.commit()

    def update_sub_last_guid(self, telegramId, podcastId, lastGuid):
        with self.connection:
            self.cursor.execute(
                'UPDATE user_channel_cs SET last_guid = ? \
                WHERE user_telegram_id = ? AND channel_id = ?',
                (str(lastGuid), str(telegramId), str(podcastId),))
            self.connection.commit()

    def update_sub_last_guid_and_date(
            self, telegramId, podcastId, lastGuid, lastDate):
        with self.connection:
            self.cursor.execute(
                'UPDATE user_channel_cs SET last_guid = ?, last_date = ? \
                WHERE user_telegram_id = ? AND channel_id = ?',
                (
                    str(lastGuid), str(lastDate),
                    str(telegramId), str(podcastId),))
            self.connection.commit()

    def register_new_user(
            self, telegram_id, user_lang, refer_id=None):
        with self.connection:
            by_refer = False
            isreg = self.cursor.execute(
                'SELECT * FROM users WHERE telegramId = ?',
                (str(telegram_id),)).fetchall()
            if len(isreg) == 0:
                new_user = True
                if refer_id is not None:
                    self.cursor.execute(
                        'INSERT INTO users (telegramId, lang, ref_id, '
                        'nosub_digest_sent_at) VALUES (?, ?, ?, datetime(\'now\'))',
                        (str(telegram_id), str(user_lang), str(refer_id),))
                    by_refer = True
                else:
                    self.cursor.execute(
                        'INSERT INTO users (telegramId, lang, '
                        'nosub_digest_sent_at) VALUES (?, ?, datetime(\'now\'))',
                        (str(telegram_id), str(user_lang),))
            else:
                new_user = False
                self.cursor.execute(
                    'UPDATE users SET lang = ? WHERE telegramId = ?',
                    (str(user_lang), str(telegram_id),))
            self.connection.commit()
        return new_user, by_refer

    def user_clear_refer(self, telegramId):
        with self.connection:
            self.cursor.execute(
                'UPDATE users SET ref_id = ? WHERE telegramId = ?',
                (None,))
            self.connection.commit()

    def update_bitrate_by_tg(self, telegramId, bitrate):
        with self.connection:
            self.cursor.execute(
                'UPDATE users SET bitrate = ? WHERE telegramId = ?',
                (str(bitrate) if bitrate is not None else None, str(telegramId),))
            self.connection.commit()

    def set_nosub_digest_enabled(self, telegramId, enabled: bool) -> None:
        with self.connection:
            self.cursor.execute(
                "UPDATE users SET nosub_digest_enabled = ? WHERE telegramId = ?",
                (1 if enabled else 0, str(telegramId)))
            self.connection.commit()

    def mark_nosub_digest_sent(self, telegramId, when=None) -> None:
        if when is None:
            stamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(when, datetime.datetime):
            stamp = when.strftime("%Y-%m-%d %H:%M:%S")
        else:
            stamp = str(when)
        with self.connection:
            self.cursor.execute(
                "UPDATE users SET nosub_digest_sent_at = ? WHERE telegramId = ?",
                (stamp, str(telegramId)))
            self.connection.commit()

    def get_all_users(
            self, language: str | None = None, include_deleted: bool = False
    ) -> list[UserDBType]:
        with self.connection:
            query = 'SELECT * FROM users WHERE 1'
            params: tuple = ()
            if language is not None:
                query += ' AND lang = ?'
                params += (language,)
            if not include_deleted:
                query += ' AND deleted_at IS NULL'
            return self.cursor.execute(query, params).fetchall()

    def get_user_by_id(self, user_id) -> UserDBType:
        with self.connection:
            return self.cursor.execute(
                "SELECT * FROM users WHERE id = ?", (str(user_id),)).fetchone()

    def get_user_by_tg(self, telegramId):
        with self.connection:
            try:
                return self.cursor.execute(
                    'SELECT * FROM users WHERE telegramId = ?',
                    (str(telegramId),)).fetchall()[0]
            except Exception:
                self.cursor.execute(
                    'DELETE FROM users WHERE telegramId = ?',
                    (str(telegramId),))
                self.connection.commit()
                self.cursor.execute(
                    'INSERT INTO users (telegramId, nosub_digest_sent_at) '
                    'VALUES (?, datetime(\'now\'))',
                    (str(telegramId),))
                self.connection.commit()
                return self.cursor.execute(
                    'SELECT * FROM users WHERE telegramId = ?',
                    (str(telegramId),)).fetchall()[0]

    def delete_user_tg(self, telegramId, hard=True):
        # ВНИМАНИЕ: деструктивно и необратимо. Удаляет все подписки пользователя, а также
        # каналы, у которых после этого не осталось подписчиков (независимо от hard).
        # Для реакции на блокировку бота использовать mark_user_deleted_tg: подписки должны
        # пережить блокировку, чтобы всё восстановилось, когда пользователь вернётся.
        # Оставлено для явного удаления по запросу пользователя.
        with self.connection:
            user = self.cursor.execute(
                "SELECT * FROM users WHERE telegramId = ?",
                (str(telegramId),)).fetchone()

            deleted_id = 0

            if user is not None:
                deleted_id = user['id']

                # другая функция: delete_payment_records_without_user
                # self.cursor.execute(
                #     'DELETE FROM user_tariff_cs WHERE uid = ?',
                #     (str(user['id']),))
                # self.connection.commit()

                subs = self.cursor.execute(
                    'SELECT * FROM user_channel_cs \
                    WHERE user_telegram_id = ?',
                    (str(telegramId),)).fetchall()
                # удалить все подписки
                self.cursor.execute(
                    'DELETE FROM user_channel_cs WHERE user_telegram_id = ?',
                    (str(telegramId),))
                self.connection.commit()
                # для каждой подписки удалить канал, если у него 0 подписчиков
                for sub in subs:
                    # self.remove_sub(
                    #     telegramId, sub['channel_id'])
                    cc = self.cursor.execute(
                        'SELECT count(*) FROM user_channel_cs \
                        WHERE channel_id = ?',
                        (str(sub['channel_id']),)).fetchone()
                    if cc[0] == 0:
                        # также удалить связь канал-жанр
                        self.cursor.execute(
                            "DELETE FROM genre_to_podcast \
                                WHERE podcast_id = ?",
                            (str(sub['channel_id']),))
                        # само уаление канала
                        self.cursor.execute(
                            'DELETE FROM channels WHERE id = ?',
                            (str(sub['channel_id']),))
                        self.connection.commit()
            if hard:
                self.cursor.execute(
                    'DELETE FROM users WHERE telegramId = ?',
                    (str(telegramId),))
                self.connection.commit()

            print(
                'user deleted ' + str(deleted_id if deleted_id else '')
                + ' ' + str(telegramId) + '; hard: ' + str(hard),
                flush=True)

    # Пометить пользователя удалённым: он перестаёт получать сообщения,
    # но подписки и всё остальное остаётся на месте.
    # Строка не создаётся: chat_id канала сюда тоже прилетает и не должен стать пользователем.
    def mark_user_deleted_tg(self, telegramId) -> bool:
        with self.connection:
            self.cursor.execute(
                'UPDATE users SET deleted_at = ? \
                WHERE telegramId = ? AND deleted_at IS NULL',
                (
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    str(telegramId),))
            marked = self.cursor.rowcount > 0
            self.connection.commit()

            if marked:
                print('user marked as deleted ' + str(telegramId), flush=True)

            return marked

    # Пользователь вернулся: снимаем пометку, всё продолжает работать как раньше
    def restore_user_tg(self, telegramId) -> bool:
        with self.connection:
            self.cursor.execute(
                'UPDATE users SET deleted_at = NULL \
                WHERE telegramId = ? AND deleted_at IS NOT NULL',
                (str(telegramId),))
            restored = self.cursor.rowcount > 0
            self.connection.commit()

            if restored:
                print('user restored ' + str(telegramId), flush=True)

            return restored

    def is_user_deleted_tg(self, telegramId) -> bool:
        with self.connection:
            row = self.cursor.execute(
                'SELECT deleted_at FROM users WHERE telegramId = ?',
                (str(telegramId),)).fetchone()
            return row is not None and row['deleted_at'] is not None

    def count_users(
            self, with_subs=False, with_subs_active=False, payed=False,
            deleted=False, receive_episodes=False, digest_reminder=False
    ) -> int:
        live_bot_sub = (
            'utc.tariff_id > 0 AND utc.time_left > 0 '
            'AND utc.notify_count != 0')
        with self.connection:
            if with_subs:
                # Count users, not subscription rows. EXISTS uses
                # ucc_user_notify_idx; COUNT(DISTINCT) over user_channel_cs
                # scans the whole table and hangs /usersCount in production.
                sql = (
                    'SELECT COUNT(*) FROM users u '
                    'WHERE u.deleted_at IS NULL AND EXISTS ('
                    'SELECT 1 FROM user_channel_cs ucc '
                    'WHERE ucc.user_telegram_id = u.telegramId)')
            elif with_subs_active:
                sql = (
                    'SELECT COUNT(*) FROM users u '
                    'WHERE u.deleted_at IS NULL AND EXISTS ('
                    'SELECT 1 FROM user_channel_cs ucc '
                    'WHERE ucc.user_telegram_id = u.telegramId '
                    'AND ucc.notify = 1)')
            elif receive_episodes:
                # Audio/episode pushes: live tariff AND notify=1 on a podcast.
                sql = (
                    'SELECT COUNT(*) FROM users u '
                    'WHERE u.deleted_at IS NULL AND EXISTS ('
                    'SELECT 1 FROM user_channel_cs ucc '
                    'WHERE ucc.user_telegram_id = u.telegramId '
                    'AND ucc.notify = 1) AND EXISTS ('
                    'SELECT 1 FROM user_tariff_cs utc '
                    'WHERE utc.uid = u.id AND ' + live_bot_sub + ')')
            elif digest_reminder:
                # End-of-circle "you have new episodes" ping: notify=1, no tariff.
                sql = (
                    'SELECT COUNT(*) FROM users u '
                    'WHERE u.deleted_at IS NULL AND EXISTS ('
                    'SELECT 1 FROM user_channel_cs ucc '
                    'WHERE ucc.user_telegram_id = u.telegramId '
                    'AND ucc.notify = 1) AND NOT EXISTS ('
                    'SELECT 1 FROM user_tariff_cs utc '
                    'WHERE utc.uid = u.id AND ' + live_bot_sub + ')')
            elif payed:
                # Same rule as is_user_have_bot_subscription: live tariff
                # with remaining time and notification quota (including -1).
                # COUNT users with EXISTS so a duplicate tariff row cannot
                # inflate the admin number.
                sql = (
                    'SELECT COUNT(*) FROM users u '
                    'WHERE u.deleted_at IS NULL AND EXISTS ('
                    'SELECT 1 FROM user_tariff_cs utc '
                    'WHERE utc.uid = u.id AND ' + live_bot_sub + ')')
            elif deleted:
                sql = (
                    'SELECT COUNT(*) FROM users '
                    'WHERE deleted_at IS NOT NULL')
            else:
                sql = (
                    'SELECT COUNT(*) FROM users '
                    'WHERE deleted_at IS NULL')
            row = self.cursor.execute(sql).fetchone()
            return int(row[0]) if row is not None else 0

    def getTariffs(self, channel_control=None):
        with self.connection:
            sql = "SELECT * FROM tariffs WHERE 1"

            if channel_control is not None:
                sql += " AND channel_control %s" % \
                       ("= 1" if channel_control else "!= 1")

            return self.cursor.execute(sql).fetchall()

    def getTariffById(self, id):
        with self.connection:
            return self.cursor.execute(
                'SELECT * FROM tariffs WHERE id = ?',
                (str(id),)).fetchone()

    def getExtremeTariff(self, extreme='min'):
        with self.connection:
            if extreme == 'min':
                return self.cursor.execute(
                    'SELECT * FROM tariffs ORDER BY level ASC LIMIT 1'
                ).fetchone()
            # extreme == max
            else:
                return self.cursor.execute(
                    'SELECT * FROM tariffs ORDER BY level DESC LIMIT 1'
                ).fetchone()

    def getUserSubscriptionByTg(self, telegramId):
        with self.connection:
            user = self.cursor.execute(
                'SELECT id from users WHERE telegramId = ?',
                (str(telegramId),)).fetchone()
            if user:
                user_id = user['id']
                is_exist = self.cursor.execute(
                    'SELECT * FROM user_tariff_cs WHERE uid = ?',
                    (str(user_id),)).fetchone()
                return is_exist
            else:
                return None

    def getUserSubscriptionByUid(self, user_id):
        with self.connection:
            subscription = self.cursor.execute(
                'SELECT * FROM user_tariff_cs WHERE uid = ?',
                (str(user_id),)).fetchone()
            return subscription

    def getAllSubscription(self):
        with self.connection:
            return self.cursor.execute(
                'SELECT * from user_tariff_cs').fetchall()

    def getPaymentServiceEmail(self, telegramId, service):
        with self.connection:
            query = """
                SELECT psud.email FROM payment_service_user_data AS psud
                INNER JOIN users AS u ON (psud.user_id = u.id)
                WHERE u.telegramId = ? AND service_type = ?
            """
            email = self.cursor.execute(
                query,
                (str(telegramId), service,)).fetchone()

            if email is None:
                return None
            else:
                return email['email']

    def savePaymentServiceEmail(self, telegramId, email, service):
        with self.connection:
            user = self.cursor.execute(
                'SELECT id from users WHERE telegramId = ?',
                (str(telegramId),)).fetchone()
            if user:
                query = """
                    SELECT COUNT(*) AS count
                    FROM payment_service_user_data
                    WHERE user_id = ? AND service_type = ?
                """
                is_exist = self.cursor.execute(
                    query, (str(user['id']), service,)
                ).fetchone()['count'] != 0

                if not is_exist:
                    query = """
                        INSERT INTO payment_service_user_data
                            (user_id, service_type, email, active)
                        VALUES (?, ?, ?, 1)
                    """
                    self.cursor.execute(
                        query, (str(user['id']), service, email,))
                else:
                    query = """
                        UPDATE payment_service_user_data
                        SET email = ?
                        WHERE user_id = ? AND service_type = ?
                    """
                    self.cursor.execute(
                        query, (email, str(user['id']), service,))

                self.connection.commit()

    def updatePaymentServiceLastReplenishment(
            self, user_id, service, last_replenishment
    ):
        with self.connection:
            self.cursor.execute(
                "UPDATE payment_service_user_data SET last_replenishment = ? \
                WHERE user_id = ? AND service_type = ?",
                (last_replenishment, user_id, service))
            self.connection.commit()

    def getPaymentDataByService(self, service):
        with self.connection:
            return self.cursor.execute(
                "SELECT * FROM payment_service_user_data").fetchall()

    def findInvoice(self, tgId, serviceType, invoiceId, invoiceHash=None):
        with self.connection:
            query = """
                SELECT * FROM payment_history AS ph
                WHERE ph.user_id = ? AND ph.service_type = ?
                    AND ph.invoice_id = ?{invoiceHashCondition}
            """
            params = (str(tgId), str(serviceType), str(invoiceId),)

            if invoiceHash:
                query = query.format(
                    invoiceHashCondition=" AND ph.invoice_hash = ?")
                params += (str(invoiceHash),)
            else:
                query = query.format(invoiceHashCondition="")

            return self.cursor.execute(query, params).fetchone()

    def createInvoice(
            self, tgId, serviceType, invoiceId, paidAt,
            invoiceHash=None, status=None, amount=None
    ):

        with self.connection:
            query = """
                INSERT INTO payment_history
                    (user_id, service_type, invoice_id, invoice_hash,
                    status, amount, datetime)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            self.cursor.execute(
                query,
                (str(tgId), str(serviceType), str(invoiceId), invoiceHash,
                 status,
                 int(amount) if amount is not None else amount,
                 str(paidAt),))

        return self.findInvoice(
            tgId, serviceType, invoiceId, invoiceHash=invoiceHash)

    def applyPaymentReplenishmentOnce(
            self, user, serviceType, invoiceId, paidAt, amountCents,
            tariff_period, invoiceHash=None, status=None
    ):
        try:
            self.cursor.execute("BEGIN IMMEDIATE")
            user_id = user['id']
            telegram_id = user['telegramId']

            invoice = self.cursor.execute(
                """
                    SELECT * FROM payment_history
                    WHERE user_id = ? AND service_type = ? AND invoice_id = ?
                """,
                (str(user_id), str(serviceType), str(invoiceId),)).fetchone()
            if invoice is not None:
                self.connection.commit()
                return {
                    'already_processed': True,
                    'invoice': invoice
                }

            current_subscription_row = self.cursor.execute(
                'SELECT * FROM user_tariff_cs WHERE uid = ?',
                (str(user_id),)).fetchone()

            if current_subscription_row is None:
                current_subscription = None
                current_tariff = None
            else:
                current_subscription = {
                    'id': current_subscription_row['id'],
                    'uid': current_subscription_row['uid'],
                    'tariff_id': current_subscription_row['tariff_id'],
                    'balance': current_subscription_row['balance'],
                    'time_left': current_subscription_row['time_left'],
                    'notify_count': current_subscription_row['notify_count']
                }
                current_tariff = self.cursor.execute(
                    'SELECT * FROM tariffs WHERE id = ?',
                    (str(current_subscription['tariff_id']),)).fetchone()

            if current_tariff is None:
                current_tariff = {
                    'id': 0, 'level': 0, 'price': 0,
                    'notify_count': 0, 'compression': 0
                }

            if current_subscription is None or current_subscription.get('id') == 0:
                tariff_id = 0
                new_balance = int(amountCents)
                new_time_left = 0
                new_notify_count = 0
                current_subscription = {
                    'balance': new_balance,
                    'time_left': new_time_left,
                    'notify_count': new_notify_count
                }
                result_mode = 0
                self.cursor.execute(
                    """
                        INSERT INTO user_tariff_cs
                            (uid, tariff_id, balance, time_left, notify_count)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                    (str(user_id), str(tariff_id), str(new_balance),
                     str(new_time_left), str(new_notify_count),))

            elif current_subscription['time_left'] > 0:
                new_balance = current_subscription['balance'] + int(amountCents)
                new_time_left = current_subscription['time_left']
                new_notify_count = current_subscription['notify_count']
                self.cursor.execute(
                    """
                        UPDATE user_tariff_cs
                        SET balance = ?, time_left = ?, notify_count = ?
                        WHERE uid = ?
                    """,
                    (str(new_balance), str(new_time_left),
                     str(new_notify_count), str(user_id),))
                current_subscription['balance'] = new_balance
                result_mode = 1

            else:
                new_balance = current_subscription['balance'] + int(amountCents)
                new_time_left = current_subscription['time_left']
                new_notify_count = 0

                if current_tariff['price'] != 0 and new_balance >= current_tariff['price']:
                    new_balance -= current_tariff['price']
                    new_time_left = tariff_period
                    new_notify_count = current_tariff['notify_count']
                    result_mode = 2
                elif current_tariff['price'] != 0:
                    result_mode = 3
                else:
                    result_mode = 0

                self.cursor.execute(
                    """
                        UPDATE user_tariff_cs
                        SET balance = ?, time_left = ?, notify_count = ?
                        WHERE uid = ?
                    """,
                    (str(new_balance), str(new_time_left),
                     str(new_notify_count), str(user_id),))
                current_subscription['balance'] = new_balance
                current_subscription['time_left'] = new_time_left
                current_subscription['notify_count'] = new_notify_count

            self.cursor.execute(
                """
                    INSERT INTO payment_history
                        (user_id, service_type, invoice_id, invoice_hash,
                         status, amount, datetime)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(user_id), str(serviceType), str(invoiceId), invoiceHash,
                 status, int(amountCents) if amountCents is not None else amountCents,
                 str(paidAt),))
            self.connection.commit()

            return {
                'already_processed': False,
                'result_mode': result_mode,
                'current_tariff': current_tariff,
                'current_subscription': current_subscription,
                'telegram_id': telegram_id
            }
        except Exception:
            self.connection.rollback()
            raise

    def subscribeUserToTariffByTg(
            self, telegram_id, tariff_id, balance, time_left, notify_count):
        with self.connection:
            user_id = self.cursor.execute(
                'SELECT id from users WHERE telegramId = ?',
                (str(telegram_id),)).fetchone()['id']
        self.subscribeUserToTariffByUid(
            user_id, tariff_id, balance, time_left, notify_count)

    def subscribeUserToTariffByUid(
            self, user_id, tariffId, balance, time_left, notify_count):
        with self.connection:
            is_exist = self.cursor.execute(
                'SELECT * FROM user_tariff_cs WHERE uid = ?',
                (str(user_id),)).fetchall()
            if len(is_exist) == 0:
                if notify_count is None:
                    if tariffId != 0:
                        notify_count = self.cursor.execute(
                            "SELECT notify_count FROM tariffs WHERE id = ?",
                            (str(tariffId),)).fetchone()['notify_count']
                    else:
                        notify_count = 0
                self.cursor.execute(
                    'INSERT INTO user_tariff_cs \
                        (uid, tariff_id, balance, time_left, notify_count) \
                    VALUES (?, ?, ?, ?, ?)',
                    (str(user_id), str(tariffId), str(balance),
                     str(time_left), str(notify_count),))
            else:
                self.cursor.execute(
                    'UPDATE user_tariff_cs \
                    SET tariff_id = ?, balance = ?, \
                        time_left = ?, notify_count = ? \
                    WHERE uid = ?',
                    (str(tariffId), str(balance), str(time_left),
                     str(notify_count), str(user_id),))
            self.connection.commit()

    def decrease_all_time_left(self):
        # Подписка помеченного удалённым заморожена: он ничего не получает, поэтому
        # его дни не должны сгорать. Когда он вернётся, отсчёт продолжится с того же места.
        with self.connection:
            self.cursor.execute(
                "UPDATE user_tariff_cs \
                SET time_left = time_left - 1\
                WHERE time_left > 0 AND tariff_id != 0\
                    AND NOT EXISTS (SELECT 1 FROM users u \
                        WHERE u.id = user_tariff_cs.uid \
                            AND u.deleted_at IS NOT NULL)")
            self.connection.commit()

    def get_users_who_can_be_prolonged(self):
        with self.connection:
            sql = """
                SELECT utc.balance, u.telegramId, u.lang,
                    t.price as tprice, t.level AS tlevel, t.notify_count as tnc
                FROM user_tariff_cs utc
                INNER JOIN tariffs t ON t.id = utc.tariff_id
                INNER JOIN users u ON u.id = utc.uid
                WHERE utc.balance >= t.price AND utc.time_left = 0
                    AND u.deleted_at IS NULL
                ORDER BY u.lang
            """
            return self.cursor.execute(sql).fetchall()

    def get_users_who_cannot_be_prolonged(self):
        with self.connection:
            sql = """
                SELECT utc.balance, u.telegramId, u.lang,
                    t.id as tid, t.price as tprice, t.level AS tlevel,
                    t.notify_count as tnc
                FROM user_tariff_cs utc
                INNER JOIN tariffs t ON t.id = utc.tariff_id
                INNER JOIN users u ON u.id = utc.uid
                WHERE utc.balance < t.price AND utc.time_left = 1
                    AND u.deleted_at IS NULL
                ORDER BY u.lang
            """
            return self.cursor.execute(sql).fetchall()

    def prolong_users(self, tariff_period):
        # Помеченного удалённым не продлеваем: списывать с баланса за выпуски,
        # которые ему всё равно не отправляются, нельзя. Тот же фильтр стоит в
        # get_users_who_can_be_prolonged, и условия обязаны совпадать — иначе
        # деньги списываются, а уведомление о списании не уходит.
        with self.connection:
            sql = """
                UPDATE user_tariff_cs
                SET time_left = time_left + ?,
                    balance = balance - (
                        SELECT price FROM tariffs
                        WHERE tariffs.id = user_tariff_cs.tariff_id),
                    notify_count = (
                        SELECT notify_count FROM tariffs
                        WHERE tariffs.id = user_tariff_cs.tariff_id)
                WHERE balance >= (
                    SELECT price FROM tariffs
                    WHERE tariffs.id = user_tariff_cs.tariff_id
                ) AND time_left = 0
                    AND NOT EXISTS (
                        SELECT 1 FROM users u
                        WHERE u.id = user_tariff_cs.uid
                            AND u.deleted_at IS NOT NULL)
            """
            self.cursor.execute(sql, (str(tariff_period),))
            rowcount = self.cursor.rowcount
            self.connection.commit()
            return rowcount

    def decrease_notify_count(self, telegramId, count):
        with self.connection:
            self.cursor.execute(
                "UPDATE user_tariff_cs \
                SET notify_count = notify_count - ? \
                WHERE uid = (SELECT id FROM users WHERE telegramId = ?) \
                    AND notify_count > 0",
                (str(count), str(telegramId),))
            self.connection.commit()

    def delete_payment_records_without_user(self):
        with self.connection:
            self.cursor.execute(
                "DELETE FROM user_tariff_cs \
                WHERE time_left = 0 AND uid NOT IN (SELECT id FROM users) \
                    AND balance < (SELECT MAX(price) FROM tariffs)")
            self.connection.commit()

    def get_genre(self, genreId):
        with self.connection:
            return self.cursor.execute(
                "SELECT * FROM genres WHERE id = ?", (str(genreId),)
            ).fetchone()

    # !!!
    # работа с категорями, топом
    top_rate_limit = 0
    top_count_limit = 0

    def get_genre_codes_from_orig_search(self, language_code: str, original_request: str) -> tuple[str, tuple]:
        found_results = []
        genres_dict = typing_cast(dict, routed_messages.get('genres', {}))
        for genre in genres_dict:
            if original_request.lower() in get_message_rtd(['genres', genre], language_code).lower():
                found_results.append(genre)

        conditions = ["LOWER_UNICODE(g.name) LIKE LOWER_UNICODE(?)"]
        genre_params = ()
        for genre_code in found_results:
            conditions.append("LOWER_UNICODE(g.name) LIKE LOWER_UNICODE(?)")
            genre_params += (genre_code,)
        return "(" + " OR ".join(conditions) + ")", genre_params

    # количество жанров, выводимых в топе
    def select_genres_count(self, lang_code: str, lang_top: bool, search: str | None = None):
        with self.connection:
            # топ по языкам
            if lang_top:
                lang_inner = "INNER JOIN users AS u \
                            ON (u.telegramId = ucc.user_telegram_id)"
                lang_where = "AND u.lang = ?"
                params = (str(lang_code),)
            else:
                lang_inner = ""
                lang_where = ""
                params = ()

            if search is not None:
                params += ("%" + search + "%",)
                genre_sql, genre_params = self.get_genre_codes_from_orig_search(lang_code, search)
                search_query = "WHERE " + genre_sql
                params += genre_params
            else:
                search_query = ""

            query = """
                SELECT COUNT(DISTINCT g.id) AS count
                FROM genres AS g
                INNER JOIN genre_to_podcast AS gtp ON (g.id = gtp.genre_id)
                INNER JOIN (
                    SELECT COUNT(*) AS rates_count, AVG(ucc.rate) AS rate,
                        ucc.channel_id
                    FROM user_channel_cs AS ucc
                    %s
                    WHERE ucc.rate IS NOT NULL %s
                    GROUP BY ucc.channel_id
                    HAVING rates_count > %d AND rate > %d
                ) AS ucc ON (ucc.channel_id = gtp.podcast_id)
                %s
            """ % (
                lang_inner, lang_where,
                self.top_count_limit, self.top_rate_limit,
                search_query
            )

            # The first button – is the general top, so we need to take into attention
            return int(self.cursor.execute(query, params).fetchone()['count']) + 1

    # жанры, выводимые в топе
    def select_genres(
            self, lang_code: str, lang_top: bool, search: str | None = None,
            _: str | None = None, limit: int = 5, offset: int = 0):
        # The first button – is the general top, so we need to take into attention
        if offset == 0:
            limit -= 1
        else:
            offset -= 1

        with self.connection:
            # топ по языкам
            if lang_top:
                lang_inner = "INNER JOIN users AS u \
                            ON (u.telegramId = ucc.user_telegram_id)"
                lang_where = "AND u.lang = ?"
                params = (str(lang_code),)
            else:
                lang_inner = ""
                lang_where = ""
                params = ()

            if search is not None:
                params += ("%" + search + "%",)
                genre_sql, genre_params = self.get_genre_codes_from_orig_search(lang_code, search)
                search_query = "WHERE " + genre_sql
                params += genre_params
            else:
                search_query = ""

            query = """
                SELECT
                    g.id as id,
                    g.name as name,
                    SUM(ucc.rates_count) as count_podcasts_popularity
                FROM genres AS g
                INNER JOIN genre_to_podcast AS gtp ON (g.id = gtp.genre_id)
                INNER JOIN (
                    SELECT COUNT(*) AS rates_count, AVG(ucc.rate) AS rate,
                        channel_id
                    FROM user_channel_cs AS ucc
                    %s
                    WHERE rate IS NOT NULL %s
                    GROUP BY channel_id
                    HAVING rates_count > %d AND rate > %d
                ) AS ucc ON (ucc.channel_id = gtp.podcast_id)
                %s
                GROUP BY g.id
                ORDER BY count_podcasts_popularity DESC
                LIMIT %d OFFSET %d
            """ % (
                lang_inner, lang_where,
                self.top_count_limit, self.top_rate_limit,
                search_query,
                limit, offset
            )

            return self.cursor.execute(query, params).fetchall()

    # количество каналов в топе
    def select_top_count(self, genre_id, lang_code, lang_top: bool, search: str | None = None):
        with self.connection:
            # языковой топ
            if lang_top:
                lang_inner = "INNER JOIN users AS u \
                            ON (u.telegramId = ucc.user_telegram_id)"
                lang_where = "AND u.lang = ?"
                params = (str(lang_code),)
            else:
                lang_inner = ""
                lang_where = ""
                params = ()

            if genre_id is not None and int(genre_id) > 0:
                genre_on = "AND gpt.genre_id = ?"
                params += (str(genre_id),)
            else:
                genre_on = ""

            if search is not None:
                search_query = " AND LOWER_UNICODE(ch.name) LIKE LOWER_UNICODE(?)"
                params += ("%" + search + "%",)
            else:
                search_query = ""

            query = """
                SELECT COUNT(DISTINCT ch.id) AS count
                FROM channels AS ch
                INNER JOIN (
                    SELECT COUNT(*) AS rates_count, AVG(ucc.rate) AS rate,
                        channel_id
                    FROM user_channel_cs AS ucc
                    %s
                    WHERE ucc.rate IS NOT NULL %s
                    GROUP BY ucc.channel_id
                ) AS ucc ON (ucc.channel_id = ch.id)
                INNER JOIN genre_to_podcast AS gpt ON (
                    gpt.podcast_id = ch.id %s)
                WHERE ucc.rates_count > %d AND ucc.rate > %d
                %s
            """ % (
                lang_inner, lang_where, genre_on,
                self.top_count_limit, self.top_rate_limit,
                search_query
            )

            return int(self.cursor.execute(query, params).fetchone()['count'])

    # подкасты в топе
    def select_top(self, genre_id, lang_code, lang_top: bool, search: str | None = None,
            _: str | None = None, limit: int = 5, offset: int = 0):
        with self.connection:
            # языковой топ
            if lang_top:
                lang_inner = "INNER JOIN users AS u \
                            ON (u.telegramId = ucc.user_telegram_id)"
                lang_where = "AND u.lang = ?"
                params = (str(lang_code),)
            else:
                lang_inner = ""
                lang_where = ""
                params = ()

            if genre_id is not None and int(genre_id) > 0:
                genre_on = "AND gpt.genre_id = ?"
                params += (str(genre_id),)
            else:
                genre_on = ""

            if search is not None:
                search_query = " AND LOWER_UNICODE(ch.name) LIKE LOWER_UNICODE(?)"
                params += ("%" + search + "%",)
            else:
                search_query = ""

            query = """
                SELECT ch.id, ch.name, ucc.rate, ucc.rates_count
                FROM channels AS ch
                INNER JOIN (
                    SELECT COUNT(*) AS rates_count,
                        ROUND(AVG(ucc.rate), 1) AS rate,
                        channel_id
                    FROM user_channel_cs AS ucc
                    %s
                    WHERE ucc.rate IS NOT NULL %s
                    GROUP BY ucc.channel_id
                ) AS ucc ON (ucc.channel_id = ch.id)
                INNER JOIN genre_to_podcast AS gpt ON (
                    gpt.podcast_id = ch.id %s)
                WHERE ucc.rates_count > %d AND ucc.rate > %d
                %s
                GROUP BY ch.id
                ORDER BY rate DESC, ucc.rates_count DESC
                LIMIT %d OFFSET %d
            """ % (
                lang_inner, lang_where, genre_on,
                self.top_count_limit, self.top_rate_limit,
                search_query,
                limit, offset)

            return self.cursor.execute(query, params).fetchall()

    # каналы пользователя в tg
    def get_user_tg_channels(self, chat_id, order_by, limit, offset):
        with self.connection:
            limit_sql = f"LIMIT {limit} OFFSET {offset}"
            query = """
                SELECT ch.id, ch.tg_id, ch.active,
                    count(sttcc.tg_channel_id) as podcast_count
                FROM tg_channels AS ch
                LEFT JOIN subscription_to_tg_channel_cs AS sttcc ON (
                    sttcc.tg_channel_id = ch.id)
                WHERE ch.user_id = ?
                GROUP BY ch.id, ch.tg_id
                %s
                %s
            """ % (order_by, limit_sql)

            return self.cursor.execute(query, (str(chat_id),)).fetchall()

    # количество каналов пользователя в tg
    def get_user_tg_channels_count(self, chat_id):
        with self.connection:
            query = """
                SELECT COUNT(DISTINCT ch.id) as count
                FROM tg_channels AS ch
                WHERE ch.user_id = ?
            """

            return self.cursor.execute(query, (str(chat_id),)).fetchone()[0]

    # добавлен ли tg канал
    def isTgChannelAlreadyAdded(self, chat_id, channel_id):
        with self.connection:
            query = """
                SELECT id FROM tg_channels
                WHERE user_id = ? AND tg_id = ?
            """

            data = self.cursor.execute(
                query, (str(chat_id), str(channel_id),)).fetchone()

            if data is not None:
                return True
            else:
                return False

    # добавить или обновить tg канал
    def addOrUpdateTgChannel(self, chat_id, channel_id, active=True):
        with self.connection:
            is_exist = len(self.cursor.execute(
                'SELECT * FROM tg_channels \
                WHERE user_id = ? AND tg_id = ?',
                (str(chat_id), str(channel_id),)).fetchall()) != 0

            active_int = (1 if active else 0)

            if not is_exist:
                self.cursor.execute(
                    'INSERT INTO tg_channels \
                        (user_id, tg_id, active) \
                    VALUES (?, ?, ?)',
                    (str(chat_id), str(channel_id), str(active_int),))
            else:
                self.cursor.execute(
                    'UPDATE tg_channels \
                    SET active = ? \
                    WHERE user_id = ? AND tg_id = ?',
                    (str(active_int), str(chat_id), str(channel_id)))
            self.connection.commit()

    # получить tg owner id по tg channel id
    def getUserTgIdByChannelTg(self, chat_id):
        with self.connection:
            query = """
                SELECT user_id FROM tg_channels
                WHERE tg_id = ?
            """
            return self.cursor.execute(
                query, (str(chat_id),)).fetchone()['user_id']

    # получить tg канал
    def getTgChannelDataById(self, chat_id, channel_id):
        with self.connection:
            query = """
                SELECT ch.id, ch.user_id, ch.tg_id, ch.active,
                    count(sttcc.tg_channel_id) as podcast_count
                FROM tg_channels AS ch
                LEFT JOIN subscription_to_tg_channel_cs AS sttcc ON (
                    sttcc.tg_channel_id = ch.id)
                WHERE ch.user_id = ? AND ch.id = ?
                GROUP BY ch.id
            """

            data = self.cursor.execute(
                query, (str(chat_id), str(channel_id),)).fetchone()

            if data:
                data = {
                    "id": data["id"], "user_id": data["user_id"],
                    "tg_id": data["tg_id"],
                    "active": (True if data["active"] else False),
                    "podcast_count": data["podcast_count"]
                }

            return data

    # получить tg канал по tg id
    def getTgChannelDataByTgId(self, chat_id, channel_tg_id):
        with self.connection:
            query = """
                SELECT ch.id, ch.user_id, ch.tg_id, ch.active,
                    count(sttcc.tg_channel_id) as podcast_count
                FROM tg_channels AS ch
                LEFT JOIN subscription_to_tg_channel_cs AS sttcc ON (
                    sttcc.tg_channel_id = ch.id)
                WHERE ch.user_id = ? AND ch.tg_id = ?
                GROUP BY ch.id
            """

            data = self.cursor.execute(
                query, (str(chat_id), str(channel_tg_id),)).fetchone()

            if data:
                data = {
                    "id": data["id"], "user_id": data["user_id"],
                    "tg_id": data["tg_id"],
                    "active": (True if data["active"] else False),
                    "podcast_count": data["podcast_count"]
                }

            return data

    def changeTgChannelToPodcastConnect(self, chat_id, channel_id, podcast_id):
        with self.connection:
            query = """
                SELECT ucc.id,
                    CASE WHEN sttcc.tg_channel_id IS NOT NULL
                        THEN 1 ELSE 0 END AS connected
                FROM user_channel_cs AS ucc
                LEFT JOIN subscription_to_tg_channel_cs AS sttcc
                    ON (
                        sttcc.user_channel_cs_id = ucc.id
                        AND sttcc.tg_channel_id = ?)
                WHERE
                    ucc.user_telegram_id = ? AND ucc.channel_id = ?
            """

            connection = self.cursor.execute(
                query,
                (str(channel_id), str(chat_id), str(podcast_id),)).fetchone()

            # связи нет
            if connection is None:
                return False

            if int(connection['connected']) == 1:
                self.cursor.execute(
                    'DELETE FROM subscription_to_tg_channel_cs WHERE \
                    user_channel_cs_id = ? AND tg_channel_id = ?',
                    (
                        str(connection['id']),
                        str(channel_id),))
                self.connection.commit()

                return "deleted"
            else:
                self.cursor.execute(
                    'INSERT INTO subscription_to_tg_channel_cs \
                    (user_channel_cs_id, tg_channel_id) \
                    VALUES (?, ?)',
                    (str(connection['id']), str(channel_id),))
                self.connection.commit()

                return "created"

    # получить подписки юзера со связью с каналами
    def select_users_subs_name_tg_channel(self, telegramId, tgChId, search, order_by, limit, offset):
        with self.connection:
            limit_sql = f"LIMIT {limit} OFFSET {offset}"
            params = (str(tgChId), str(telegramId),)

            if search is not None:
                params += ("%" + search + "%",)
                search_query = " AND LOWER_UNICODE(channels.name) LIKE LOWER_UNICODE(?)"
            else:
                search_query = ""

            query = """SELECT
                        channels.id as id,
                        channels.name as name,
                        CASE WHEN sttcc.tg_channel_id IS NOT NULL
                            THEN 1 ELSE 0 END AS connected
                    FROM user_channel_cs
                    LEFT JOIN channels
                        ON user_channel_cs.channel_id = channels.id
                    LEFT JOIN subscription_to_tg_channel_cs AS sttcc
                        ON (
                            sttcc.user_channel_cs_id = user_channel_cs.id
                            AND sttcc.tg_channel_id = ?
                        )
                    WHERE user_channel_cs.user_telegram_id = ? %s
                    %s
                    %s""" % (search_query, order_by, limit_sql)

            return self.cursor.execute(query,params).fetchall()

    def deleteTgChannel(self, chat_id, channel_id):
        with self.connection:
            # удаление канала
            self.cursor.execute(
                'DELETE FROM tg_channels WHERE \
                id = ? AND user_id = ?',
                (str(channel_id), str(chat_id),))
            self.connection.commit()

            # удаление связей
            self.cursor.execute(
                'DELETE FROM subscription_to_tg_channel_cs \
                WHERE tg_channel_id = ? AND user_channel_cs_id IN \
                (SELECT id FROM user_channel_cs WHERE user_telegram_id = ?)',
                (str(channel_id), str(chat_id),))
            self.connection.commit()

    # получить связи канал-подкаст по id подкаста
    # формат аналогичен get_uccs_by_channel, для podcastUpdater
    def getTgChannelSubConnectionsByPodcast(
            self, channel_id,
            notifications_enabled=None, have_subscription=None):
        with self.connection:
            query = """SELECT uc.id,
                        tc.tg_id AS user_telegram_id,
                        uc.channel_id, uc.last_guid, uc.last_date,
                        tc.active AS notify,
                        uc.rate,
                        ut.notify_count,
                        -- только для каналов
                        'channel' AS user_type,
                        uc.user_telegram_id AS owner_id
                    FROM user_channel_cs AS uc
                    INNER JOIN subscription_to_tg_channel_cs AS sttcc
                        ON (sttcc.user_channel_cs_id = uc.id)
                    INNER JOIN tg_channels AS tc
                        ON (tc.id = sttcc.tg_channel_id)
                    LEFT JOIN user_tariff_cs AS ut ON ut.uid = (SELECT id
                        FROM users AS u
                        WHERE u.telegramId = uc.user_telegram_id)
                    LEFT JOIN tariffs AS t ON t.id = ut.tariff_id
                    WHERE uc.channel_id = ?"""
            if have_subscription is not None:
                if have_subscription:
                    query += " AND ( \
                        ut.notify_count != 0 \
                            AND ut.time_left > 0 \
                            AND t.channel_control = 1)"
                else:
                    query += " AND ( \
                        ut.notify_count = 0 \
                            OR ut.time_left = 0 \
                            OR ut.tariff_id = 0)"
            if notifications_enabled is not None:
                if notifications_enabled:
                    query += " AND tc.active = 1"
                else:
                    query += " AND tc.active = 0"
            return self.cursor.execute(query, (str(channel_id),)).fetchall()

    # # получить связи канал-подкаст по id пользователя в tg
    # # формат аналогичен get_uccs_by_channel, для podcastUpdater
    # def getTgChannelSubConnectionsByUserTg(
    #         self, telegramId,
    #         notifications_enabled=True, have_subscription=None):
    #     with self.connection:
    #         query = """SELECT uc.id,
    #                     tc.tg_id AS user_telegram_id,
    #                     uc.channel_id, uc.last_guid, uc.last_date,
    #                     tc.active AS notify,
    #                     uc.rate,
    #                     ut.notify_count,
    #                     -- только для каналов
    #                     'channel' AS user_type,
    #                     uc.user_telegram_id AS owner_id
    #                 FROM user_channel_cs AS uc
    #                 INNER JOIN subscription_to_tg_channel_cs AS sttcc
    #                     ON (sttcc.user_channel_cs_id = uc.id)
    #                 INNER JOIN tg_channels AS tc
    #                     ON (tc.id = sttcc.tg_channel_id)
    #                 LEFT JOIN user_tariff_cs AS ut ON ut.uid = (SELECT id
    #                     FROM users AS u
    #                     WHERE u.telegramId = uc.user_telegram_id)
    #                 WHERE uc.user_telegram_id = ?"""
    #         if have_subscription is not None:
    #             if have_subscription:
    #                 query += " AND ( \
    #                     ut.notify_count != 0 \
    #                         AND ut.time_left > 0 \
    #                         AND ut.tariff_id = %i)" \
    #                 % tgChannelsNeedableTariffLvl
    #             else:
    #                 query += " AND ( \
    #                     ut.notify_count = 0 \
    #                         OR ut.time_left = 0 \
    #                         OR ut.tariff_id = 0)"
    #         if notifications_enabled:
    #             query += " AND tc.active = 1"
    #         return self.cursor.execute(query, (str(telegramId),)).fetchall()

    # закрытие
    def close(self):
        """ Закрываем текущее соединение с БД """
        if self.cursor is not None:
            self.cursor.close()
        if self.connection is not None:
            self.connection.close()
        self.cursor = None
        self.connection = None
