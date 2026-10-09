# -*- coding: utf-8 -*-
"""A button of an old screen: the saved state is gone, the handler says so.

Seen once a day on the episode list (test_open_recs.py). The same assumption
sits in the handlers that subscript the saved state: subscribe/unsubscribe,
notifications, remove_sub, and the two Telegram-channel pages. A lost state is
None or missing keys (the central loader hands `{}`), and they ended in a
KeyError/TypeError; remove_sub after the unsubscription was already written
to the database. The guards ask for exactly the keys each handler subscripts
anyway, so a live state is never refused.

The CD gate runs state_lost and the shape of the handlers (no bot
requirements); the behaviour runs where they are installed.
Run from the repo root: python app/controller/builders/test_screen_state.py
"""
import ast
import os
import sys
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.controller.builders.test_open_recs import import_builder  # noqa: E402
from app.i18n.messages import get_message  # noqa: E402
from app.routes.screen_state import state_lost  # noqa: E402

OUTDATED = get_message("screenOutdated", "en")


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def test_state_lost():
    _assert(state_lost(None) and state_lost({}), "no state, an empty state: lost")
    _assert(not state_lost({'id': None}), "a state with no keys asked for is live")
    _assert(state_lost({'id': 1}, 'id', 'service_id'), "a missing key: lost")
    _assert(not state_lost({'id': None, 'service_id': None}, 'id', 'service_id'),
            "None values are live: a podcast not in the database has id None")
    _assert(not state_lost({'notify': False}, 'notify'), "False is a value too")


def _function(path, name):
    tree = ast.parse(open(os.path.join(_ROOT, path), encoding="utf-8").read())
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)


def test_guards_come_first():
    cases = (
        ("app/controller/builders/podcastModule.py", "switch_subscription", "notify_outdated_screen"),
        ("app/controller/builders/podcastModule.py", "change_channel_notify", "notify_outdated_screen"),
        ("app/controller/builders/channelModule.py", "open_channel_subs", "render_outdated_screen"),
        ("app/controller/builders/channelModule.py", "change_channel_sub_active", "notify_outdated_screen"),
    )
    for path, name, answer in cases:
        fn = _function(path, name)
        guard = next((n for n in fn.body[:3]
                      if isinstance(n, ast.If) and "state_lost" in ast.dump(n.test)), None)
        _assert(guard is not None and answer in ast.dump(guard),
                "%s: a state_lost guard among the first statements answers with %s" % (name, answer))
        before = fn.body[:fn.body.index(guard)]
        _assert(not any("SQLighter" in ast.dump(n) or "set_user_state_data" in ast.dump(n) for n in before),
                "%s: nothing is written or read from the database before the guard" % name)

    remove = _function("app/service/podcast/subscription.py", "remove_sub")
    none_guard = next(i for i, n in enumerate(remove.body)
                      if isinstance(n, ast.If) and "podcast_data" in ast.dump(n.test)
                      and "Is" in ast.dump(n.test))
    first_write = next(i for i, n in enumerate(remove.body)
                       if isinstance(n, ast.Assign) and "Subscript" in ast.dump(n.targets[0]))
    _assert(none_guard < first_write, "remove_sub: a lost state becomes {} before it is written (as add_sub)")


class _Reached(Exception):
    """Raised by a stub standing where the handler goes on past its guard."""


class _Forbidden:
    """A database that must not be touched before the guard."""

    def __init__(self, *args, **kwargs):
        raise AssertionError("the database was touched on a lost state")


class _Toasts:
    """bot.answer_callback_query / render_messages of notify.py, recorded."""

    def __init__(self, notify_module):
        self.toasts, self.pages = [], []
        notify_module.bot = types.SimpleNamespace(
            answer_callback_query=lambda callback_query_id, show_alert, text: self.toasts.append(
                (text, show_alert)))
        notify_module.render_messages = lambda chat_id, structures, **kw: self.pages.append(
            (chat_id, structures, kw.get("resending")))

    def clear(self):
        del self.toasts[:], self.pages[:]


def _data(united_data=None, callback=True):
    return {
        'chat_id': 4001, 'language_code': 'en', 'message': None, 'route_name': 'podcast',
        'callback': types.SimpleNamespace(id=1, message=None) if callback else None,
        'united_data': {} if united_data is None else united_data,
        'go_back_action': lambda data: "went back", 'is_command': False,
    }


def _expect_outdated(out, call, label):
    out.clear()
    result = call()
    _assert(result is False, "%s: ends with False" % label)
    _assert(out.toasts == [(OUTDATED, True)], "%s: one alert toast, the outdated-screen text" % label)


