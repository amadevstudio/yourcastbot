"""Private voice collections: download without AI; explicitly confirm output and grouping.

These handlers live outside the route map, so they say to Amplitude themselves: the menu's
button (`voice_help`), each recording sent (`voice_received {seconds}` or `{rejected}`) and each
start (`voice_requested {output, mode, recordings, seconds, allowed}`); what comes of it is the
worker's `summary_ready` / `transcript_ready` with `source: voice`.
Lock: python tools/botsim/test_voice.py"""
import asyncio
import collections
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path

from config import work_dir
from db import ai, voice as batches
from lib.system.disk_budget import DiskBudget

MAX_BYTES = 20 * 1024 * 1024
MAX_SECONDS = 3600
LANGUAGE_FLAG = 'voice_summary_language'
_active = {}
_budget = None


def audio_path(ref):
    if not re.fullmatch(r'v_[a-f0-9]{20}', ref):
        raise ValueError('not a voice reference')
    return str(Path(work_dir) / 'records' / 'voices' / (ref + '.ogg'))


def remove_audio(ref):
    if re.fullmatch(r'v_[a-f0-9]{20}', ref):
        Path(audio_path(ref)).unlink(missing_ok=True)


def cleanup():
    batches.cleanup()
    ai.prune_voices()
    c = ai.connect()
    try:
        live = {row[0] for row in c.execute("SELECT ref FROM ai_requests WHERE status IN ('uploading','pending','working')")}
        live.update(row[0] for row in c.execute('SELECT i.ref FROM voice_items i JOIN voice_batches b ON b.ref=i.batch '
                                                'WHERE b.expires_at>?', (time.time(),)))
    finally:
        c.close()
    for path in (Path(work_dir) / 'records' / 'voices').glob('v_*.ogg'):
        try:
            if path.stem not in live and path.stat().st_mtime < time.time() - 3600:
                path.unlink(missing_ok=True)
        except FileNotFoundError:
            pass


def _remember_language(chat_id, value):
    from config import db_path
    from db.sqliteAdapter import SQLighter
    db = SQLighter(db_path)
    try:
        db.set_user_flag(chat_id, LANGUAGE_FLAG, value)
    finally:
        db.close()


def preference(chat_id):
    from config import db_path
    from db.sqliteAdapter import SQLighter
    db = SQLighter(db_path)
    try:
        return db.get_user_flag(chat_id, LANGUAGE_FLAG)
    finally:
        db.close()


def language(chat_id, ui_lang):
    from app.service.ai import summary
    return summary.summary_language(preference(chat_id), ui_lang)


ICONS = {'voiceEach': '🗂 ', 'voiceTogether': '🧩 ', 'voiceBack': '⬅️ ', 'voiceLanguage': '🌐 ',
         'voiceCancel': '🗑 ', 'voiceLanguageOriginal': '🎙 ', 'summaryLanguageMine': '🌍 '}


def button(key, lang, payload):
    from app.i18n.messages import get_message
    return {'text': ICONS.get(key, '') + get_message(key, lang),
            'callback_data': json.dumps({'tp': 'v', 'p': payload}, separators=(',', ':'))}


def running(ref):
    return ai._one(None, "SELECT a.id FROM ai_requests a JOIN voice_runs r ON r.request_id=a.id "
                        "WHERE r.batch=? AND a.status IN ('uploading','pending','working') LIMIT 1", (ref,)) is not None


def progress_line(ref, lang):
    from app.i18n.messages import get_message as tr
    counts = batches.progress(ref)
    total = sum(counts.values())
    if not total:
        return ''
    if counts.get('uploading'):
        return '\n' + tr('voiceDownloading', lang).format(done=total - counts['uploading'], total=total)
    return '\n' + tr('voiceWorking', lang).format(done=counts.get('done', 0) + counts.get('failed', 0), total=total)


