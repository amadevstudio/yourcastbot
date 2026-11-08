# -*- coding: utf-8 -*-
"""A CryptoBot or Robokassa webhook delivered twice credits once.

Both scripts run whole, as the PHP listeners run them (Telethon replaced by a
stub that sends nothing): the same signed invoice twice gives one credit and
one payment_history row; another invoice is credited. An unsigned Robokassa
request makes no users row and writes to nobody but the creator.

Run from the repo root: python scripts/payment/test_webhook_credit.py
"""
import base64
import hashlib
import hmac
import json
import os
import runpy
import sqlite3
import sys
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

SENT = []  # (chat, text) the stub Telethon client was asked to send
BLOCKED = set()  # chats that blocked the bot: Telethon raises UserIsBlockedError


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _stub_telethon():
    class Loop:
        @staticmethod
        def run_until_complete(coroutine):
            try:
                coroutine.send(None)
            except StopIteration:
                pass

    class TelegramClient:
        loop = Loop()

        def __init__(self, *args, **kwargs):
            pass

        def start(self, **kwargs):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        async def send_message(self, chat, text, **kwargs):
            if int(chat) in BLOCKED:
                raise type("UserIsBlockedError", (Exception,), {})("User is blocked (caused by SendMessageRequest)")
            SENT.append((int(chat), text))

    telethon = types.ModuleType("telethon")
    telethon.TelegramClient = TelegramClient
    custom = types.ModuleType("telethon.tl.custom")
    custom.Button = types.SimpleNamespace(inline=lambda *args: None)
    sys.modules.update({"telethon": telethon, "telethon.tl": types.ModuleType("telethon.tl"),
                        "telethon.tl.custom": custom})


def _database():
    from app.service.payment.test_referral_award import _temp_db
    path = _temp_db()
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE payment_history (user_id integer NOT NULL, service_type text NOT NULL, "
                 "invoice_id text, invoice_hash text, status text, amount integer, datetime text, "
                 "PRIMARY KEY (user_id, service_type, invoice_id))")
    conn.commit()
    conn.close()
    return path


def _balance(path, tg):
    conn = sqlite3.connect(path)
    try:
        row = conn.execute("SELECT ut.balance FROM user_tariff_cs ut JOIN users u ON u.id = ut.uid "
                           "WHERE u.telegramId = ?", (tg,)).fetchone()
        rows = conn.execute("SELECT COUNT(*) FROM payment_history").fetchone()[0]
        return (None if row is None else int(row[0])), rows
    finally:
        conn.close()


def _plan(path, tg):
    conn = sqlite3.connect(path)
    try:
        return tuple(conn.execute("SELECT ut.tariff_id, ut.balance, ut.time_left FROM user_tariff_cs ut "
                                  "JOIN users u ON u.id = ut.uid WHERE u.telegramId = ?", (tg,)).fetchone())
    finally:
        conn.close()


def _invite(path, invitee, inviter):
    from db.sqliteAdapter import SQLighter
    db = SQLighter(path)
    try:
        db.get_user_by_tg(inviter)
        db.get_user_by_tg(invitee)
        db.cursor.execute("UPDATE users SET ref_id = ? WHERE telegramId = ?", (inviter, invitee))
        db.connection.commit()
    finally:
        db.close()


def _ref_id(path, tg):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT ref_id FROM users WHERE telegramId = ?", (tg,)).fetchone()[0]
    finally:
        conn.close()


def _run(script, argv):
    saved = (sys.argv[:], os.getcwd())
    sys.argv = [script] + argv
    try:
        runpy.run_path(os.path.join(_ROOT, "scripts", "payment", script), run_name="__main__")
    finally:
        sys.argv, cwd = saved
        os.chdir(cwd)


def _b64(text):
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _charged(path, invoice_id):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT amount, charged FROM payment_history WHERE service_type = 'cryptoBot' "
                            "AND invoice_id = ?", (str(invoice_id),)).fetchone()
    finally:
        conn.close()


def _crypto(invoice_id, tg, cents, plan=None, months=None, discount=None):
    payload = {"tgid": tg, "amount": cents}
    if plan:
        payload["v"] = plan
    if months:
        payload.update(m=months, d=discount)
    body = json.dumps({"update_type": "invoice_paid", "payload": {
        "invoice_id": invoice_id, "hash": "h%d" % invoice_id, "paid_at": "2026-10-23T10:00:00Z",
        "status": "paid", "payload": json.dumps(payload)}})
    key = hashlib.sha256(b"crypto-key").digest()
    signature = hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()
    _run("cryptoBot.py", [_ROOT, _b64(body), _b64(json.dumps({"Crypto-Pay-Api-Signature": signature}))])


def _robokassa(inv_id, tg, summa, sign=True):
    import config
    params = {"OutSum": summa, "InvId": str(inv_id), "Shp_summa": summa, "Shp_uid": str(tg)}
    base = "%s:%s:%s:Shp_summa=%s:Shp_uid=%s" % (summa, inv_id, config.payment_p2_test, summa, tg)
    params["SignatureValue"] = hashlib.md5(base.encode()).hexdigest().upper() if sign else "0" * 32
    _run("subscription_income.py", [_b64(json.dumps(params)), _ROOT])


