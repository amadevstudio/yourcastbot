# -*- coding: utf-8 -*-
"""/settings is a short list of sections; each section is its own screen.

The first screen held every setting at once (four episode-text buttons, the
reminders switch and their help text), and every new setting would have made
it longer. Now: /settings -> Episode text, AI summaries (when AI is on),
Reminders (without a plan only);
each button names what is set. A button that leads nowhere is the failure to
lock: every button of the three screens is a route, an action or "back".

Needs the bot's requirements (skips without them).
Run from the repo root: python app/controller/builders/test_settings_screens.py
"""
import os
import sys
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.controller.builders.test_open_recs import import_builder  # noqa: E402
from app.i18n.messages import get_message  # noqa: E402

LANGUAGES = ("ru", "en", "pt-BR", "es", "de", "he")


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _tps(screen):
    return [button['callback_data']['tp'] for row in screen[0]['reply_markup'] for button in row]


def _texts(screen):
    return [button['text'] for row in screen[0]['reply_markup'] for button in row]


def test_sections(settings):
    user = {'episode_format': None, 'nosub_digest_enabled': 1}
    settings._read_user = lambda chat_id: (user, False)
    free = settings.construct_settings_message('en', 1)
    _assert(_tps(free) == ['settsText', 'settsRem', 'bck'],
            "without a plan: both sections, then Back")
    _assert(get_message("episodeFormatRich", "en") in _texts(free)[0],
            "the episode text button shows what is set (the default: one message)")
    _assert(_texts(free)[1].endswith(settings.reminders_mark(True)), "the reminders button shows on")

    user['nosub_digest_enabled'] = 0
    user['episode_format'] = 'meta'
    off = settings.construct_settings_message('en', 1)
    _assert(get_message("episodeFormatMeta", "en") in _texts(off)[0], "a changed format is shown")
    _assert(_texts(off)[1].endswith(settings.reminders_mark(False)), "and reminders off")

    settings._read_user = lambda chat_id: (user, True)
    paid = settings.construct_settings_message('en', 1)
    _assert(_tps(paid) == ['settsText', 'bck'], "with a plan: no reminders section")

    settings.ai_summary.enabled = lambda: True
    try:
        ai_on = settings.construct_settings_message('en', 1)
        _assert(_tps(ai_on) == ['settsText', 'settsSum', 'bck'], "AI on: the summaries section")
        _assert(_texts(ai_on)[1].endswith(get_message("summaryLanguageOriginal", "en")),
                "it shows the default: the episode's language")
        user['flags'] = '{"summary_language": "mine"}'
        _assert(_texts(settings.construct_settings_message('en', 1))[1].endswith(
            get_message("summaryLanguageMine", "en")), "and the user's choice")
    finally:
        settings.ai_summary.enabled = lambda: False


def test_pages(settings):
    user = {'episode_format': 'caption', 'nosub_digest_enabled': 1}
    settings._read_user = lambda chat_id: (user, False)
    page = settings.construct_episode_text_message('en', 1)
    marked = [text for text in _texts(page) if text.startswith('✅')]
    _assert(len(_tps(page)) == 5 and _tps(page)[-1] == 'bck', "episode text: four formats, Back")
    _assert(len(marked) == 1 and get_message("episodeFormatCaption", "en") in marked[0],
            "episode text: the current format is the marked one")
    _assert(get_message("episodeFormatHelp", "en") in page[0]['text'], "episode text: the explanation is here")
    _assert(get_message("episodeFormatHelp", "en") not in settings.construct_settings_message('en', 1)[0]['text'],
            "and no longer on the first screen")

    page = settings.construct_summary_message('en', 1)
    marked = [text for text in _texts(page) if text.startswith('✅')]
    _assert(_tps(page) == ['sumLangOrig', 'sumLangMine', 'sumAuto', 'bck'],
            "summaries: two languages, summaries of new episodes, Back")
    _assert(get_message("summaryAutoOff", "en") in _texts(page), "summaries of new episodes: off by default")
    _assert(len(marked) == 1 and get_message("summaryLanguageOriginal", "en") in marked[0],
            "summaries: the episode's language by default")
    user['flags'] = '{"summary_language": "mine"}'
    marked = [text for text in _texts(settings.construct_summary_message('en', 1)) if text.startswith('✅')]
    _assert(len(marked) == 1 and get_message("summaryLanguageMine", "en") in marked[0],
            "summaries: the user's choice is marked")
    user['flags'] = '{"summary_language": "mine", "auto_summary": 1}'
    _assert(get_message("summaryAutoOn", "en") in _texts(settings.construct_summary_message('en', 1)),
            "summaries of new episodes: the button says it is on")

    page = settings.construct_reminders_message('en', 1)
    _assert(_tps(page) == ['digestToggle', 'bck'], "reminders: the switch, Back")
    _assert(get_message("nosubDigestRemindersHelp", "en") in page[0]['text'], "reminders: the explanation is here")