def screen(ref, chat_id, lang):
    from app.i18n.messages import get_message as tr
    from app.service.ai.offer import length_text
    found, rows, needed = batches.quote(ref, chat_id)
    text = tr('voiceCollected', lang).format(count=len(rows), duration=length_text(sum(r['seconds'] for r in rows), lang))
    if running(ref):
        return {'type': 'text', 'text': text + '\n\n' + tr('voiceProcessing', lang) + progress_line(ref, lang),
                'reply_markup': [[button('voiceBack', lang, ref + ':help')]]}
    if any(r['status'] != 'ready' for r in rows):
        text += '\n\n' + tr('voiceReceiving', lang)
        keyboard = [[button('voiceCancel', lang, ref + ':cancel')]]
    elif not rows:
        text += '\n\n' + tr('voiceSend', lang)
        keyboard = []
    elif len(rows) == 1 and not found['selected']:
        # one recording has nothing to group: the result button starts it
        text += '\n\n' + tr('voiceChooseOutput', lang)
        text += '\n' + tr('voiceCost', lang).format(duration=length_text(needed, lang))
        suffix = ':e:%d:%d' % (found['revision'], needed)
        keyboard = [[button('voiceSummary', lang, ref + ':s' + suffix), button('voiceText', lang, ref + ':t' + suffix)]]
    elif found['selected']:
        kind = 's' if found['selected'] == 'summary' else 't'
        text += '\n\n' + tr('voiceSummary' if kind == 's' else 'voiceText', lang)
        text += '\n' + tr('voiceCost', lang).format(duration=length_text(needed, lang))
        text += '\n' + tr('voiceChooseMode', lang)
        prefix = ref + ':' + kind + ':'
        suffix = ':%d:%d' % (found['revision'], needed)
        keyboard = [[button('voiceEach', lang, prefix + 'e' + suffix),
                     button('voiceTogether', lang, prefix + 'a' + suffix)],
                    [button('voiceBack', lang, ref + ':back')]]
    else:
        text += '\n\n' + tr('voiceChooseOutput', lang)
        keyboard = [[button('voiceSummary', lang, ref + ':s'), button('voiceText', lang, ref + ':t')]]
    if not running(ref):
        if preference(chat_id) is None:
            # asked until the first summary is started; after that it lives in /settings
            text += '\n\n' + tr('voiceLanguage', lang) + ': ' + tr('voiceLanguageOriginal', lang)
            keyboard.append([button('voiceLanguage', lang, ref + ':lang')])
        if found['state'] == 'collecting' and rows and all(r['status'] == 'ready' for r in rows):
            keyboard.append([button('voiceCancel', lang, ref + ':cancel')])
    if not any(item['text'] == tr('voiceBack', lang) for row in keyboard for item in row):
        keyboard.append([button('voiceBack', lang, ref + ':help')])
    return {'type': 'text', 'text': text, 'reply_markup': keyboard}


def refresh(ref, chat_id, lang, gap=0.0):
    """Update the collection's single card; remember a replacement if Telegram lost it.
    `gap`: wait until this long after the card's last edit (Telegram limits edits of one message)."""
    from lib.telegram.general.message_master import message_editor, outer_sender
    found = batches.batch(ref, chat_id)
    if found is None:
        return
    wait = _edited.get(ref, 0) + gap - time.time()
    if gap and 0 < wait <= gap:
        time.sleep(wait)
    _edited[ref] = time.time()
    if len(_edited) > 2000:
        _edited.clear()
    message = screen(ref, chat_id, lang)
    if found['message_id']:
        try:
            message_editor(chat_id, message, found['message_id'])
            return
        except Exception:
            pass
    sent = outer_sender(chat_id, [message])
    if sent and sent[0].get('id'):
        batches.set_message(ref, sent[0]['id'])


def help_screen(chat_id, lang):
    from app.i18n.messages import get_message as tr
    choice = 'summaryLanguageMine' if preference(chat_id) == 'mine' else 'voiceLanguageOriginal'
    language_button = button('voiceLanguage', lang, ':helpLang')
    language_button['text'] += ' · ' + tr(choice, lang)
    return {'type': 'text', 'text': tr('voiceHelp', lang), 'reply_markup': [[language_button], [button('voiceBack', lang, ':menu')]]}


def help_message(data):
    from app.service import analytics_events
    from lib.telegram.general.message_master import outer_sender
    outer_sender(data['chat_id'], [help_screen(data['chat_id'], data['language_code'])])
    analytics_events.track(data['chat_id'], 'voice_help')


