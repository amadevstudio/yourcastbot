# -*- coding: utf-8 -*-
"""A referral bonus must not turn an unlimited plan (-1) into a counted one.

Run from the repo root: python app/service/payment/test_referral_award.py
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.payment import paymentSafeModule  # noqa: E402
from app.service.payment.paymentSafeModule import (  # noqa: E402
    giveAward, notify_count_after_referral)


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


class FakeDB:
    subscription = {}
    saved = []

    def __init__(self, _path):
        pass

    def get_user_by_tg(self, _tg_id):
        return {'id': 1, 'lang': 'en'}

    def getUserSubscriptionByTg(self, _tg_id):
        return dict(FakeDB.subscription)

    def getTariffById(self, tariff_id):
        return {'id': tariff_id, 'level': 3, 'price': 500,
                'notify_count': -1, 'compression': 0}

    def subscribeUserToTariffByTg(self, tg_id, tariff_id, balance, time_left, notify_count):
        FakeDB.saved.append((tariff_id, balance, time_left, notify_count))

    def close(self):
        pass


def _award_with(notify_count):
    FakeDB.subscription = {
        'tariff_id': 3, 'balance': 100, 'time_left': 50, 'notify_count': notify_count}
    FakeDB.saved = []
    original = paymentSafeModule.SQLighter
    paymentSafeModule.SQLighter = FakeDB
    try:
        giveAward(1001, 1002, 'reged')
    finally:
        paymentSafeModule.SQLighter = original
    return FakeDB.saved[0]


def main():
    _assert_eq(notify_count_after_referral(-1, 20), -1, "unlimited stays unlimited")
    _assert_eq(notify_count_after_referral(0, 20), 20, "spent plan gets the bonus")
    _assert_eq(notify_count_after_referral(5, 20), 25, "counted plan gets the bonus")
    _assert_eq(_award_with(-1)[3], -1, "giveAward keeps an unlimited plan unlimited")
    _assert_eq(_award_with(5)[3], 25, "giveAward adds the bonus to a counted plan")
    print("all referral award checks passed")


if __name__ == "__main__":
    main()
