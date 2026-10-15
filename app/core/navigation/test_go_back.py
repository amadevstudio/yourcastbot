# -*- coding: utf-8 -*-
""""Back" to a screen that does not exist opens the menu instead of failing.

A stored screen stack outlives the code. On 15 Oct 2026 about a third of them
held names from the bot before its rewrite ('pc', 'srch', 'welc': KeyError at
the first "Back"), and 'empty' is a route with no screen (None: AttributeError).
Both ended the tap with an ERR and no answer.

Runs without the bot's requirements: the controller, the routes and the
storage are replaced by stubs, only goBackModule is real.
Run from the repo root: python app/core/navigation/test_go_back.py
"""
import importlib.util
import os
import sys
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


class Storage:
    def __init__(self, states):
        self.states = list(states)
        self.cleared = False

    def get_user_prev_curr_states(self, chat_id):
        if len(self.states) < 2:
            return None, (self.states[0] if self.states else None)
        return self.states[-2], self.states[-1]

    def get_user_states(self, chat_id):
        return self.states

    def del_user_curr_state(self, chat_id):
        self.states.pop()

    def del_user_state_data(self, chat_id, route):
        pass

    def clear_user_storage(self, chat_id):
        self.cleared = True
        self.states = []

    def add_user_state(self, chat_id, state):
        self.states.append(state)


def _load(states):
    """goBackModule over stubs; returns (module, storage, opened screens)."""
    opened = []
    routes = {
        'menu': {'method': lambda params: opened.append(params['route_name'])},
        'subs': {'method': lambda params: opened.append(params['route_name']), 'routes': []},
        'recs': {'method': lambda params: None},
        'empty': None,
    }
    storage = Storage(states)
    stubs = {
        'app.core.controller': types.SimpleNamespace(
            construct_params=lambda callback, message, route, is_step_back=False: {'route_name': route}),
        'app.routes.routes': types.SimpleNamespace(RouteMap=types.SimpleNamespace(ROUTES=routes)),
        'app.routes.routes_list': types.SimpleNamespace(AvailableRoutes=str),
        'app.routes.ptypes': types.SimpleNamespace(ControllerParams=dict),
        'app.repository.storage': types.SimpleNamespace(storage=storage),
        'lib.tools.logger': types.SimpleNamespace(
            logger=types.SimpleNamespace(warn=lambda *a: None)),
    }
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location(
            "go_back_under_test", os.path.join(_ROOT, "app/core/navigation/goBackModule.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for name, old in saved.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
    return module, storage, opened


def _back(states):
    module, storage, opened = _load(states)
    result = module.go_back({'chat_id': 1, 'callback': None, 'message': None})
    return result, storage, opened


def test_is_screen():
    module, _, _ = _load([])
    routes = {'menu': {'method': print}, 'empty': None, 'bare': {}}
    _assert(module.is_screen('menu', routes), "a route with a method is a screen")
    _assert(not module.is_screen('empty', routes), "'empty' is no screen")
    _assert(not module.is_screen('bare', routes), "a route without a method is no screen")
    _assert(not module.is_screen('pc', routes), "an old name is no screen")


def test_back_to_a_live_screen_is_as_before():
    result, storage, opened = _back(['menu', 'subs', 'recs'])
    _assert(opened == ['subs'] and storage.states == ['menu', 'subs'], "Back opens the previous screen")
    _assert(result is False and not storage.cleared, "the stack is not reset")


def test_back_to_an_old_name_opens_the_menu():
    for old in ('pc', 'srch', 'welc', 'EMPTYTEXTSTATE'):
        result, storage, opened = _back([old, 'recs'])
        _assert(opened == ['menu'], "%s: the menu is shown" % old)
        _assert(storage.states == ['menu'] and result is False,
                "%s: a clean stack with the menu, no state added after" % old)


def test_back_to_empty_opens_the_menu():
    _, storage, opened = _back(['empty', 'recs'])
    _assert(opened == ['menu'] and storage.states == ['menu'], "'empty' before the screen: the menu")


def test_no_previous_screen_does_nothing():
    result, storage, opened = _back(['recs'])
    _assert(result is None and opened == [] and storage.states == ['recs'], "first screen: nothing happens")


def test_custom_prev_is_checked_too():
    module, storage, opened = _load(['menu', 'recs'])
    module.go_back({'chat_id': 1, 'callback': None, 'message': None}, custom_prev='pc')
    _assert(opened == ['menu'], "a caller's own old name does not crash either")


if __name__ == "__main__":
    test_is_screen()
    test_back_to_a_live_screen_is_as_before()
    test_back_to_an_old_name_opens_the_menu()
    test_back_to_empty_opens_the_menu()
    test_no_previous_screen_does_nothing()
    test_custom_prev_is_checked_too()
    print("all go_back checks passed")