def language_screen(chat_id, lang, ref='', from_help=False):
    from app.i18n.messages import get_message as tr
    current = preference(chat_id)
    rows = []
    for choice, key in (('original', 'voiceLanguageOriginal'), ('mine', 'summaryLanguageMine')):
        item = button(key, lang, ref + (':helpLang:' if from_help else ':lang:') + choice)
        if (current or 'original') == choice:
            item['text'] = '✅ ' + item['text']
        rows.append([item])
    if from_help:
        rows.append([button('voiceBack', lang, ':help')])
    elif ref:
        rows.append([button('voiceBack', lang, ref + ':show')])
    else:
        rows.append([{'text': tr('voiceBack', lang), 'callback_data': {'tp': 'setts'}}])
    return {'type': 'text', 'text': tr('voiceLanguageHelp', lang), 'reply_markup': rows}


def _allow(ref, chat_id, lang, output, mode, needed, rows):
    """Quota and money for the whole operation, including every new per-recording model call."""
    import config
    from app.service.ai import quota
    unique = {row['ref']: row for row in rows}
    new_text = any(ai.transcript(r) is None for r in unique)
    calls = (sum(ai.summary(r, lang) is None for r in unique) if mode == 'each'
             else int(ai.summary(ref, lang) is None)) if output == 'summary' else 0
    allowed = quota.check(chat_id, needed)
    if not needed and not new_text and not calls:
        return allowed._replace(allowed=True, limit=max(allowed.limit, allowed.used))
    budget = quota.budget(chat_id)
    cost = needed / 3600 * config.ai_transcribe_usd_hour + calls * config.ai_call_usd
    if allowed.allowed and budget is not None and not budget.fits(cost):
        return allowed._replace(allowed=False, budget=True)
    return allowed


def callback(data):
    from app.controller.general.notify import notify
    from app.i18n.messages import get_message as tr
    from app.service.ai import summary
    from app.service.ai.offer import offer_message
    from lib.telegram.general.message_master import message_editor, outer_sender
    chat, lang = data['chat_id'], data['language_code']
    if not summary.enabled():
        notify(data['callback'], data['message'], tr('summaryUnavailable', lang))
        return
    try:
        parts = str(json.loads(data['callback'].data)['p']).split(':')
        ref, action = parts[:2]
    except (KeyError, TypeError, ValueError):
        return
    if ref and batches.batch(ref, chat) is None:
        notify(data['callback'], data['message'], tr('screenOutdated', lang))
        return
    notify(data['callback'], data['message'], '')
    if action == 'menu' and not ref:
        from app.controller.builders.menuModule import construct_menu_message
        from app.repository.storage import storage
        storage.clear_user_storage(chat)
        storage.add_user_state(chat, 'menu')
        message_editor(chat, construct_menu_message(lang, chat)[0], data['message'].message_id)
        return
    if action == 'help':
        if ref:
            batches.set_message(ref, None)
        message_editor(chat, help_screen(chat, lang), data['message'].message_id)
        return
    if action in ('lang', 'helpLang'):
        if len(parts) == 3 and parts[2] in ('original', 'mine'):
            from config import db_path
            from db.sqliteAdapter import SQLighter
            db = SQLighter(db_path)
            try:
                db.set_user_flag(chat, LANGUAGE_FLAG, parts[2])
            finally:
                db.close()
        message_editor(chat, language_screen(chat, lang, ref, from_help=action == 'helpLang'), data['message'].message_id)
        return
    if not ref:
        return
    if action == 'cancel':
        ai._write(None, "UPDATE voice_batches SET state='cancelled',expires_at=? WHERE ref=? AND chat_id=? AND state='collecting'",
                  (time.time(), ref, chat))
        if batches.batch(ref, chat) is None:
            message_editor(chat, {'type': 'text', 'text': tr('voiceCancelled', lang),
                                  'reply_markup': [[button('voiceBack', lang, ':help')]]}, data['message'].message_id)
        return
    if action in ('s', 't') and len(parts) == 2:
        batches.select(ref, chat, 'summary' if action == 's' else 'transcript')
    elif action == 'back':
        batches.select(ref, chat, None)
    elif action in ('s', 't') and len(parts) == 5 and parts[2] in ('e', 'a'):
        if running(ref):
            refresh(ref, chat, lang)
            return
        output, mode = ('summary' if action == 's' else 'transcript'), ('each' if parts[2] == 'e' else 'all')
        try:
            revision, quoted = int(parts[3]), int(parts[4])
            found, rows, needed = batches.quote(ref, chat)
            chosen_language = language(chat, lang)
            batches.select(ref, chat, output)
            allowed = _allow(ref, chat, chosen_language, output, mode, needed, rows)
            from app.service import analytics_events
            analytics_events.track(chat, 'voice_requested', {
                'output': output, 'mode': mode, 'recordings': len({row['ref'] for row in rows}),
                'seconds': int(needed), 'allowed': bool(allowed.allowed)})
            if not allowed.allowed:
                outer_sender(chat, [offer_message(lang, allowed, transcript=output == 'transcript')])
                return
            _, started = batches.launch(ref, chat, revision, output, mode, chosen_language, allowed.limit, quoted,
                                        tr('voiceBatchTitle', lang))
            if started and output == 'summary' and preference(chat) is None:
                _remember_language(chat, 'original')
        except (ValueError, batches.BatchChanged):
            outer_sender(chat, [{'type': 'text', 'text': tr('voiceChanged', lang)}])
    refresh(ref, chat, lang)


