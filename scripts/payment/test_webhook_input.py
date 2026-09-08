# -*- coding: utf-8 -*-
"""Empty/probe payment bodies must not look like invoices.

Run: python scripts/payment/test_webhook_input.py
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.payment.webhook_input import crypto_invoice, robokassa_result  # noqa: E402


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def main():
    _assert_eq(crypto_invoice("", "{}"), None, "empty crypto body")
    _assert_eq(crypto_invoice("   ", "{}"), None, "blank crypto body")
    _assert_eq(crypto_invoice("{", "{}"), None, "broken json")
    _assert_eq(
        crypto_invoice(json.dumps({"probe": True}), "[]"),
        None, "crypto probe")
    _assert_eq(
        crypto_invoice(json.dumps({"payload": {"hash": "x"}}), "{}"),
        None, "payload without invoice_id")
    _assert_eq(
        crypto_invoice(json.dumps({"payload": {"invoice_id": 1, "payload": ""}}), "{}"),
        None, "empty inner payload")

    ok_params = {
        "payload": {
            "invoice_id": 9,
            "hash": "abc",
            "payload": json.dumps({"tgid": 1, "amount": 199}),
        }
    }
    parsed = crypto_invoice(json.dumps(ok_params), "[]")
    _assert_eq(parsed is not None, True, "real crypto invoice")
    _assert_eq(parsed[1], {}, "list headers become dict")
    _assert_eq(parsed[0]["payload"]["invoice_id"], 9, "invoice id kept")

    _assert_eq(robokassa_result(""), None, "empty robokassa")
    _assert_eq(robokassa_result("[]"), None, "php empty GET is []")
    _assert_eq(robokassa_result("{}"), None, "php empty GET as object")
    real = {
        "OutSum": "1.99",
        "InvId": "3",
        "SignatureValue": "ABC",
        "Shp_uid": "1",
        "Shp_summa": "1.99",
    }
    got = robokassa_result(json.dumps(real))
    _assert_eq(got["InvId"], "3", "real robokassa result")
    print("all webhook_input checks passed")


if __name__ == "__main__":
    main()
