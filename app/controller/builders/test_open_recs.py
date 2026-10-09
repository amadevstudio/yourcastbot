# -*- coding: utf-8 -*-
"""The episode list of a podcast whose screen state is gone says so.

The state is gone when a button of an old message is tapped (or the state
store was restarted). open_recs then read `podcast_data.get(...)` on None:
an AttributeError after "Loading...", logged as ERR, and the chat was left on
"Loading..." with nothing to tap. It now answers with `screenOutdated` and a
back button, before any loading text.

The CD gate runs the parts that need no bot requirements (the texts, the
shape of open_recs). The behaviour runs where the bot's requirements are
installed (it imports recsModule, without connecting to Telegram).
Run from the repo root: python app/controller/builders/test_open_recs.py
"""
import ast
import importlib
import os
import sys
import tempfile
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.i18n.messages import get_message  # noqa: E402

LANGUAGES = ("en", "ru", "pt-BR", "es", "de", "he")
_OURS = {"app", "lib", "db", "config", "agent", "constants", "constant_texts"}


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def test_texts():
    english = get_message("screenOutdated", "en")
    _assert("out of date" in english, "the English text says the screen is out of date")
    for lang in LANGUAGES:
        text = get_message("screenOutdated", lang)
        _assert(bool(text) and (lang == "en" or text != english),
                "screenOutdated is translated: %s" % lang)


def test_guard_comes_first():
    path = os.path.join(_ROOT, "app", "controller", "builders", "recsModule.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "open_recs")
    load, guard = fn.body[0], fn.body[1]
    _assert(isinstance(load, (ast.Assign, ast.AnnAssign)) and "get_user_state_data" in ast.dump(load),
            "open_recs reads the podcast state first")
    _assert(isinstance(guard, ast.If) and "state_lost" in ast.dump(guard.test)
            and "podcast_data" in ast.dump(guard.test),
            "and checks it right away, before the loading text and any .get on it")
    _assert("render_outdated_screen" in ast.dump(guard) and isinstance(guard.body[-1], ast.Return),
            "a lost state answers with the outdated-screen message and stops")
    _assert("loading" not in ast.dump(guard), "without a 'Loading...' first")


def import_builder(name):
    """app.controller.builders.<name>, or None where the bot's requirements are
    not installed (the module imports telebot and Telethon, it does not connect)."""
    import config
    config.db_path = os.path.join(tempfile.mkdtemp(prefix="yourcast_screen_state_"), "t.db")
    stub = types.ModuleType("agent.bot_telethon")
    stub.thobot_session_handler = ""
    sys.modules["agent.bot_telethon"] = stub
    try:
        return importlib.import_module("app.controller.builders." + name)
    except ModuleNotFoundError as e:
        if (e.name or "").split(".")[0] in _OURS:
            raise
        print("skip  behaviour: %s is not installed (the bot's requirements)" % e.name)
        return None


class _Stop(Exception):
    pass


def test_behaviour(recs):
    from app.controller.general import notify as notify_module
    renders = []
    capture = lambda chat_id, structures, **kw: renders.append(  # noqa: E731
        (chat_id, structures, kw.get("resending")))
    recs.render_messages = capture
    notify_module.render_messages = capture

    def data(callback):
        return {'chat_id': 4001, 'language_code': 'en', 'callback': callback, 'message': None,
                'united_data': {}, 'route_name': 'recs', 'is_command': False}

    # As in production: the page is read before the state is touched.
    recs.determine_search_query_and_page = lambda *a, **k: {'p': 1}

    # The state is gone, from a button (callback) and from a command.
    # (Before the fix: AttributeError, 'NoneType' object has no attribute 'get'.)
    recs.storage = types.SimpleNamespace(get_user_state_data=lambda chat_id, route: None)
    for callback, label in ((types.SimpleNamespace(id=1), "button"), (None, "command")):
        del renders[:]
        result = recs.open_recs(data(callback))
        _assert(result is False, "%s: open_recs ends with False" % label)
        _assert(len(renders) == 1, "%s: one message, no 'Loading...' first" % label)
        chat_id, structures, resending = renders[0]
        _assert(chat_id == 4001 and structures[0]['text'] == get_message("screenOutdated", "en"),
                "%s: the outdated-screen text" % label)
        _assert(structures[0]['reply_markup'][0][0]['callback_data'] == {'tp': 'bck'},
                "%s: a back button" % label)
        _assert(resending is (callback is None), "%s: edits a button's message, resends a command's" % label)

    # An empty state cannot open a list either.
    recs.storage = types.SimpleNamespace(get_user_state_data=lambda chat_id, route: {})
    del renders[:]
    _assert(recs.open_recs(data(None)) is False and len(renders) == 1, "an empty state is a lost state")

    # A live state goes on as before: 'Loading...' first, then the list.
    recs.storage = types.SimpleNamespace(
        get_user_state_data=lambda chat_id, route: {'id': 5, 'service_name': 'itunes', 'service_id': 1})
    del renders[:]
    recs.determine_search_query_and_page = lambda *a, **k: (_ for _ in ()).throw(_Stop())
    try:
        recs.open_recs(data(None))
        raise AssertionError("the list must have been requested")
    except _Stop:
        pass
    _assert(len(renders) == 1 and renders[0][1][0]['text'] == get_message("loading", "en"),
            "a live state: 'Loading...' first, the list is requested")


def main():
    for case in (test_texts, test_guard_comes_first):
        print("-- %s" % case.__name__)
        case()
    recs = import_builder("recsModule")
    if recs is not None:
        print("-- test_behaviour")
        test_behaviour(recs)
    print("all open_recs checks passed")


if __name__ == "__main__":
    main()