_messages = collections.OrderedDict()
_edited = {}
_downloading = {}
POLL_SECONDS = 2
CARD_GAP = 1.2


def _remember_message(chat, message):
    _messages[(chat, message.id)] = message
    while len(_messages) > 1000:
        _messages.popitem(last=False)


async def receive(event):
    """Register a recording at once, from what Telegram says about it. Nothing is downloaded or
    measured here (see `download_pending`), so a long run of forwards is one quick card update."""
    from functools import partial
    from app.i18n.messages import get_message
    from app.service import analytics_events
    from app.service.ai import summary
    from lib.telegram.general.message_master import outer_sender
    from lib.tools.logger import logger

    chat = event.chat_id
    async def run(fn, *args, **kwargs):
        return await asyncio.get_running_loop().run_in_executor(None, partial(fn, *args, **kwargs))
    lock, waiting = _active.get(chat, (asyncio.Lock(), 0))
    _active[chat] = (lock, waiting + 1)
    acquired = False
    item = None
    try:
        await lock.acquire()
        acquired = True
        sender = await event.get_sender()
        lang = getattr(sender, 'lang_code', None)
        async def say(key):
            await run(outer_sender, chat, [{'type': 'text', 'text': get_message(key, lang), 'reply_to': event.message.id}])
        if not summary.enabled():
            await say('summaryUnavailable')
            await run(analytics_events.track, chat, 'voice_received', {'rejected': 'off'})
            return
        from app.routes.middleware.default_middleware import get_user
        await run(get_user, chat)
        await run(ai._write, None, 'UPDATE users SET lang=? WHERE telegramId=?', (lang, chat))
        size, seconds = event.file.size or 0, math.ceil(event.file.duration or 0)
        if not 0 < size <= MAX_BYTES or not 0 < seconds <= MAX_SECONDS:
            await say('voiceLimit')
            await run(analytics_events.track, chat, 'voice_received', {'rejected': 'limit', 'seconds': seconds})
            return
        ref = 'v_' + hashlib.sha256(('%s:%s' % (chat, event.message.document.id)).encode()).hexdigest()[:20]
        batch_ref, item, new = await run(batches.stage, chat, ref, event.message.id, seconds, size)
        if not new:
            item = None
            return
        await run(ai.prune_voices)
        await run(ai.remember_voice, ref, chat, get_message('voiceTitle', lang), seconds)
        _remember_message(chat, event.message)
        await run(analytics_events.track, chat, 'voice_received', {'seconds': seconds})
        item = None
        # the last of a run of forwards redraws the card; the ones before it only when it is quiet
        if _active[chat][1] <= 1 or time.time() - _edited.get(batch_ref, 0) > CARD_GAP:
            await run(refresh, batch_ref, chat, lang)
    except Exception as error:
        logger.warn('voice intake:', type(error).__name__)
        await run(outer_sender, chat, [{'type': 'text', 'text': get_message(
            'voiceBatchLimit' if isinstance(error, batches.BatchLimit) else 'summaryFailed', locals().get('lang'))}])
    finally:
        if item:
            await run(batches.discard_item, item)
        if acquired:
            lock.release()
        remaining = _active[chat][1] - 1
        if remaining:
            _active[chat] = (lock, remaining)
        else:
            _active.pop(chat, None)


