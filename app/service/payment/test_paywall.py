# -*- coding: utf-8 -*-
"""A free limit sells Relay: the subscription limit, the manual update limit
and the channel page each carry Relay's invoice one tap away (change-plan
kept next to it), and that button bills Relay without naming a tariff id.

Needs the bot's requirements (the builders import telebot and Telethon).
Run from the repo root: python app/service/payment/test_paywall.py
"""
import json
import os
import sys
import types
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.controller.builders.test_open_recs import import_builder  # noqa: E402

TARIFFS = [{'id': 1, 'level': 1, 'price': 50, 'notify_count': 30},
           {'id': 3, 'level': 3, 'price': 500, 'notify_count': -1}]


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _first_cta(markup):
    return [row[0].get('callback_data') for row in markup][:2]


PAYWALL = [{'tp': 'bs_stars_pay'}, {'tp': 'bs_trfs'}]


class _FreeUserDB:
    """A free user over the 15-podcast limit."""

    def __init__(self, _path):
        pass

    def get_uccs_count_by_tg(self, _chat_id):
        return 16

    def getUserSubscriptionByTg(self, _chat_id):
        return None

    def get_user_related_podcast_info(self, _chat_id, _podcast_id):
        return {'subscribed': False}

    def is_user_have_bot_subscription(self, _chat_id):
        return False

    def getTariffs(self, channel_control=None):
        return [t for t in TARIFFS if not channel_control or t['level'] == 3]

    def close(self):
        pass


def _call(data):
    return types.SimpleNamespace(data=json.dumps(data))


def subscription_limit(podcast):
    sent, toasts, subscribed = [], [], []
    data = {'chat_id': 501, 'language_code': 'en', 'message': None,
            'callback': _call({'tp': 'subscription'}),
            'united_data': {'id': 7, 'service_id': '77', 'service_name': 'itunes'}}
    with patch.object(podcast, 'SQLighter', _FreeUserDB), \
            patch.object(podcast, 'notify', lambda _c, _m, text, **kw: toasts.append((text, kw))), \
            patch.object(podcast, 'outer_sender', lambda chat, msgs, **kw: sent.append((chat, msgs))), \
            patch.object(podcast.app.service.podcast.subscription, 'add_sub',
                         lambda *a: subscribed.append(a)):
        _assert_eq(podcast.switch_subscription(data), False, "the 16th free podcast is refused")
    _assert_eq(subscribed, [], "and not subscribed")
    _assert_eq(toasts[0][1].get('alert', False), False, "a toast, not a blocking alert")
    _assert_eq(_first_cta(sent[0][1][0]['reply_markup']), PAYWALL,
               "the limit message carries Relay's invoice and change-plan")


def update_limit():
    stub = types.ModuleType("agent.bot_telethon")
    stub.thobot_session_handler = ""
    sys.modules["agent.bot_telethon"] = stub
    import app.jobs.podcastsUpdater as updater
    renders = []
    data = {'chat_id': 502, 'language_code': 'en', 'message': None, 'callback': None}
    with patch.object(updater, 'SQLighter', _FreeUserDB), \
            patch.object(updater, 'outer_sender', lambda *a, **kw: True), \
            patch.object(updater, 'render_messages', lambda chat, msgs, **kw: renders.append(msgs)), \
            patch.object(updater.outbox, 'enqueue', lambda *a, **kw: None), \
            patch.object(updater.storage, 'del_user_state', lambda *a: None), \
            patch.object(updater.storage, 'add_user_state', lambda *a: None):
        updater.update_feed(data)
    markup = renders[0][0]['reply_markup']
    _assert_eq(_first_cta(markup), PAYWALL, "the manual update limit carries the invoice")
    _assert_eq(markup[-1][0]['callback_data']['tp'], 'bck', "and keeps the back button")


def channel_limit(channel):
    page = channel.get_connecting_channel_message(
        'en', {'id': 0, 'level': 0, 'price': 0}, [TARIFFS[1]])
    _assert_eq(_first_cta(page['markup']), PAYWALL, "the channel page carries the invoice")


def invoice_defaults_to_relay(stars):
    invoices = []
    data = {'chat_id': 503, 'language_code': 'en', 'message': None,
            'callback': _call({'tp': 'bs_stars_pay'}), 'united_data': {}}
    with patch.object(stars, 'SQLighter', _FreeUserDB), \
            patch.object(stars, 'get_invoice_stars_withdraw_rate_x1000', lambda: 1300), \
            patch.object(stars.bot, 'send_invoice', lambda *a, **kw: invoices.append(a)):
        stars.send_invoice(data)
        stars.send_invoice(dict(data, united_data={'v': 1}))
    _assert_eq(json.loads(invoices[0][3])['b'], 500, "a button without an id bills Relay's price")
    _assert_eq(json.loads(invoices[1][3])['b'], 50, "a button with an id bills that plan")


def main():
    podcast = import_builder("podcastModule")
    if podcast is None:
        return
    channel = import_builder("channelModule")
    from app.service.payment import starsPaymentModule
    subscription_limit(podcast)
    update_limit()
    channel_limit(channel)
    invoice_defaults_to_relay(starsPaymentModule)
    print("all paywall checks passed")


if __name__ == "__main__":
    main()
