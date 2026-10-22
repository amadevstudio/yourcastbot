# -*- coding: utf-8 -*-
"""Drain ai_requests in the jobs process: transcript, summary, message.

One request at a time: a summary waits for a download, ffmpeg and two APIs,
and the server has one CPU. The transcript and the summary are cached
(db/ai.py), so a second request for the same episode costs nothing. What a
new summary cost is written to the usage ledger for the chat that asked,
and the request is charged the audio Whisper measured (the feed's length was
an estimate) or nothing when someone else's summary served it.

A tap's request carries its status line (ai_requests.status_message): it is
edited as the work goes (downloading, transcribing part n of m, writing) and
at the end into the summary itself, or into "could not". Editing it keeps it
a reply to the audio, so the times still play the episode. A status line that
cannot be edited (deleted) leaves the summary to a new message, as before.
"""
import time

import requests

from app.controller.builders.summaryModule import summary_message
from app.i18n.messages import get_message
from app.service import analytics_events
from app.service.ai import summary, transcript
from app.service.podcast.rss import get_rss_root
from db import ai, usage
from lib.requests import requesterModule
from lib.telegram.general.message_master import message_editor, outer_sender
from lib.tools.logger import logger

IDLE_SLEEP_SECONDS = 5

requester = requesterModule.Requester(attempts=0, total_attempts=0)


def episode_transcript(episode, session, progress=None) -> transcript.Transcript:
    """Cached (free now), the feed's, or Whisper's; a new one is cached.
    `progress(stage, done, total)` follows Whisper's work."""
    cached = ai.transcript(episode['ref'])
    if cached is not None:
        return transcript.Transcript(cached['text'], cached['source'], 0.0, cached['seconds'])
    found = None
    if episode['feed_url']:
        try:
            found = transcript.from_feed(requester, get_rss_root(episode['feed_url']), episode['link'])
        except Exception as e:
            logger.warn('ai_watcher/feed transcript:', e)
    found = found or transcript.from_audio(requester, session, episode['link'], progress=progress)
    ai.save_transcript(episode['ref'], found.text, found.source, found.cost_usd, found.seconds)
    return found


STATUS = {'download': 'summaryStatusDownloading', 'transcribe': 'summaryStatusTranscribing',
          'write': 'summaryStatusWriting'}


def status_updater(request, edit=message_editor):
    """progress(stage, done, total): the request's status line says what is being done.
    Bookkeeping: an edit that fails never fails the summary."""
    message_id = request.get('status_message')

    def progress(stage, done=0, total=0):
        if not message_id or stage not in STATUS:
            return
        try:
            edit(request['chat_id'], {'type': 'text', 'text': get_message(STATUS[stage], request.get('ui_lang')).format(
                done=done, total=total)}, message_id)
        except Exception as e:
            logger.warn('ai_watcher/status:', type(e).__name__, e)
    return progress


def deliver(request, message, send=outer_sender, edit=message_editor):
    """The result: the status line edited into it, else a new message."""
    if request.get('status_message'):
        try:
            edit(request['chat_id'], message, request['status_message'])
            return
        except Exception as e:  # deleted by the user, too old: a message of its own
            logger.warn('ai_watcher/status result:', type(e).__name__, e)
    send(request['chat_id'], [message])


def process(request, session, send=outer_sender, edit=message_editor) -> int:
    """Send the summary; the seconds of quota the request is charged in the end."""
    progress = status_updater(request, edit)
    episode = ai.episode(request['ref'])
    if episode is None:
        raise summary.SummaryUnavailable('episode is not known any more')
    cached = ai.summary(request['ref'], request['lang'])
    if cached is not None:
        text, cost, charged = cached['text'], 0.0, 0
    else:
        found = episode_transcript(episode, session, progress)
        charged = round(found.seconds) or request['seconds']
        progress('write')
        try:
            text, summary_cost = summary.summarize(
                found.text, episode['title'], episode['show'], request['lang'], session=session)
        except Exception:
            # the transcript is cached and billed: a retry reads it for free, so book it now
            if found.cost_usd:
                usage.record_ai(request['chat_id'], request['ref'], found.cost_usd)
            raise
        cost = found.cost_usd + summary_cost
        ai.save_summary(request['ref'], request['lang'], text, cost)
    usage.record_ai(request['chat_id'], request['ref'], cost)
    deliver(request, summary_message(episode, text, request['ref'], request.get('reply_to'), request.get('ui_lang')),
            send, edit)
    analytics_events.track(request['chat_id'], 'summary_ready', {'cached': cached is not None, 'seconds': charged})
    return charged


def ai_watcher():
    logger.log('AI watcher started')
    session = requests.Session()
    while True:
        try:
            request = ai.claim()
            if request is None:
                time.sleep(IDLE_SLEEP_SECONDS)
                continue
            try:
                charged = process(request, session)
                ai.finish(request['id'], 'done', seconds=charged)
            except Exception as e:
                logger.warn('ai_watcher/request', request['id'], e)
                # a summary nobody tapped for (a new episode) fails quietly
                if ai.retry_or_fail(request) and not request.get('auto'):
                    try:
                        deliver(request, {'type': 'text', 'text': get_message('summaryFailed', request['ui_lang'])})
                    except Exception as notify_error:
                        logger.warn('ai_watcher/notify', notify_error)
        except Exception as e:
            logger.err('ai_watcher/loop:', e)
            time.sleep(IDLE_SLEEP_SECONDS)