class _Gone(Exception):
    pass


def _reconcile(request, measured):
    """The audio was measured: what Telegram claimed is replaced by it. More than claimed needs
    the plan's hours for the difference; less gives them back. A recording nobody is charged for
    (its text is shared or already paid) stays free."""
    from app.service.ai import quota
    claimed = request['seconds']
    if not claimed or measured == claimed:
        return claimed
    if measured > claimed and not quota.check(request['chat_id'], measured - claimed).allowed:
        raise batches.BatchLimit()
    return measured


async def _fetch(client, row, run):
    from functools import partial
    from app.service.ai import transcript
    global _budget
    ref, chat, size = row['ref'], row['chat_id'], row['bytes']
    path = Path(audio_path(ref))
    if await run(ai.transcript, ref) is not None or path.is_file():
        await run(batches.release, row['request_id'])
        return
    message = _messages.get((chat, row['message_id']))
    if message is None:
        message = await client.get_messages(chat, ids=row['message_id'])
    if message is None or not getattr(message, 'voice', None):
        raise _Gone()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if _budget is None:
        _budget = DiskBudget(str(path.parent))
    reservation = _budget.reserve(size * 3)
    try:
        def progress(done, total):
            if done > MAX_BYTES:
                raise batches.BatchLimit()
            reservation.wrote(done)
        with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'wb') as output:
            await asyncio.wait_for(message.download_media(file=output, progress_callback=progress), 300)
        measured = math.ceil(await run(transcript._duration, str(path)))
        if not 0 < measured <= MAX_SECONDS:
            raise batches.BatchLimit()
        charged = await run(_reconcile, row, measured)
        await run(batches.release, row['request_id'], measured, charged)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        reservation.release()


async def _finish_runs(run):
    from app.i18n.messages import get_message
    from lib.telegram.general.message_master import outer_sender
    for final in await run(batches.settle):
        lang = final['ui_lang']
        await run(refresh, final['batch'], final['chat_id'], lang, CARD_GAP)
        if final['failed']:
            await run(outer_sender, final['chat_id'], [{'type': 'text', 'text': get_message('voiceFetchFailed', lang)}])


async def _download_chat(client, chat):
    from functools import partial
    from lib.tools.logger import logger
    async def run(fn, *args, **kwargs):
        return await asyncio.get_running_loop().run_in_executor(None, partial(fn, *args, **kwargs))
    try:
        while True:
            rows = await run(batches.uploading, chat)
            if not rows:
                break
            row = rows[0]
            try:
                await _fetch(client, row, run)
            except Exception as error:
                logger.warn('voice download:', type(error).__name__)
                await run(batches.fail_child, row['request_id'])
            await run(refresh, row['batch'], chat, row['ui_lang'], CARD_GAP)
        await _finish_runs(run)
    except Exception as error:
        logger.warn('voice download loop:', type(error).__name__)
    finally:
        _downloading.pop(chat, None)


async def download_pending(client):
    """One pass: a task per chat with recordings that wait for their audio (one at a time per chat)."""
    chats = await asyncio.get_running_loop().run_in_executor(None, batches.uploading_chats)
    for chat in chats:
        if chat not in _downloading:
            _downloading[chat] = asyncio.ensure_future(_download_chat(client, chat))
    return [_downloading[chat] for chat in chats if chat in _downloading]


async def pump(client):
    """Started with the bot: restart-safe, the queue is the database."""
    from lib.tools.logger import logger
    while True:
        try:
            await download_pending(client)
        except Exception as error:
            logger.warn('voice pump:', type(error).__name__)
        await asyncio.sleep(POLL_SECONDS)
