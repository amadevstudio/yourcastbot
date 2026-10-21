# -*- coding: utf-8 -*-
"""OpenRouter over plain HTTP: one key for the chat model and for Whisper.

`post` returns the parsed body or raises OpenRouterError (an HTTP error or
an error in the body); `cost` is what OpenRouter billed for the call.
"""
import requests

from config import openrouter_api_key

BASE_URL = 'https://openrouter.ai/api/v1/'
HTTP_TIMEOUT = 300


class OpenRouterError(Exception):
    pass


def configured() -> bool:
    return bool(openrouter_api_key)


def post(path, session=None, **kwargs) -> dict:
    """POST to BASE_URL + path with our key; `kwargs` go to requests (json, files, data)."""
    response = (session or requests).post(
        BASE_URL + path, headers={'Authorization': 'Bearer ' + openrouter_api_key},
        timeout=kwargs.pop('timeout', HTTP_TIMEOUT), **kwargs)
    if response.status_code != 200:
        raise OpenRouterError('%s %s: %s' % (path, response.status_code, response.text[:200]))
    body = response.json()
    if body.get('error'):
        raise OpenRouterError('%s: %s' % (path, str(body['error'])[:200]))
    return body


def cost(body) -> float:
    return float((body.get('usage') or {}).get('cost') or 0.0)
