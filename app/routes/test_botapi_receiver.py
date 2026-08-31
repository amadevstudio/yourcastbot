"""Smoke tests for Bot API command/callback routing helpers.

Run from the repo root: python app/routes/test_botapi_receiver.py
Does not talk to Telegram.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.routes.botapi_receiver import command_name, iter_command_routes, is_channel_chat
from app.routes.initialize_routes import get_tp


class _Chat:
    def __init__(self, chat_type: str):
        self.type = chat_type


def _assert(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def main() -> None:
    _assert(command_name('/start') == 'start', 'parse /start')
    _assert(command_name('/start@YourInstaFeedDevelopingBot extra') == 'start', 'parse /start@bot')
    _assert(command_name('/subscriptions') == 'subscriptions', 'parse /subscriptions')
    _assert(command_name('hello') is None, 'plain text is not a command')
    _assert(command_name('') is None, 'empty text is not a command')

    _assert(list(iter_command_routes('start')) == ['start'], 'start route')
    _assert(list(iter_command_routes('menu')) == ['menu'], 'menu route')
    _assert(list(iter_command_routes('subscriptions')) == ['subs'], 'subscriptions alias')
    _assert(list(iter_command_routes('nope')) == [], 'unknown command')

    _assert(get_tp('{"tp":"bck"}') == 'bck', 'callback back')
    _assert(get_tp('{"tp":"podcast","id":1}') == 'podcast', 'callback podcast')
    _assert(get_tp('not-json') == '', 'invalid callback data')

    _assert(is_channel_chat(_Chat('channel')) is True, 'skip channels')
    _assert(is_channel_chat(_Chat('private')) is False, 'allow private')
    _assert(is_channel_chat(_Chat('supergroup')) is False, 'allow groups')

    print('botapi_receiver helpers: ok')


if __name__ == '__main__':
    main()
