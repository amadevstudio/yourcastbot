# -*- coding: utf-8 -*-
"""render_messages retries once when Telegram's gateway fails. No network.

A user tapped a podcast card twice and got 502 Bad Gateway both times, with no
answer at all. One retry a moment later usually goes through.

Run from the repo root: python lib/telegram/general/test_render_retry.py
"""
import importlib
import os
import sys
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class _InertModule(types.ModuleType):
    """Unknown attributes are inert classes: import-time names resolve, nothing runs."""

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        value = type(name, (), {'__init__': lambda self, *a, **k: None})
        setattr(self, name, value)
        return value


def _install_fake(name):
    parts = name.split('.')
    for i in range(1, len(parts) + 1):
        module_name = '.'.join(parts[:i])
        module = sys.modules.get(module_name)
        if not isinstance(module, _InertModule):
            module = _InertModule(module_name)
            sys.modules[module_name] = module
        if i > 1:
            setattr(sys.modules['.'.join(parts[:i - 1])], parts[i - 1], module)


class ApiException(Exception):
    pass


class ApiTelegramException(ApiException):
    def __init__(self, error_code, description):
        super().__init__("A request to the Telegram API was unsuccessful. "
                         "Error code: %d. Description: %s" % (error_code, description))
        self.error_code = error_code


for _name in ('telebot.apihelper', 'telebot.types'):
    _install_fake(_name)


def _fake_leaf(name):
    """Fake one module inside a real (namespace) package: `app`, `agent` stay importable."""
    package, _, leaf = name.rpartition('.')
    module = _InertModule(name)
    sys.modules[name] = module
    setattr(importlib.import_module(package), leaf, module)
    return module


for _name in ('agent.bot_telebot', 'app.repository.storage.storage',
              'app.repository.storage.telegram_cache'):
    _fake_leaf(_name)
sys.modules['telebot.apihelper'].ApiException = ApiException
sys.modules['telebot.apihelper'].ApiTelegramException = ApiTelegramException


class _Storage:
    def __init__(self):
        self.saved = None

    def get_user_resend_flag(self, chat_id):
        return False

    def get_message_structures(self, chat_id):
        return [{'id': 10, 'type': 'text'}]

    def set_user_message_structures(self, chat_id, structures):
        self.saved = structures

    def del_user_resend_flag(self, chat_id):
        pass


storage = _Storage()
sys.modules['app.repository.storage'].storage = storage
sys.modules['app.repository.storage.storage'] = storage

from lib.telegram.general import message_master as mm  # noqa: E402


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _run(failures):
    """message_master fails with each error in `failures`, then succeeds."""
    calls = []
    queue = list(failures)

    def fake_master(bot, chat_id, resending=False, message_structures=None,
                    previous_message_structures=None):
        calls.append(resending)
        if queue:
            raise queue.pop(0)
        return [{'id': 11, 'type': 'text'}]

    mm.message_master = fake_master
    mm.SERVER_ERROR_RETRY_SECONDS = 0
    try:
        result = mm.render_messages(1, [{'type': 'text', 'text': 'card'}])
    except ApiException as e:
        result = e
    return calls, result


def main():
    calls, result = _run([ApiTelegramException(502, "Bad Gateway")])
    _assert_eq(len(calls), 2, "a 502 is retried once")
    _assert_eq(result, [{'id': 11, 'type': 'text'}], "the retry's message is the answer")
    _assert_eq(calls[1], False, "the retry edits the same screen, it does not resend")

    calls, result = _run([ApiTelegramException(502, "Bad Gateway")] * 2)
    _assert_eq(len(calls), 2, "only one retry")
    _assert_eq(isinstance(result, ApiTelegramException), True, "second 502 is raised")

    calls, result = _run([ApiTelegramException(400, "Bad Request: message text is empty")])
    _assert_eq(len(calls), 1, "a 400 is our bug and is not retried")
    print("all render retry checks passed")


if __name__ == "__main__":
    main()
