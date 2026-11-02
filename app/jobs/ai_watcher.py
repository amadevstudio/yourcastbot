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

A transcript request (ai.TRANSCRIPT, the Transcript button) stops after the
transcript: no model call; the file goes as a reply to the audio and the
status line is deleted. It is charged what Whisper measured, nothing when the
transcript was made before or came from the feed. A summary whose transcript
was made before is charged nothing when this chat paid for that audio already
(ai.audio_paid): the hours pay for transcription, the model call is cents.

A chat with the better models (app/service/ai/paid_models.py) gets its new
transcripts made with speakers (Whisper's one is made again for it) and its
summaries by the paid model; the cache then serves those to everyone.
"""
import time

import requests

from app.controller.builders.summaryModule import send_transcript_file, summary_message
from app.i18n.messages import get_message
from app.service import analytics_events
from app.service.ai import paid_models, summary, transcript
from db import ai, usage
from lib.requests import requesterModule
from lib.telegram.general.message_master import message_deleter, message_editor, outer_sender
from lib.tools.logger import logger

IDLE_SLEEP_SECONDS = 5

requester = requesterModule.Requester(attempts=0, total_attempts=0)


def episode_transcript(episode, session, progress=None, speakers=False) -> tuple[transcript.Transcript, bool]:
    """(transcript, made from the audio now): cached (free now), the feed's, or Whisper's; a new one is
    cached. `speakers`: the paid model, which also makes Whisper's cached one again.
    `progress(stage, done, total)` follows the transcription."""
    cached = ai.transcript(episode['ref'])
    if cached is not None and not (speakers and cached['source'] == transcript.WHISPER):
        return transcript.Transcript(cached['text'], cached['source'], 0.0, cached['seconds']), False
    found = None
    try:
        found = transcript.from_episode_feed(requester, episode)
    except Exception as e:
        logger.warn('ai_watcher/feed transcript:', e)
    made = found is None
    found = found or transcript.from_audio(
        requester, session, episode['link'], progress=progress,
        speakers_model=paid_models.transcribe_model(True) if speakers else None)
    ai.save_transcript(episode['ref'], found.text, found.source, found.cost_usd, found.seconds)
    return found, made


STATUS = {'download': 'summaryStatusDownloading', 'transcribe': 'summaryStatusTranscribing',
          'write': 'summaryStatusWriting'}
TRANSCRIPT_STATUS = {'download': 'transcriptStatusDownloading', 'transcribe': 'transcriptStatusTranscribing'}


def status_updater(request, edit=message_editor):
    """progress(stage, done, total): the request's status line says what is being done.
    Bookkeeping: an edit that fails never fails the summary."""
    message_id = request.get('status_message')
    texts = TRANSCRIPT_STATUS if request.get('kind') == ai.TRANSCRIPT else STATUS

    def progress(stage, done=0, total=0):
        if not message_id or stage not in texts:
            return
        try:
            edit(request['chat_id'], {'type': 'text', 'text': get_message(texts[stage], request.get('ui_lang')).format(
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


def process(request, session, send=outer_sender, edit=message_editor, send_file=send_transcript_file,
            delete=message_deleter) -> int:
    """Send the summary (or the transcript); the seconds of quota the request is charged in the end."""
    if request.get('kind') == ai.TRANSCRIPT:
        return process_transcript(request, session, edit, send_file, delete)
    progress = status_updater(request, edit)
    episode = ai.episode(request['ref'])
    if episode is None:
        raise summary.SummaryUnavailable('episode is not known any more')
    cached = ai.summary(request['ref'], request['lang'])
    model = None
    if cached is not None:
        text, cost, charged = cached['text'], 0.0, 0
    else:
        found, made = episode_transcript(episode, session, progress, paid_models.speakers(request['chat_id']))
        if not made and ai.audio_paid(request['chat_id'], request['ref'], exclude=request.get('id'), done_only=True):
            charged = 0  # this chat paid for the audio (its transcript): the model call is cents
        else:
            charged = round(found.seconds) or request['seconds']
        progress('write')
        model = paid_models.summary_model(request['chat_id'])
        try:
            text, summary_cost = summary.summarize(
                found.text, episode['title'], episode['show'], request['lang'], session=session, model=model)
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
    analytics_events.track(request['chat_id'], 'summary_ready',
                           {'cached': cached is not None, 'seconds': charged, 'model': model})
    return charged


def process_transcript(request, session, edit=message_editor, send_file=send_transcript_file,
                       delete=message_deleter) -> int:
    """The transcript alone, as a file replying to the audio; the status line goes. Charged the audio
    transcribed, nothing when the transcript was made before or came from the feed."""
    episode = ai.episode(request['ref'])
    if episode is None:
        raise summary.SummaryUnavailable('episode is not known any more')
    speakers = paid_models.speakers(request['chat_id'])
    found, made = episode_transcript(episode, session, status_updater(request, edit), speakers)
    charged = (round(found.seconds) or request['seconds']) if made else 0
    usage.record_transcript(request['chat_id'], request['ref'], found.cost_usd if made else 0.0)
    send_file(request['chat_id'], episode, found.text, found.source, request.get('ui_lang'), request.get('reply_to'))
    if request.get('status_message'):
        try:
            delete(request['chat_id'], request['status_message'])
        except Exception as e:
            logger.warn('ai_watcher/status delete:', type(e).__name__, e)
    analytics_events.track(request['chat_id'], 'transcript_ready',
                           {'source': found.source, 'made': made, 'seconds': charged,
                            'model': paid_models.transcribe_model(speakers) if made else None})
    return charged


FAILED = {ai.SUMMARY: 'summaryFailed', ai.TRANSCRIPT: 'transcriptFailed'}


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
                        deliver(request, {'type': 'text', 'text': get_message(
                            FAILED.get(request.get('kind'), 'summaryFailed'), request['ui_lang'])})
                    except Exception as notify_error:
                        logger.warn('ai_watcher/notify', notify_error)
        except Exception as e:
            logger.err('ai_watcher/loop:', e)
            time.sleep(IDLE_SLEEP_SECONDS)
