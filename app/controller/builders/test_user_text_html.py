# -*- coding: utf-8 -*-
"""Text a user typed or named goes into our HTML messages escaped.

A "<" in a Telegram channel's title or in the email saved for Patreon is a tag
to Telegram: the whole message was refused, and the Patreon page, showing the
saved email, could never open again.

Run from the repo root: python app/controller/builders/test_user_text_html.py
(needs the bot's requirements; skipped without them)
"""
import os
import sys
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.payment.test_days_left import _telegram_html  # noqa: E402

TITLE = 'Podcasts <3 & more'


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _channel_removed_notice(channelModule):
    """The notice to a channel's owner when the bot was removed from it."""
    sent = []

    class FakeDb:
        def __init__(self, *args):
            pass

        def getUserTgIdByChannelTg(self, channel_tg_id):
            return 5001

        def getTgChannelDataByTgId(self, user_tg_id, channel_tg_id):
            return {'active': True}

        def addOrUpdateTgChannel(self, *args):
            pass

        def get_user_by_tg(self, tg_id):
            return {'lang': 'en'}

        def close(self):
            pass

    saved = channelModule.SQLighter, channelModule.bot, channelModule.render_messages
    channelModule.SQLighter = FakeDb
    channelModule.bot = types.SimpleNamespace(get_chat=lambda chat_id: types.SimpleNamespace(title=TITLE))
    channelModule.render_messages = lambda chat_id, structures, **kwargs: sent.append(structures[0]['text'])
    try:
        channelModule.bot_removed_from_channel_reaction(
            Exception("Forbidden: bot was kicked from the channel chat"), -1001)
    finally:
        channelModule.SQLighter, channelModule.bot, channelModule.render_messages = saved
    return sent


def main():
    try:
        import telebot  # noqa: F401  (the modules import the bot)
    except ModuleNotFoundError:
        print("skip  user text in HTML: the bot's requirements are not installed")
        return
    from app.controller.builders import channelModule
    from app.service.payment.patreonPaymentModule import get_patreon_email_message

    added = channelModule.get_input_channel_id_message(
        'en', 'added', types.SimpleNamespace(title=TITLE))['message']
    _assert(_telegram_html(added) and '&lt;3' in added, "channel added: the title is escaped")

    sent = _channel_removed_notice(channelModule)
    _assert(len(sent) == 1 and _telegram_html(sent[0]) and '&lt;3' in sent[0],
            "bot removed from the channel: the title is escaped")

    for language in ('en', 'ru'):
        page = get_patreon_email_message('me<3@example.com', language)['message']
        _assert(_telegram_html(page) and 'me&lt;3@example.com' in page,
                "Patreon page, %s: the saved email is escaped" % language)
    print("all user text checks passed")


if __name__ == "__main__":
    main()
