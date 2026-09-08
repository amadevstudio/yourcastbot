# -*- coding: utf-8 -*-
"""Parse Crypto Pay / Robokassa webhook bodies. Empty probes are not payments."""
from __future__ import annotations

import json
from typing import Any, Optional


def crypto_invoice(params_s: str, headers_s: str) -> Optional[tuple[dict, dict]]:
    if not (params_s or "").strip():
        return None
    try:
        params = json.loads(params_s)
        headers = json.loads(headers_s or "{}")
    except (ValueError, TypeError):
        return None
    if not isinstance(params, dict):
        return None
    payload = params.get("payload")
    if not isinstance(payload, dict) or "invoice_id" not in payload:
        return None
    inner = payload.get("payload")
    if not isinstance(inner, str) or not inner.strip():
        return None
    if not isinstance(headers, dict):
        headers = {}
    return params, headers


def robokassa_result(raw: str) -> Optional[dict[str, Any]]:
    if not (raw or "").strip():
        return None
    try:
        params = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(params, dict):
        return None
    needed = ("OutSum", "InvId", "SignatureValue", "Shp_uid", "Shp_summa")
    if any(key not in params for key in needed):
        return None
    return params
