# -*- coding: utf-8 -*-
import sqlite3
import re
from typing import Any, cast as typing_cast

from app.i18n.messages import routed_messages, get_message_rtd
from config import (
    max_subscriptions_without_tariff)

from db.dbTypes import UserDBType

from lib.tools.logger import logger


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
        self.connection = sqlite3.connect(database, timeout=10)
        self.connection.create_function("LOWER_UNICODE", 1, self.__lower_unicode)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()

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
            hncq = self.cursor.execute(
                """
                    SELECT COUNT(*) AS channel_with_new_episodes
                    FROM user_channel_cs
                    INNER JOIN channels
                        ON user_channel_cs.channel_id = channels.id
                    WHERE user_channel_cs.user_telegram_id = ?
                        AND channels.last_guid IS NOT NULL
                        AND channels.last_date IS NOT NULL
                        AND (
                            channels.last_guid != user_channel_cs.last_guid
                            AND channels.last_date > user_channel_cs.last_date
                        )
                """,
                (str(telegramId),)).fetchone()
            return hncq["channel_with_new_episodes"] > 0

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

    def get_channel_or_next(self, channel_id, channel_set=[]):
        with self.connection:
            if channel_set == []:
                return self.cursor.execute(
                    "SELECT * FROM channels WHERE id >= ? LIMIT 1",
                    (str(channel_id),)).fetchone()
            else:
                return self.cursor.execute(
                    "SELECT * FROM channels WHERE id >= ? \
                    AND id IN (" + ','.join(channel_set) + ")\
                    LIMIT 1",
                    (str(channel_id),)).fetchone()

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

    def get_uccs_by_channel(
            self, channel_id,
            notifications_enabled=None, have_subscription=None):
        with self.connection:
            query = "SELECT uc.*, ut.notify_count \
                    FROM user_channel_cs uc \
                    LEFT JOIN user_tariff_cs ut ON ut.uid = (SELECT id \
                        FROM users u \
                        WHERE u.telegramId = uc.user_telegram_id) \
                    WHERE channel_id = ?"
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
                        'INSERT INTO users (telegramId, lang, ref_id) \
                        VALUES (?, ?, ?)',
                        (str(telegram_id), str(user_lang), str(refer_id),))
                    by_refer = True
                else:
                    self.cursor.execute(
                        'INSERT INTO users (telegramId, lang) \
                        VALUES (?, ?)',
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

    def get_all_users(self, language: str | None = None) -> list[UserDBType]:
        with self.connection:
            query = 'SELECT * FROM users'
            if language is not None:
                query += f" WHERE lang = '{language}'"
            return self.cursor.execute(query).fetchall()

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
                    'INSERT INTO users (telegramId) VALUES (?)',
                    (str(telegramId),))
                self.connection.commit()
                return self.cursor.execute(
                    'SELECT * FROM users WHERE telegramId = ?',
                    (str(telegramId),)).fetchall()[0]

    def delete_user_tg(self, telegramId, hard=True):
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

    def count_users(
            self, with_subs=False, with_subs_active=False, payed=False
    ):
        with self.connection:
            if with_subs:
                return self.cursor.execute(
                    'SELECT COUNT(DISTINCT ucc.user_telegram_id)\
                    FROM user_channel_cs ucc\
                    INNER JOIN users u\
                        ON (u.telegramId = ucc.user_telegram_id)'
                ).fetchall()[0]
            elif with_subs_active:
                return self.cursor.execute(
                    'SELECT COUNT(DISTINCT ucc.user_telegram_id)\
                    FROM user_channel_cs ucc\
                    INNER JOIN users u\
                        ON (u.telegramId = ucc.user_telegram_id\
                            AND ucc.notify = 1)'
                ).fetchall()[0]

            elif payed:
                return self.cursor.execute(
                    'SELECT count(*) FROM user_tariff_cs\
                    WHERE tariff_id > 0\
                        AND time_left > 0 AND notify_count != 0').fetchone()
            else:
                return self.cursor.execute(
                    'SELECT COUNT(*) FROM users').fetchall()[0]

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
        with self.connection:
            self.cursor.execute(
                "UPDATE user_tariff_cs \
                SET time_left = time_left - 1\
                WHERE time_left > 0 AND tariff_id != 0")
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
                ORDER BY u.lang
            """
            return self.cursor.execute(sql).fetchall()

    def prolong_users(self, tariff_period):
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

    def get_genre_codes_from_orig_search(self, language_code: str, original_request: str):
        found_results = []
        genres_dict = typing_cast(dict, routed_messages.get('genres', {}))
        for genre in genres_dict:
            if original_request.lower() in get_message_rtd(['genres', genre], language_code).lower():
                found_results.append(genre)

        search_query = "LOWER_UNICODE(g.name) LIKE LOWER_UNICODE(?)"
        for genre_code in found_results:
            search_query += f" OR LOWER_UNICODE(g.name) LIKE LOWER_UNICODE('{genre_code}')"
        return "(" + search_query + ")"

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
                search_query = "WHERE " + self.get_genre_codes_from_orig_search(lang_code, search)
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
                search_query = "WHERE " + self.get_genre_codes_from_orig_search(lang_code, search)
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
