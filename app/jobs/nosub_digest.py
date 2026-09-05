# -*- coding: utf-8 -*-
"""No-tariff digest: 'you have new episodes' for users without a bot tariff.

Paid users get the audio in send_new_records_by_channel. Users with
notify=1 but no bot tariff are only flagged into digest_outbox; the jobs
process drains that queue so the RSS circle is not blocked.

Last-sent and opt-out are columns on users (durable, like other account
prefs). Leftover runtime_kv flags are migrated once into digest_outbox.
"""
import datetime

DIGEST_COOLDOWN = datetime.timedelta(days=7)
DIGEST_MUTE_ACTION = "digestMute"
DIGEST_TOGGLE_ACTION = "digestToggle"


def is_missing_guid(value) -> bool:
    return value in (None, '', 'None')


def _user_field(user, name, default=None):
    if user is None:
        return default
    try:
        return user[name]
    except (KeyError, IndexError, TypeError):
        return default


def parse_digest_sent_at(value):
    if is_missing_guid(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text[:19] if fmt != "%Y-%m-%d" else text[:10], fmt)
        except ValueError:
            continue
    try:
        parsed = datetime.datetime.fromisoformat(text)
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def digest_enabled(user) -> bool:
    value = _user_field(user, "nosub_digest_enabled", 1)
    if value is None:
        return True
    try:
        return int(value) != 0
    except (TypeError, ValueError):
        return True


def digest_is_due(sent_at, now=None, cooldown=DIGEST_COOLDOWN) -> bool:
    parsed = parse_digest_sent_at(sent_at)
    if parsed is None:
        return True
    if now is None:
        now = datetime.datetime.utcnow()
    return now - parsed >= cooldown


def should_send_nosub_digest(user, now=None) -> bool:
    if user is None:
        return False
    if _user_field(user, "deleted_at") is not None:
        return False
    if not digest_enabled(user):
        return False
    return digest_is_due(_user_field(user, "nosub_digest_sent_at"), now=now)


def should_skip_item_parse(target_connections, feed_last_date) -> bool:
    """Skip RSS items only when there are paid/channel targets and all are current.

    An empty target list must not skip: otherwise nosubs-only podcasts never
    reach the digest (vacuous 'all current').
    """
    if not target_connections:
        return False
    if is_missing_guid(feed_last_date):
        return False
    for connection in target_connections:
        if feed_last_date != connection['last_date']:
            return False
    return True


def latest_episode_id(channel, fallback_connections=None):
    guid = None
    if channel is not None:
        try:
            guid = channel['last_guid']
        except (KeyError, IndexError, TypeError):
            guid = None
    if is_missing_guid(guid) and fallback_connections:
        guid = fallback_connections[0]['last_guid']
    if is_missing_guid(guid):
        return None
    return guid


def for_each_digest_user(user_tg_ids, handle_user, on_error=None, pause=None):
    """Call handle_user for each flagged chat. One failure does not stop the rest."""
    for user_tg_id in user_tg_ids:
        try:
            handle_user(user_tg_id)
        except Exception as e:
            if on_error is not None:
                on_error(user_tg_id, e)
        if pause is not None:
            pause()


def nosub_users_behind(nosub_last_guids, latest_pgd):
    """Telegram ids whose saved last_guid is not the latest episode on this channel."""
    if is_missing_guid(latest_pgd):
        return []
    behind = []
    seen = set()
    for user_tg_id, saved_guid in (nosub_last_guids or {}).items():
        if user_tg_id in seen:
            continue
        if saved_guid != latest_pgd:
            behind.append(user_tg_id)
            seen.add(user_tg_id)
    return behind
