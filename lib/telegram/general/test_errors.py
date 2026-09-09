# -*- coding: utf-8 -*-
"""Telegram error classification. No network.

Run from the repo root: python lib/telegram/general/test_errors.py
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from lib.telegram.general.errors import (  # noqa: E402
    message_to_edit_not_found, user_unavailable_error,
    audio_source_gone, expected_send_noise)


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def main():
    unavailable = [
        "Forbidden: bot was blocked by the user",
        "Bad Request: chat not found",
        "Forbidden: user is deactivated",
        "Forbidden: bot was kicked from the group chat",
        "Forbidden: bot was kicked from the supergroup chat",
        "A request to the Telegram API was unsuccessful. Error code: 400. "
        "Description: Bad Request: group chat was upgraded to a supergroup chat",
        "GROUP_CHAT_UPGRADED",
        "Bad Request: PEER_ID_INVALID",
        "Forbidden: the group chat was deleted",
    ]
    for text in unavailable:
        _assert_eq(user_unavailable_error(text), True, text[:48])

    still_alive = [
        "Too Many Requests: retry after 37",
        "Bad Request: message text is empty",
        "failed to get HTTP URL content",
        "Bad Request: message to edit not found",
    ]
    for text in still_alive:
        _assert_eq(user_unavailable_error(text), False, text[:48])

    stale_edit = [
        "Bad Request: message to edit not found",
        "Bad Request: MESSAGE_ID_INVALID",
        "A request to the Telegram API was unsuccessful. Error code: 400. "
        "Description: Bad Request: MESSAGE_ID_INVALID",
        "message identifier is not specified",
    ]
    for text in stale_edit:
        _assert_eq(message_to_edit_not_found(text), True, text[:48])
        _assert_eq(user_unavailable_error(text), False, "not blocked: " + text[:32])
    _assert_eq(
        message_to_edit_not_found("Too Many Requests: retry after 3"),
        False, "flood is not a stale edit")
    _assert_eq(
        expected_send_noise("Forbidden: bot was blocked by the user"),
        True, "blocked is expected noise")
    _assert_eq(
        expected_send_noise("Too Many Requests: retry after 37"),
        True, "429 is expected noise")
    _assert_eq(
        expected_send_noise("Bad Request: MESSAGE_ID_INVALID"),
        True, "stale edit is expected noise")
    _assert_eq(
        expected_send_noise(RuntimeError(
            "HTTPSConnectionPool(host='x', port=443): Max retries exceeded "
            "(Caused by ReadTimeoutError(Read timed out.))")),
        True, "cdn timeout is expected noise")
    _assert_eq(
        audio_source_gone(RuntimeError(
            "HTTPSConnectionPool(host='x', port=443): Max retries exceeded "
            "(Caused by ReadTimeoutError(Read timed out.))")),
        True, "cdn timeout is a gone enclosure")
    _assert_eq(
        expected_send_noise(RuntimeError("disk I/O error")),
        False, "unexpected stays unexpected")
    print("all error classification checks passed")


if __name__ == "__main__":
    main()