def main():
    try:
        import telebot  # noqa: F401  (the scripts import the bot's modules)
    except ModuleNotFoundError:
        print("skip  webhook credit: the bot's requirements are not installed")
        return
    _stub_telethon()
    import config
    from app.service import analytics_events
    from app.service.payment import offers, paymentSafeModule
    path = _database()
    saved = (config.db_path, paymentSafeModule.db_path, offers.db_path, config.server, config.crypto_bot_api_key,
             config.payment_p2_test, analytics_events.track)
    config.db_path = paymentSafeModule.db_path = offers.db_path = path
    config.server = False
    config.crypto_bot_api_key = "crypto-key"
    config.payment_p2_test = "p2-test"
    analytics_events.track = lambda *args, **kwargs: None
    try:
        _crypto(77, 6001, 500)
        _assert(_balance(path, 6001) == (500, 1), "a CryptoBot invoice is credited")
        _crypto(77, 6001, 500)
        _assert(_balance(path, 6001) == (500, 1), "the same invoice delivered again credits nothing")
        _crypto(78, 6001, 300)
        _assert(_balance(path, 6001) == (800, 2), "another invoice is credited")
        _crypto(80, 6008, 500, plan=3)
        _assert(_plan(path, 6008) == (3, 0, 720),
                "a plan's CryptoBot invoice turns that plan on when none runs (as Stars)")
        _crypto(81, 6008, 500, plan=3)
        _assert(_plan(path, 6008) == (3, 500, 720), "with the plan running it only tops the balance up")
        _crypto(82, 6009, 1, plan=3)
        _assert(_plan(path, 6009)[0] != 3 and _plan(path, 6009)[1] == 1,
                "an invoice for less than its plan's price (a forged button) is a top-up, no plan")

        # prepaid months through CryptoBot, as through Stars (purchase.py): the payload's terms
        _crypto(83, 6010, 3000, plan=3, months=6, discount=15)
        _assert(_plan(path, 6010) == (3, 2500, 720),
                "6 months of Relay: Relay on, the other five on the balance at full price")
        _assert(_charged(path, 83) == (3000, 2550), "the payment keeps what was charged (15% off) beside it")
        _crypto(83, 6010, 3000, plan=3, months=6, discount=15)
        _assert(_plan(path, 6010) == (3, 2500, 720), "the same bundle delivered again credits nothing")
        _crypto(84, 6011, 50, plan=1)
        _crypto(85, 6011, 3000, plan=3, months=6, discount=15)
        _assert(_plan(path, 6011) == (1, 2550, 720) and _charged(path, 85) == (2550, 2550),
                "Relay's months paid while Bronze runs (no pre-checkout to refuse): what was paid, a top-up")
        _crypto(86, 6012, 3000, plan=3, months=6, discount=60)
        _assert(_plan(path, 6012)[0] != 3 and _charged(path, 86) == (1200, 1200),
                "terms that were never sold (60% off) credit what was paid, no plan")

        _robokassa(9001, 6002, "4.99")
        _assert(_balance(path, 6002) == (499, 10), "a Robokassa invoice is credited, to the cent")
        _robokassa(9001, 6002, "4.99")
        _assert(_balance(path, 6002) == (499, 10), "the same signed notice again credits nothing")

        # A payer who blocked the bot: the notice fails, the inviter still gets the bonus
        # (before, Telethon's error skipped everything after the payer's notice).
        for invoice, payer, inviter, pay in ((79, 6004, 6005, lambda: _crypto(79, 6004, 500)),
                                             (9003, 6006, 6007, lambda: _robokassa(9003, 6006, "5.0"))):
            _invite(path, payer, inviter)
            BLOCKED.add(payer)
            SENT.clear()
            pay()
            _assert(_balance(path, payer)[0] == 500, "blocked payer, invoice %d: credited" % invoice)
            _assert(_ref_id(path, payer) is None and any(chat == inviter for chat, _ in SENT),
                    "blocked payer, invoice %d: the inviter is awarded and told" % invoice)

        SENT.clear()
        _robokassa(9002, 6003, "5.0", sign=False)
        conn = sqlite3.connect(path)
        made = conn.execute("SELECT COUNT(*) FROM users WHERE telegramId = 6003").fetchone()[0]
        conn.close()
        _assert(made == 0 and all(chat == int(config.creatorId) for chat, _ in SENT),
                "an unsigned request makes no user and writes to nobody but the creator")
    finally:
        (config.db_path, paymentSafeModule.db_path, offers.db_path, config.server, config.crypto_bot_api_key,
         config.payment_p2_test, analytics_events.track) = saved
        os.remove(path)
    print("all webhook credit checks passed")


if __name__ == "__main__":
    main()
