# -*- coding: utf-8 -*-
"""Covers Telegram cannot fetch: a refused cover is marked and the page goes
at once without it; a background check, once an hour, clears the mark and
caches the file_id when Telegram fetches it again; the buttons of a page
without its picture still update.

Run from the repo root: python app/service/podcast/test_cover.py
(the page and editor parts run where the bot's requirements are installed).
"""
import json
import os
import sys
import tempfile
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.repository.storage import telegram_cache  # noqa: E402
from app.service.podcast import cover  # noqa: E402

URL = 'https://cdn.example/covers/show.png'
REFUSED = Exception('A request to the Telegram API was unsuccessful. Error code: 400. '
                    'Description: Bad Request: failed to get HTTP URL content')


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


class FakeBot:
    def __init__(self, fetches):
        self.fetches, self.sent, self.deleted = fetches, [], []

    def send_photo(self, chat_id, photo):
        self.sent.append((chat_id, photo))
        if not self.fetches:
            raise REFUSED
        return types.SimpleNamespace(message_id=5, photo=[types.SimpleNamespace(file_id='small'),
                                                          types.SimpleNamespace(file_id='FID')])

    def delete_message(self, chat_id, message_id):
        self.deleted.append(message_id)


def test_marks():
    _assert(not cover.known_unreachable(URL), "a cover is tried until Telegram refuses it")
    cover.mark_unreachable(URL)
    _assert(cover.known_unreachable(URL), "refused: marked")
    cover.mark_unreachable('/app/static/no_photo.png')
    _assert(not cover.known_unreachable('/app/static/no_photo.png'), "a local placeholder is never marked")

    refused = FakeBot(fetches=False)
    _assert(cover.recheck(URL, bot=refused, storage_chat_id=-100) is False and cover.known_unreachable(URL),
            "a check Telegram still refuses keeps the mark")
    fetched = FakeBot(fetches=True)
    _assert(cover.recheck(URL, bot=fetched, storage_chat_id=-100) is True, "a check that goes through")
    _assert(not cover.known_unreachable(URL) and telegram_cache.get_file_id(URL, 'img') == 'FID',
            "clears the mark and caches the file_id: the next page shows the cover at once")
    _assert(fetched.deleted == [5], "the check leaves nothing in the storage chat")

    _assert(telegram_cache.claim_once('coverCheck:' + URL, cover.RECHECK_SECONDS)
            and not telegram_cache.claim_once('coverCheck:' + URL, cover.RECHECK_SECONDS),
            "one background check an hour per cover")
    started = []
    cover.recheck_later(URL, check=started.append)
    _assert(started == [], "within the hour no second check starts")


def test_page(cache_db):
    try:
        from app.controller.builders.test_open_recs import import_builder
        page = import_builder('podcastModule')
    except Exception as e:
        print("skip page (%s)" % e.__class__.__name__)
        return
    if page is None:
        return
    rendered, checked = [], []
    keyboard = [[{'text': 'Subscribe', 'callback_data': {'tp': 'subscription'}}]]

    class DB:
        def __init__(self, *_):
            pass

        def get_channel(self, channel_id):
            return {'id': channel_id, 'itunes_id': '42', 'rss_link': None}

        def close(self):
            pass

    def render(chat_id, structures, resending=False):
        rendered.append([s['type'] for s in structures])
        if any(s['type'] == 'image' for s in structures):
            raise REFUSED

    saved = (page.SQLighter, page.storage, page.get_and_set_podcast_data, page.construct_channel_message,
             page.render_messages, page.cover_service.recheck_later)
    page.SQLighter = DB
    page.storage = types.SimpleNamespace(del_user_state_data=lambda *a: None,
                                         get_user_state_data_empty=lambda *a: True)
    page.get_and_set_podcast_data = lambda *a, **k: (True, {'id': 7})
    page.construct_channel_message = lambda *a, **k: [
        {'type': 'text', 'text': 'Show'}, {'type': 'image', 'image': URL, 'reply_markup': keyboard}]
    page.render_messages = render
    page.cover_service.recheck_later = checked.append
    data = {'chat_id': 1, 'language_code': 'en', 'callback': None, 'united_data': {},
            'message': types.SimpleNamespace(text=json.dumps({'id': 7}))}
    try:
        telegram_cache.clear_image_unreachable(URL)
        page.channel_query(data)
        _assert(rendered == [['text'], ['text', 'image'], ['text']] and cover.known_unreachable(URL),
                "first refusal: the page falls back to text with its buttons, and the cover is marked")
        del rendered[:]
        page.channel_query(data)
        _assert(rendered == [['text'], ['text']] and checked == [URL],
                "marked: the page goes at once without the cover, the check runs in the background")
        _assert(page.without_cover(page.construct_channel_message())[0]['reply_markup'] == keyboard,
                "the buttons that live on the cover come with the text")
    finally:
        (page.SQLighter, page.storage, page.get_and_set_podcast_data, page.construct_channel_message,
         page.render_messages, page.cover_service.recheck_later) = saved


def test_editor():
    try:
        from lib.telegram.general import message_master
    except Exception as e:
        print("skip editor (%s)" % e.__class__.__name__)
        return
    calls = []

    class Bot:
        def __init__(self, markup_error=None):
            self.markup_error = markup_error

        def edit_message_media(self, **kwargs):
            raise Exception('Bad Request: there is no media in the message to edit')

        def edit_message_reply_markup(self, **kwargs):
            calls.append(kwargs['message_id'])
            if self.markup_error:
                raise self.markup_error

    saved = (message_master.bot, message_master.prepare_images)
    message_master.prepare_images = lambda structures: structures
    structure = {'type': 'image', 'image': URL, 'reply_markup': [[{'text': 'Rate', 'callback_data': {'tp': 'rate'}}]]}
    try:
        message_master.bot = Bot()
        message_master.message_editor(1, dict(structure), 77)
        _assert(calls == [77], "a page without its picture: a button refreshes the keyboard")
        message_master.bot = Bot(Exception('Bad Request: message is not modified: specified new message content '
                                           'and reply markup are exactly the same as a current content and reply '
                                           'markup of the message'))
        message_master.message_editor(1, dict(structure), 78)
        _assert(calls == [77, 78], "the same keyboard again is not an error")
    finally:
        message_master.bot, message_master.prepare_images = saved


def main():
    with tempfile.TemporaryDirectory() as tmp:
        saved = telegram_cache.db_path
        telegram_cache.db_path = os.path.join(tmp, 'cache.sqlite')
        try:
            test_marks()
            test_page(telegram_cache.db_path)
            test_editor()
        finally:
            telegram_cache.db_path = saved
    print("all cover checks passed")


if __name__ == "__main__":
    main()
