# -*- coding: utf-8 -*-
"""Covers Telegram cannot fetch: a refused cover is marked and uploaded as a
file we download, so the page has its picture on the first open; when the
host does not give it to us either, the page goes without it and a
background check, once an hour, clears the mark and caches the file_id
later; the buttons of a page without its picture still update.

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
    """fetches: Telegram gets the URL itself; uploads: it takes the file we send."""
    def __init__(self, fetches, uploads=True):
        self.fetches, self.uploads, self.sent, self.deleted = fetches, uploads, [], []

    def send_photo(self, chat_id, photo):
        self.sent.append((chat_id, photo))
        if isinstance(photo, str) and not self.fetches:
            raise REFUSED
        if isinstance(photo, bytes) and not self.uploads:
            raise Exception('Bad Request: IMAGE_PROCESS_FAILED')
        return types.SimpleNamespace(message_id=5, photo=[types.SimpleNamespace(file_id='small'),
                                                          types.SimpleNamespace(file_id='FID')])

    def delete_message(self, chat_id, message_id):
        self.deleted.append(message_id)


class FakeResponse:
    def __init__(self, status=200, kind='image/jpeg', body=b'JPEG'):
        self.status_code, self.headers, self.body = status, {'Content-Type': kind}, body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_content(self, size):
        for i in range(0, len(self.body), size):
            yield self.body[i:i + size]


def host(response=None, error=None):
    def get(url, **kwargs):
        if error:
            raise error
        return response or FakeResponse()
    return get


def test_marks():
    _assert(not cover.known_unreachable(URL), "a cover is tried until Telegram refuses it")
    cover.mark_unreachable(URL)
    _assert(cover.known_unreachable(URL), "refused: marked")
    cover.mark_unreachable('/app/static/no_photo.png')
    _assert(not cover.known_unreachable('/app/static/no_photo.png'), "a local placeholder is never marked")

    refused = FakeBot(fetches=False)
    _assert(cover.recheck(URL, bot=refused, storage_chat_id=-100, get=host(error=OSError('timed out'))) is False
            and cover.known_unreachable(URL), "Telegram refuses the URL and the host does not answer us: marked")
    _assert(cover.recheck(URL, bot=refused, storage_chat_id=-100, get=host(FakeResponse(kind='text/html'))) is False
            and cover.known_unreachable(URL) and len(refused.sent) == 2, "a page that is not an image is not uploaded")
    big = FakeResponse(body=b'x' * (cover.MAX_COVER_BYTES + 1))
    _assert(cover.recheck(URL, bot=refused, storage_chat_id=-100, get=host(big)) is False
            and cover.known_unreachable(URL), "nor a file far bigger than a cover")
    _assert(cover.recheck(URL, bot=FakeBot(fetches=False, uploads=False), storage_chat_id=-100, get=host()) is False
            and cover.known_unreachable(URL), "an upload Telegram refuses keeps the mark")

    fetched = FakeBot(fetches=True)
    _assert(cover.recheck(URL, bot=fetched, storage_chat_id=-100, get=host(error=AssertionError('no download')))
            is True and fetched.sent == [(-100, URL)], "Telegram fetches the URL again: nothing downloaded")
    _assert(not cover.known_unreachable(URL) and telegram_cache.get_file_id(URL, 'img') == 'FID',
            "clears the mark and caches the file_id: the next page shows the cover at once")
    _assert(fetched.deleted == [5], "the check leaves nothing in the storage chat")

    cover.mark_unreachable(URL)
    telegram_cache.add_file_id(URL, 'old', 'img')
    uploaded = FakeBot(fetches=False)
    _assert(cover.recheck(URL, bot=uploaded, storage_chat_id=-100, get=host()) is True
            and uploaded.sent == [(-100, URL), (-100, b'JPEG')],
            "Telegram refuses the URL but the host gives the file to us: uploaded")
    _assert(not cover.known_unreachable(URL) and telegram_cache.get_file_id(URL, 'img') == 'FID'
            and uploaded.deleted == [5], "the uploaded cover is shown from then on")

    cover.mark_unreachable(URL)
    now = FakeBot(fetches=False)
    _assert(cover.upload_now(URL, bot=now, storage_chat_id=-100, get=host()) is True
            and now.sent == [(-100, b'JPEG')], "a page that waits: the cover is uploaded at once, no URL try")
    _assert(not cover.known_unreachable(URL) and telegram_cache.get_file_id(URL, 'img') == 'FID'
            and now.deleted == [5], "its file_id is cached and the mark goes")
    _assert(cover.upload_now(URL, bot=now, storage_chat_id=-100, get=host()) is False and len(now.sent) == 1,
            "one upload try an hour per cover: a dead host does not slow every open")
    other = URL + '?v=2'
    _assert(cover.upload_now(other, bot=now, storage_chat_id=-100, get=host(error=OSError('timed out'))) is False,
            "a host that does not answer us: no upload")
    _assert(cover.upload_now('/app/static/no_photo.png', bot=now, storage_chat_id=-100, get=host()) is False,
            "a local placeholder is never uploaded")

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

    uploaded, upload_works = [], [False]

    def render(chat_id, structures, resending=False):
        rendered.append([s['type'] for s in structures])
        if any(s['type'] == 'image' for s in structures) and not uploaded:
            raise REFUSED  # Telegram refuses the URL; a cached file_id goes

    def upload_now(image):
        if upload_works[0]:
            uploaded.append(image)
        return upload_works[0]

    saved = (page.SQLighter, page.storage, page.get_and_set_podcast_data, page.construct_channel_message,
             page.render_messages, page.cover_service.recheck_later, page.cover_service.upload_now)
    page.SQLighter = DB
    page.storage = types.SimpleNamespace(del_user_state_data=lambda *a: None,
                                         get_user_state_data_empty=lambda *a: True)
    page.get_and_set_podcast_data = lambda *a, **k: (True, {'id': 7})
    page.construct_channel_message = lambda *a, **k: [
        {'type': 'text', 'text': 'Show'}, {'type': 'image', 'image': URL, 'reply_markup': keyboard}]
    page.render_messages = render
    page.cover_service.recheck_later = checked.append
    page.cover_service.upload_now = upload_now
    data = {'chat_id': 1, 'language_code': 'en', 'callback': None, 'united_data': {},
            'message': types.SimpleNamespace(text=json.dumps({'id': 7}))}
    try:
        telegram_cache.clear_image_unreachable(URL)
        page.channel_query(data)
        _assert(rendered == [['text'], ['text', 'image'], ['text']] and cover.known_unreachable(URL),
                "first refusal: the page falls back to text with its buttons, and the cover is marked")
        _assert(checked == [URL], "and checked in the background at once: the next open may have it")
        del rendered[:]
        page.channel_query(data)
        _assert(rendered == [['text'], ['text']] and checked == [URL, URL],
                "marked: the page goes at once without the cover, the check runs in the background")
        _assert(page.without_cover(page.construct_channel_message())[0]['reply_markup'] == keyboard,
                "the buttons that live on the cover come with the text")

        upload_works[0] = True
        del rendered[:], checked[:]
        telegram_cache.clear_image_unreachable(URL)
        page.channel_query(data)
        _assert(rendered == [['text'], ['text', 'image'], ['text', 'image']] and uploaded == [URL]
                and not checked, "first refusal, the host gives us the file: the first open has its picture")
        del rendered[:], uploaded[:]
        telegram_cache.mark_image_unreachable(URL)
        page.channel_query(data)
        _assert(rendered == [['text'], ['text', 'image']] and uploaded == [URL] and not checked,
                "marked: uploaded at once, no wait for Telegram's refusal, the page with its picture")
    finally:
        (page.SQLighter, page.storage, page.get_and_set_podcast_data, page.construct_channel_message,
         page.render_messages, page.cover_service.recheck_later, page.cover_service.upload_now) = saved


def test_page_buttons():
    """Notify, rate and unsubscribe on a podcast page refresh its keyboard, never
    its media: Telegram turns a text message into a photo by editMessageMedia, so
    the page sent without its cover lost its text once the cover came through."""
    try:
        from app.controller.builders.test_open_recs import import_builder
        page = import_builder('podcastModule')
    except Exception as e:
        print("skip page buttons (%s)" % e.__class__.__name__)
        return
    if page is None:
        return
    keyboards, keyboard = [], [[{'text': 'Listen', 'callback_data': {'tp': 'recs', 'p': 1}}]]

    class DB:
        def __init__(self, *_):
            pass

        def turn_notify_tg(self, *a):
            pass

        def rate_podcast(self, *a):
            pass

        def get_uccs_count_by_tg(self, *a):
            return 1

        def getUserSubscriptionByTg(self, *a):
            return None

        def close(self):
            pass

    def media_edit(*a, **k):
        raise AssertionError("a page button edited the media")

    from app.service.podcast import subscription
    saved = (page.SQLighter, page.storage, page.notify, page.set_podcast_data, page.get_and_set_podcast_data,
             page.construct_channel_message, page.keyboard_editor, page.render_messages, subscription.remove_sub,
             getattr(page, 'message_editor', None))
    page.SQLighter = DB
    page.storage = types.SimpleNamespace(get_user_state_data=lambda *a: {'id': 7},
                                         set_user_state_data=lambda *a: None)
    page.notify = lambda *a, **k: None
    page.set_podcast_data = lambda *a: None
    page.get_and_set_podcast_data = lambda *a, **k: (True, {'id': 7})
    page.construct_channel_message = lambda *a, **k: [
        {'type': 'text', 'text': 'Show'}, {'type': 'image', 'image': URL, 'reply_markup': keyboard}]
    page.keyboard_editor = lambda chat_id, structure, message_id: keyboards.append(
        (structure['reply_markup'], message_id))
    page.render_messages = page.message_editor = media_edit
    subscription.remove_sub = lambda *a: 'Show'
    state = {'id': 7, 'notify': True, 'rate': 3, 'subscribed': True, 'service_id': '42', 'service_name': 'itunes'}

    def data():
        return {'chat_id': 1, 'language_code': 'en', 'message': None, 'united_data': dict(state),
                'callback': types.SimpleNamespace(id=1, message=types.SimpleNamespace(message_id=55))}
    try:
        page.change_channel_notify(data())
        page.rate(data())
        page.switch_subscription(data())
        _assert(keyboards == [(keyboard, 55)] * 3,
                "notify, rate and unsubscribe refresh the keyboard of the tapped page, not its media")
    finally:
        (page.SQLighter, page.storage, page.notify, page.set_podcast_data, page.get_and_set_podcast_data,
         page.construct_channel_message, page.keyboard_editor, page.render_messages,
         subscription.remove_sub, page.message_editor) = saved


def test_keyboard_editor():
    try:
        from lib.telegram.general import message_master
    except Exception as e:
        print("skip keyboard editor (%s)" % e.__class__.__name__)
        return
    calls = []

    class Bot:
        def __init__(self, markup_error=None):
            self.markup_error = markup_error

        def edit_message_media(self, **kwargs):
            raise AssertionError("the keyboard editor edited the media")

        def edit_message_reply_markup(self, **kwargs):
            calls.append(kwargs['message_id'])
            if self.markup_error:
                raise self.markup_error

    saved = message_master.bot
    structure = {'type': 'image', 'image': URL, 'reply_markup': [[{'text': 'Rate', 'callback_data': {'tp': 'rate'}}]]}
    try:
        message_master.bot = Bot()
        message_master.keyboard_editor(1, dict(structure), 77)
        _assert(calls == [77], "the keyboard editor changes the buttons only")
        message_master.bot = Bot(Exception('Bad Request: message is not modified: specified new message content '
                                           'and reply markup are exactly the same as a current content and reply '
                                           'markup of the message'))
        message_master.keyboard_editor(1, dict(structure), 78)
        _assert(calls == [77, 78], "the same keyboard again is not an error")
    finally:
        message_master.bot = saved


def test_screen_resent():
    """A screen stored as text whose message is now media (a page that became its
    cover before this fix) is sent again, not left on "no text to edit"."""
    try:
        from lib.telegram.general import message_master
    except Exception as e:
        print("skip screen resent (%s)" % e.__class__.__name__)
        return
    calls = []

    def master(bot, chat_id, resending=False, message_structures=None, previous_message_structures=None):
        calls.append(resending)
        if not resending:
            raise message_master.ApiTelegramException(
                'editMessageText', None, {'error_code': 400,
                                          'description': 'Bad Request: there is no text in the message to edit'})
        return [{'id': 9, 'type': 'text'}]

    saved = (message_master.message_master, message_master.storage)
    message_master.message_master = master
    message_master.storage = types.SimpleNamespace(
        get_user_resend_flag=lambda *a: False, get_message_structures=lambda *a: [{'id': 55, 'type': 'text'}],
        set_user_message_structures=lambda *a: None, del_user_resend_flag=lambda *a: None)
    try:
        result = message_master.render_messages(1, [{'type': 'text', 'text': 'Episodes'}])
        _assert(calls == [False, True] and result == [{'id': 9, 'type': 'text'}],
                "no text to edit: the screen is sent again, once")
    finally:
        message_master.message_master, message_master.storage = saved


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
            test_page_buttons()
            test_keyboard_editor()
            test_screen_resent()
            test_editor()
        finally:
            telegram_cache.db_path = saved
    print("all cover checks passed")


if __name__ == "__main__":
    main()
