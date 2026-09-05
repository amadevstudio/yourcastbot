# -*- coding: utf-8 -*-
"""nosub digest helpers. Run from repo root: python app/jobs/test_nosub_digest.py"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.jobs.nosub_digest import (  # noqa: E402
    DIGEST_COOLDOWN, digest_enabled, digest_is_due, for_each_digest_user,
    latest_episode_id, nosub_users_behind, parse_digest_sent_at,
    should_send_nosub_digest, should_skip_item_parse)
from app.i18n.messages import emojiCodes, get_message  # noqa: E402
from datetime import datetime  # noqa: E402


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def main():
    _assert_eq(
        should_skip_item_parse([], "Mon, 01 Jan 2026"),
        False,
        "nosubs-only must parse items")
    _assert_eq(
        should_skip_item_parse(
            [{'last_date': "Mon, 01 Jan 2026"}], "Mon, 01 Jan 2026"),
        True,
        "all paid current skips items")
    _assert_eq(
        should_skip_item_parse(
            [{'last_date': "Sun, 31 Dec 2025"}, {'last_date': "Mon, 01 Jan 2026"}],
            "Mon, 01 Jan 2026"),
        False,
        "one paid behind still parses")
    _assert_eq(
        should_skip_item_parse([{'last_date': "Mon, 01 Jan 2026"}], None),
        False,
        "missing feed date does not skip")

    _assert_eq(
        nosub_users_behind({1001: "old", 1002: "new-ep", 1003: "old"}, "new-ep"),
        [1001, 1003],
        "behind users")
    _assert_eq(
        nosub_users_behind({1001: "new-ep"}, "new-ep"),
        [],
        "already current")
    _assert_eq(
        nosub_users_behind({1001: "old"}, None),
        [],
        "no latest episode")
    _assert_eq(
        nosub_users_behind({1001: None}, "new-ep"),
        [1001],
        "empty saved guid is behind")

    _assert_eq(
        latest_episode_id({'last_guid': "ch-ep"}, [{'last_guid': "paid-ep"}]),
        "ch-ep",
        "prefer channel last_guid")
    _assert_eq(
        latest_episode_id({'last_guid': None}, [{'last_guid': "paid-ep"}]),
        "paid-ep",
        "fallback to paid last_guid")
    _assert_eq(
        latest_episode_id({'last_guid': ""}, []),
        None,
        "missing both")

    sent = []
    errors = []

    def handle_user(user_tg_id):
        if user_tg_id == 2:
            raise RuntimeError(
                "Bad Request: group chat was upgraded to a supergroup chat")
        sent.append(user_tg_id)

    pauses = []
    for_each_digest_user(
        [1, 2, 3],
        handle_user,
        on_error=lambda uid, _e: errors.append(uid),
        pause=lambda: pauses.append(1))
    _assert_eq(sent, [1, 3], "digest continues after one send error")
    _assert_eq(errors, [2], "failed digest user is reported")
    _assert_eq(pauses, [1, 1, 1], "pause still runs after a failure")

    now = datetime(2026, 9, 5, 3, 0, 0)
    _assert_eq(parse_digest_sent_at(None), None, "missing sent_at")
    _assert_eq(
        parse_digest_sent_at("2026-09-05 03:00:00"),
        datetime(2026, 9, 5, 3, 0, 0),
        "sqlite datetime")
    _assert_eq(
        digest_is_due("2026-09-05 03:00:00", now=now),
        False,
        "just sent is not due")
    _assert_eq(
        digest_is_due(
            "2026-08-29 02:59:59", now=now, cooldown=DIGEST_COOLDOWN),
        True,
        "week plus a second is due")
    _assert_eq(
        digest_is_due("2026-08-29 03:00:00", now=now),
        True,
        "exactly a week is due")
    _assert_eq(
        digest_is_due("2026-08-29 03:00:01", now=now),
        False,
        "one second under a week is not due")
    _assert_eq(digest_is_due(None, now=now), True, "never sent is due")

    due_user = {
        "deleted_at": None,
        "nosub_digest_enabled": 1,
        "nosub_digest_sent_at": "2026-01-01 00:00:00",
    }
    _assert_eq(
        should_send_nosub_digest(due_user, now=now), True, "eligible user")
    _assert_eq(
        should_send_nosub_digest(
            {**due_user, "nosub_digest_enabled": 0}, now=now),
        False, "opted out")
    _assert_eq(
        should_send_nosub_digest(
            {**due_user, "deleted_at": "2026-09-01 00:00:00"}, now=now),
        False, "deleted user")
    _assert_eq(
        should_send_nosub_digest(
            {**due_user, "nosub_digest_sent_at": "2026-09-05 00:00:00"},
            now=now),
        False, "sent this week")
    _assert_eq(digest_enabled({"nosub_digest_enabled": 0}), False, "disabled")
    _assert_eq(digest_enabled({}), True, "missing flag defaults on")

    langs = ("ru", "en", "pt", "es", "de", "he")
    for lang in langs:
        mute = get_message("nosubDigestMuteButton", lang)
        toast = get_message("nosubDigestMutedToast", lang)
        on_label = (
            emojiCodes["whiteHeavyCheckMark"] + " "
            + get_message("nosubDigestRemindersOn", lang))
        off_label = (
            emojiCodes["crossMark"] + " "
            + get_message("nosubDigestRemindersOff", lang))
        if len(mute) > 64:
            raise AssertionError("%s mute button is %s chars: %r" % (
                lang, len(mute), mute))
        if len(on_label) > 64:
            raise AssertionError("%s on button is %s chars: %r" % (
                lang, len(on_label), on_label))
        if len(off_label) > 64:
            raise AssertionError("%s off button is %s chars: %r" % (
                lang, len(off_label), off_label))
        if len(toast) > 200:
            raise AssertionError("%s toast is %s chars" % (lang, len(toast)))
        print("ok  %s mute=%s on=%s off=%s" % (
            lang, len(mute), len(on_label), len(off_label)))

    print("all nosub_digest checks passed")


if __name__ == "__main__":
    main()
