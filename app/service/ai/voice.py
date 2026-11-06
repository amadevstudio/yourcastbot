"""Private voice collections: download without AI; explicitly confirm output and grouping."""
import asyncio
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
        live = {row[0] for row in c.execute("SELECT ref FROM ai_requests WHERE status IN ('pending','working')")}
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


def button(key, lang, payload):
    from app.i18n.messages import get_message
    return {'text': get_message(key, lang),
            'callback_data': json.dumps({'tp': 'v', 'p': payload}, separators=(',', ':'))}


def running(ref):
    return ai._one(None, "SELECT a.id FROM ai_requests a JOIN voice_runs r ON r.request_id=a.id "
                        "WHERE r.batch=? AND a.status IN ('pending','working') LIMIT 1", (ref,)) is not None


def screen(ref, chat_id, lang):
    from app.i18n.messages import get_message as tr
    from app.service.ai.offer import length_text
    found, rows, needed = batches.quote(ref, chat_id)
    text = tr('voiceCollected', lang).format(count=len(rows), duration=length_text(sum(r['seconds'] for r in rows), lang))
    if running(ref):
        return {'type': 'text', 'text': text + '\n\n' + tr('voiceProcessing', lang)}
    if any(r['status'] != 'ready' for r in rows):
        text += '\n\n' + tr('voiceReceiving', lang)
        keyboard = [[button('voiceCancel', lang, ref + ':cancel')]]
    elif not rows:
        text += '\n\n' + tr('voiceSend', lang)
        keyboard = []
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
        text += '\n\n' + tr('voiceLanguage', lang) + ': ' + tr(
            'summaryLanguageMine' if preference(chat_id) == 'mine' else 'voiceLanguageOriginal', lang)
        keyboard.append([button('voiceLanguage', lang, ref + ':lang')])
        if found['state'] == 'collecting' and rows and all(r['status'] == 'ready' for r in rows):
            keyboard.append([button('voiceCancel', lang, ref + ':cancel')])
    return {'type': 'text', 'text': text, 'reply_markup': keyboard}


def refresh(ref, chat_id, lang):
    """Update the collection's single card; remember a replacement if Telegram lost it."""
    from lib.telegram.general.message_master import message_editor, outer_sender
    found = batches.batch(ref, chat_id)
    if found is None:
        return
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


def help_message(data):
    from app.i18n.messages import get_message
    from lib.telegram.general.message_master import outer_sender
    outer_sender(data['chat_id'], [{'type': 'text', 'text': get_message('voiceHelp', data['language_code'])}])


def language_screen(chat_id, lang, ref=''):
    from app.i18n.messages import get_message as tr
    current = preference(chat_id)
    rows = []
    for choice, key in (('original', 'voiceLanguageOriginal'), ('mine', 'summaryLanguageMine')):
        item = button(key, lang, ref + ':lang:' + choice)
        if (current or 'original') == choice:
            item['text'] = '✅ ' + item['text']
        rows.append([item])
    if ref:
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
    if action == 'lang':
        if len(parts) == 3 and parts[2] in ('original', 'mine'):
            from config import db_path
            from db.sqliteAdapter import SQLighter
            db = SQLighter(db_path)
            try:
                db.set_user_flag(chat, LANGUAGE_FLAG, parts[2])
            finally:
                db.close()
        message_editor(chat, language_screen(chat, lang, ref), data['message'].message_id)
        return
    if not ref:
        return
    if action == 'cancel':
        ai._write(None, "UPDATE voice_batches SET state='cancelled',expires_at=? WHERE ref=? AND chat_id=? AND state='collecting'",
                  (time.time(), ref, chat))
        if batches.batch(ref, chat) is None:
            message_editor(chat, {'type': 'text', 'text': tr('voiceCancelled', lang), 'reply_markup': []}, data['message'].message_id)
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
            allowed = _allow(ref, chat, chosen_language, output, mode, needed, rows)
            if not allowed.allowed:
                outer_sender(chat, [offer_message(lang, allowed, transcript=output == 'transcript')])
                return
            batches.launch(ref, chat, revision, output, mode, chosen_language, allowed.limit, quoted,
                           tr('voiceBatchTitle', lang))
        except (ValueError, batches.BatchChanged):
            outer_sender(chat, [{'type': 'text', 'text': tr('voiceChanged', lang)}])
    refresh(ref, chat, lang)