def test_every_button_leads_somewhere(settings):
    from app.routes.routes import RouteMap
    known = {'bck'} | set(RouteMap.ROUTES)
    for route in RouteMap.ROUTES.values():
        known |= set((route or {}).get('actions', {}))
    settings._read_user = lambda chat_id: ({'episode_format': None, 'nosub_digest_enabled': 1}, False)
    settings.ai_summary.enabled = lambda: True
    try:
        for name in ('construct_settings_message', 'construct_episode_text_message',
                     'construct_summary_message', 'construct_reminders_message'):
            for tp in _tps(getattr(settings, name)('en', 1)):
                _assert(tp in known, "%s: '%s' is a route, an action or Back" % (name, tp))
    finally:
        settings.ai_summary.enabled = lambda: False
    reachable = RouteMap.ROUTES['setts']['routes']
    _assert(set(reachable) == {'settsText', 'settsSum', 'settsRem'}, "/settings lists its sections as routes")
    for route in reachable:
        _assert(RouteMap.ROUTES[route]['method'] and RouteMap.ROUTES[route]['available_from'] == ['call'],
                "%s opens from a button" % route)


def test_languages(settings):
    settings._read_user = lambda chat_id: ({'episode_format': None, 'nosub_digest_enabled': 1}, False)
    for language in LANGUAGES:
        for name in ('construct_settings_message', 'construct_episode_text_message',
                     'construct_summary_message', 'construct_reminders_message'):
            screen = getattr(settings, name)(language, 1)
            _assert(screen[0]['text'].strip() and all(_texts(screen)), "%s %s" % (language, name))


def test_redraw(settings):
    edits, renders = [], []
    settings.message_editor = lambda chat_id, screen, message_id: edits.append(message_id)
    settings.render_messages = lambda chat_id, screen: renders.append(chat_id)
    callback = types.SimpleNamespace(message=types.SimpleNamespace(message_id=77))
    data = {'chat_id': 5, 'callback': callback}
    settings._redraw(data, [{'type': 'text', 'text': 'x'}])
    _assert(edits == [77] and not renders, "a button edits its own screen")

    def cannot_edit(*args):
        raise RuntimeError("message is not modified")
    settings.message_editor = cannot_edit
    settings._redraw(data, [{'type': 'text', 'text': 'x'}])
    _assert(renders == [5], "a screen that cannot be edited is sent again")
    del renders[:]
    settings._redraw({'chat_id': 5, 'callback': None}, [{'type': 'text', 'text': 'x'}])
    _assert(renders == [5], "a command sends a message")


def test_auto_summary_toggle(settings):
    import db.tariff_rows as tariff_rows
    flags, toasts = {}, []

    class DB:
        def __init__(self, *_):
            pass

        def get_user_flag(self, chat_id, name):
            return flags.get(name)

        def set_user_flag(self, chat_id, name, value=1):
            flags[name] = value

        def close(self):
            pass

    saved = (settings.SQLighter, settings.notify, settings._redraw, tariff_rows.running_plan_level)
    settings.SQLighter, settings._redraw = DB, lambda data, screen: None
    settings.notify = lambda call, message, text, alert=False: toasts.append((text, alert))
    data = {'chat_id': 5, 'callback': None, 'message': None, 'language_code': 'en'}
    try:
        tariff_rows.running_plan_level = lambda chat_id, database=None: 0
        settings.toggle_auto_summary(data)
        _assert(flags['auto_summary'] == 1 and toasts[-1] == (get_message('summaryAutoNeedsPlan', 'en'), True),
                "no plan: turned on, and an alert says they come with a plan")
        settings.toggle_auto_summary(data)
        _assert(flags['auto_summary'] == 0 and toasts[-1] == (get_message('summaryAutoOff', 'en'), False), "off")
        tariff_rows.running_plan_level = lambda chat_id, database=None: 3
        settings.toggle_auto_summary(data)
        _assert(toasts[-1] == (get_message('summaryAutoOn', 'en'), False), "with a plan: on, a toast")
    finally:
        settings.SQLighter, settings.notify, settings._redraw, tariff_rows.running_plan_level = saved


def main():
    settings = import_builder('settingsModule')
    if settings is None:
        return
    settings.ai_summary.enabled = lambda: False  # the local constants decide nothing here
    test_sections(settings)
    test_pages(settings)
    test_every_button_leads_somewhere(settings)
    test_languages(settings)
    test_redraw(settings)
    test_auto_summary_toggle(settings)
    print("all settings screen checks passed")


if __name__ == "__main__":
    main()
