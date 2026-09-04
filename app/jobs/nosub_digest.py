# -*- coding: utf-8 -*-
"""No-tariff digest: 'you have new episodes' after an updater circle.

Paid users get the audio in send_new_records_by_channel. Users with
notify=1 but no bot tariff are only flagged here; the updater sends one
message per user when the circle finishes.
"""


def is_missing_guid(value) -> bool:
    return value in (None, '', 'None')


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