async def receive(event):
    """Serialize arrival before network awaits; persist membership before downloading media."""
    from functools import partial
    from app.controller.builders import summaryModule as ui
    from app.i18n.messages import get_message
    from app.service.ai import summary, transcript
    from lib.telegram.general.message_master import outer_sender
    from lib.tools.logger import logger

    chat = event.chat_id
    async def run(fn, *args, **kwargs):
        return await asyncio.get_running_loop().run_in_executor(None, partial(fn, *args, **kwargs))
    lock, waiting = _active.get(chat, (asyncio.Lock(), 0))
    _active[chat] = (lock, waiting + 1)
    acquired = False
    item = None
    batch_ref = None
    reservation = None
    created_file = False
    ref = None
    try:
        await lock.acquire()
        acquired = True
        sender = await event.get_sender()
        lang = getattr(sender, 'lang_code', None)
        async def say(key):
            await run(outer_sender, chat, [{'type': 'text', 'text': get_message(key, lang), 'reply_to': event.message.id}])
        if not summary.enabled():
            await say('summaryUnavailable')
            return
        from app.routes.middleware.default_middleware import get_user
        await run(get_user, chat)
        await run(ai._write, None, 'UPDATE users SET lang=? WHERE telegramId=?', (lang, chat))
        size, seconds = event.file.size or 0, math.ceil(event.file.duration or 0)
        if not 0 < size <= MAX_BYTES or not 0 < seconds <= MAX_SECONDS:
            await say('voiceLimit')
            return
        ref = 'v_' + hashlib.sha256(('%s:%s' % (chat, event.message.document.id)).encode()).hexdigest()[:20]
        batch_ref, item, new = await run(batches.stage, chat, ref, event.message.id, seconds, size)
        if not new:
            item = None
            return
        await run(ai.prune_voices)
        await run(ai.remember_voice, ref, chat, get_message('voiceTitle', lang), seconds)
        await run(refresh, batch_ref, chat, lang)
        found = await run(ai.transcript, ref)
        path = Path(audio_path(ref))
        if found is None and not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            global _budget
            if _budget is None:
                _budget = DiskBudget(str(path.parent))
            reservation = _budget.reserve(size * 3)
            def progress(done, total):
                if done > MAX_BYTES:
                    raise batches.BatchLimit()
                reservation.wrote(done)
            created_file = True
            with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'wb') as output:
                await asyncio.wait_for(event.message.download_media(file=output, progress_callback=progress), 300)
        measured = math.ceil(found['seconds']) if found and found['seconds'] else (
            math.ceil(await run(transcript._duration, str(path))) if path.is_file() else seconds)
        if not 0 < measured <= MAX_SECONDS:
            raise batches.BatchLimit()
        await run(ai._write, None, 'UPDATE ai_episodes SET seconds=? WHERE ref=? AND owner_chat=?', (measured, ref, chat))
        await run(batches.ready, item, measured)
        item = None
        await run(refresh, batch_ref, chat, lang)
    except Exception as error:
        logger.warn('voice intake:', type(error).__name__)
        await run(outer_sender, chat, [{'type': 'text', 'text': get_message(
            'voiceBatchLimit' if isinstance(error, batches.BatchLimit) else 'summaryFailed', locals().get('lang'))}])
    finally:
        if item:
            await run(batches.discard_item, item)
            if created_file:
                remove_audio(ref)
            await run(refresh, batch_ref, chat, locals().get('lang'))
        if reservation:
            reservation.release()
        if acquired:
            lock.release()
        remaining = _active[chat][1] - 1
        if remaining:
            _active[chat] = (lock, remaining)
        else:
            _active.pop(chat, None)
