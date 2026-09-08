# -*- coding: utf-8 -*-
"""Signed-cookie admin sessions. Passwords stay SHA-256 to match `admins`,
then upgrade to PBKDF2 on a successful login.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any, Optional, Tuple

import config

COOKIE_NAME = "yc_admin"
SESSION_TTL_SEC = 7 * 24 * 3600
MAX_LOGIN_ATTEMPTS = 8
LOGIN_WINDOW_SEC = 15 * 60
PBKDF2_PREFIX = "pbkdf2_sha256$"
PBKDF2_ROUNDS = 260000

_login_attempts: dict[str, list[float]] = {}


def _secret() -> bytes:
    extra = getattr(config, "admin_session_secret", None)
    if extra:
        return hashlib.sha256(str(extra).encode("utf-8")).digest()
    return hashlib.sha256(("yc-admin|" + str(config.token)).encode("utf-8")).digest()


def sign_session(admin_id: int, mail: str, now: Optional[float] = None) -> str:
    payload = {
        "id": int(admin_id),
        "mail": mail,
        "exp": int((now or time.time()) + SESSION_TTL_SEC),
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    body = raw.encode("utf-8")
    sig = hmac.new(_secret(), body, hashlib.sha256).hexdigest()
    return body.hex() + "." + sig


def read_session(token: Optional[str], now: Optional[float] = None) -> Optional[dict[str, Any]]:
    if not token or "." not in token:
        return None
    hex_body, sig = token.split(".", 1)
    try:
        body = bytes.fromhex(hex_body)
    except ValueError:
        return None
    expected = hmac.new(_secret(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if int(payload.get("exp") or 0) < int(now or time.time()):
        return None
    if "id" not in payload or "mail" not in payload:
        return None
    return payload


def hash_password(password: str) -> str:
    """Legacy SHA-256 hex stored by the old PHP admin."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def make_password(password: str) -> str:
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("ascii"), PBKDF2_ROUNDS)
    return "%s%d$%s$%s" % (PBKDF2_PREFIX, PBKDF2_ROUNDS, salt, dk.hex())


def verify_password(
        password: str, stored: str) -> Tuple[bool, Optional[str]]:
    stored = stored or ""
    if stored.startswith(PBKDF2_PREFIX):
        try:
            rest = stored[len(PBKDF2_PREFIX):]
            rounds_s, salt, hexdk = rest.split("$", 2)
            rounds = int(rounds_s)
        except ValueError:
            return False, None
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("ascii"), rounds)
        if not hmac.compare_digest(dk.hex(), hexdk):
            return False, None
        if rounds != PBKDF2_ROUNDS:
            return True, make_password(password)
        return True, None
    legacy = hash_password(password)
    if len(stored) != len(legacy) or not hmac.compare_digest(legacy, stored):
        return False, None
    return True, make_password(password)


def login_allowed(ip: str, now: Optional[float] = None) -> bool:
    when = now or time.time()
    stamps = [t for t in _login_attempts.get(ip, []) if when - t < LOGIN_WINDOW_SEC]
    _login_attempts[ip] = stamps
    return len(stamps) < MAX_LOGIN_ATTEMPTS


def register_login_failure(ip: str, now: Optional[float] = None) -> None:
    when = now or time.time()
    _login_attempts.setdefault(ip, []).append(when)


def clear_login_failures(ip: str) -> None:
    _login_attempts.pop(ip, None)