def test_podcast_actions(podcast, out):
    podcast.SQLighter = _Forbidden
    podcast.set_podcast_data = lambda *a, **k: (_ for _ in ()).throw(_Reached())
    unavailable = {'id': None, 'title': '', 'unavailable': True, 'service_id': None,
                   'service_name': 'itunes', 'subscribed': True}

    for state, label in (({}, "empty"), ({'subscribed': False}, "no podcast ids"),
                         ({'id': 3, 'service_id': 5}, "no service name")):
        _expect_outdated(out, lambda: podcast.switch_subscription(_data(state)),
                         "subscribe, %s state" % label)

    # A live state goes past the guard to its first database access: the
    # state of an unavailable podcast keeps its keys (None values) too.
    for state, label in (({'id': None, 'service_id': 5, 'service_name': 'itunes'}, "a podcast"),
                         (unavailable, "an unavailable podcast")):
        out.clear()
        try:
            podcast.switch_subscription(_data(state))
            raise AssertionError("must have gone on")
        except AssertionError as e:
            _assert("database was touched" in str(e) and not out.toasts,
                    "subscribe, %s: not refused, goes on to the database" % label)

    _expect_outdated(out, lambda: podcast.change_channel_notify(_data({})), "notifications, empty state")
    _expect_outdated(out, lambda: podcast.change_channel_notify(_data({'id': 3})),
                     "notifications, no 'notify' in the state")

    class Db:
        toggled = []

        def __init__(self, *args):
            pass

        def turn_notify_tg(self, chat_id, podcast_id, value):
            Db.toggled.append((chat_id, podcast_id, value))

        def close(self):
            pass

    podcast.SQLighter = Db
    podcast.storage = types.SimpleNamespace(get_user_state_data=lambda chat_id, route: {'id': 7})
    podcast.notify = lambda *a, **k: None
    out.clear()
    try:
        podcast.change_channel_notify(_data({'notify': True, 'id': 7}))
    except _Reached:
        pass
    _assert(Db.toggled == [(4001, 7, False)] and not out.toasts,
            "notifications, a live state: toggled as before")


def test_remove_sub(subscription):
    class Db:
        def __init__(self, *args):
            pass

        def remove_sub(self, u_tg_id, podcast_id, service_id, service_name):
            return "Some Show"

        def close(self):
            pass

    saved = []
    subscription.SQLighter = Db
    subscription.storage = types.SimpleNamespace(
        get_user_state_data=lambda chat_id, route: None,
        set_user_state_data=lambda chat_id, route, value: saved.append((route, dict(value))))
    result = subscription.remove_sub(4001, 5, 77, 'itunes')
    _assert(result == ("Some Show", None), "remove_sub with a lost state: the unsubscription is reported")
    _assert(saved and saved[0][0] == 'podcast' and saved[0][1]['subscribed'] is False,
            "and the state is written clean, not a TypeError after the database write")


def test_channel_pages(channel, out):
    channel.SQLighter = _Forbidden
    channel.storage = types.SimpleNamespace(get_user_state_data=lambda chat_id, route: None)

    out.clear()
    _assert(channel.open_channel_subs(_data()) is False, "channel subs page, lost state: ends with False")
    _assert(len(out.pages) == 1 and out.pages[0][1][0]['text'] == OUTDATED and not out.toasts,
            "the page is replaced by the outdated-screen message")
    _assert(out.pages[0][1][0]['reply_markup'][0][0]['callback_data'] == {'tp': 'bck'}, "with a back button")

    _expect_outdated(out, lambda: channel.change_channel_sub_active(_data({'id': 9})),
                     "channel link toggle, lost channel state")
    channel.storage = types.SimpleNamespace(get_user_state_data=lambda chat_id, route: {'id': 3})
    _expect_outdated(out, lambda: channel.change_channel_sub_active(_data({})),
                     "channel link toggle, no podcast id in the button data")

    out.clear()
    try:
        channel.change_channel_sub_active(_data({'id': 9}))
        raise AssertionError("must have gone on")
    except AssertionError as e:
        _assert("database was touched" in str(e) and not out.toasts,
                "channel link toggle, a live state: not refused")


def main():
    for case in (test_state_lost, test_guards_come_first):
        print("-- %s" % case.__name__)
        case()
    podcast = import_builder("podcastModule")
    channel = import_builder("channelModule")
    if podcast is None or channel is None:
        print("all screen state checks passed (shape only)")
        return
    from app.controller.general import notify as notify_module
    from app.service.podcast import subscription
    out = _Toasts(notify_module)
    for name, case, args in (
            ("test_podcast_actions", test_podcast_actions, (podcast, out)),
            ("test_remove_sub", test_remove_sub, (subscription,)),
            ("test_channel_pages", test_channel_pages, (channel, out))):
        print("-- %s" % name)
        case(*args)
    print("all screen state checks passed")


if __name__ == "__main__":
    main()
