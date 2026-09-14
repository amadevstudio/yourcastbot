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
    audio_source_gone, expected_send_noise, message_to_delete_not_found,
    entities_parse_error, file_refused)


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

    # Status message: an edit racing the sender's own delete, and the delete
    # of a message the user already removed. Both are stale, not bugs.
    race = ("A request to the Telegram API was unsuccessful. Error code: 400. "
            "Description: Bad Request: not Found")
    _assert_eq(message_to_edit_not_found(race), True, "edit racing delete is a stale edit")
    _assert_eq(user_unavailable_error(race), False, "edit race does not mark the user deleted")
    gone_delete = "Bad Request: message to delete not found"
    _assert_eq(message_to_delete_not_found(gone_delete), True, "stale delete detected")
    _assert_eq(expected_send_noise(gone_delete), True, "stale delete is expected noise")
    _assert_eq(user_unavailable_error("Bad Request: chat not found"), True, "chat not found still blocks")
    _assert_eq(message_to_edit_not_found("Bad Request: chat not found"), False,
               "chat not found is not a stale edit")

    # The enclosure URL is refused: terminal, like 404. "Try later" codes retry.
    for code in ("400", "401", "403", "404", "410", "451"):
        text = "%s Client Error: Bad Request for url: https://cdn.example/ep.mp3" % code
        _assert_eq(audio_source_gone(RuntimeError(text)), True, "enclosure %s is gone" % code)
    for code in ("408", "425", "429"):
        text = "%s Client Error: Too Many Requests for url: https://cdn.example/ep.mp3" % code
        _assert_eq(audio_source_gone(RuntimeError(text)), False, "enclosure %s retries" % code)
    _assert_eq(audio_source_gone(RuntimeError("500 Server Error: for url: https://cdn.example/ep.mp3")),
               False, "enclosure 5xx retries")
    _assert_eq(audio_source_gone("Bad Request: message text is empty"), False,
               "Telegram 400 is not an enclosure refusal")

    # URL-level refusals end the URL step for every recipient; per-chat errors do not.
    for text in ("Bad Request: failed to get HTTP URL content",
                 "Bad Request: wrong file identifier/HTTP URL specified",
                 "Request Entity Too Large"):
        _assert_eq(file_refused(text), True, "url refused: " + text[:40])
    for text in ("Too Many Requests: retry after 5", "Forbidden: bot was blocked by the user",
                 "Bad Request: not enough rights to send audio"):
        _assert_eq(file_refused(text), False, "per chat, not url: " + text[:40])

    parse = ("Bad Request: can't parse entities: Unclosed start tag \"span\" "
             "at byte offset 950")
    _assert_eq(entities_parse_error(parse), True, "unclosed tag is a parse error")
    _assert_eq(entities_parse_error("Bad Request: message is too long"), False,
               "too long is not a parse error")
    print("all error classification checks passed")


if __name__ == "__main__":
    main()
