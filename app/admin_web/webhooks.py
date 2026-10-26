# -*- coding: utf-8 -*-
"""Payment webhooks, served by the admin process instead of PHP.

The PHP listeners on the server only handed the request to the Python
scripts in scripts/payment. PHP there is 7.4 (Ubuntu 20.04), open to
PHP2Shell (CVE-2026-109618/109619, 2026-10): a request is enough to run code
before any check in the script. Here the same scripts get the same input at
the same public paths (nginx proxies them), so Robokassa's and CryptoBot's
settings stay as they are.

- CryptoBot: the raw body and the signature header, as listener.php passed
  them; 200 "OK" when the script says OK, else 400.
- Robokassa: the query parameters (Result URL is a GET), only from the
  addresses Robokassa documents (nginx allows only them too); the script's
  answer as it is ("OK<inv_id>" or "bad sign").

These paths are outside /api: the admin's CSRF check would refuse a POST
without an Origin, and a webhook never sends one. Nothing here reads the
admin session or the diag token.
"""
import base64
import json
import os
import subprocess
import sys

import config
from lib.tools.logger import logger

CRYPTOBOT_PATH = '/payment/crypto-bot/listener.php'
ROBOKASSA_PATH = '/payment/robokassa/result.php'
# docs.robokassa.ru, "Уведомления и переадресация": notices come from these addresses only
ROBOKASSA_IPS = ('185.59.216.65', '185.59.217.65')
SCRIPT_TIMEOUT = 120  # the script starts Telethon and talks to Telegram


def _b64(text) -> str:
    return base64.b64encode(text if isinstance(text, bytes) else str(text).encode('utf-8')).decode('ascii')


def run_script(name, args, runner=None) -> str:
    """scripts/payment/<name> with `args`, from the bot's folder; its stdout, '' when it failed."""
    runner = runner or subprocess.run
    script = os.path.join(config.BASE_DIR, 'scripts', 'payment', name)
    try:
        done = runner([sys.executable, script] + list(args), cwd=config.BASE_DIR, capture_output=True,
                      timeout=SCRIPT_TIMEOUT, check=False)
    except Exception as e:
        logger.err('payment webhook:', name, type(e).__name__, e)
        return ''
    return (done.stdout or b'').decode('utf-8', 'replace')


def cryptobot(body: bytes, signature: str, runner=None) -> tuple[int, str]:
    """(status, text) for a CryptoBot webhook, as listener.php answered it."""
    headers = {'Crypto-Pay-Api-Signature': signature} if signature else {}
    out = run_script('cryptoBot.py', [config.BASE_DIR, _b64(body or b''), _b64(json.dumps(headers))], runner)
    ok = ''.join(out.split()) == 'OK'
    return (200, 'OK') if ok else (400, '')


def robokassa(params: dict, client_ip: str, runner=None) -> tuple[int, str]:
    """(status, text) for a Robokassa Result URL notice, as result.php answered it."""
    if client_ip not in ROBOKASSA_IPS:
        return 403, 'bad sign\n'
    out = run_script('subscription_income.py', [_b64(json.dumps(dict(params))), config.BASE_DIR], runner)
    return 200, out
