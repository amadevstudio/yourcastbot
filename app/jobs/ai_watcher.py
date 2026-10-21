# -*- coding: utf-8 -*-
"""Drain ai_requests in the jobs process: transcript, summary, message.

One request at a time: a summary waits for a download, ffmpeg and two APIs,
and the server has one CPU. The transcript and the summary are cached
(db/ai.py), so a second request for the same episode costs nothing. What a
new summary cost is written to the usage ledger for the chat that asked.
"""
import time

import requests

from app.controller.builders.summaryModule import summary_message
from app.i18n.messages import get_message
from app.service.ai import summary, transcript
from app.service.podcast.rss import get_rss_root
from config import db_path
from db import ai, usage
from db.connection import connect_sqlite
from lib.requests import requesterModule
from lib.telegram.general.message_master import outer_sender
from lib.tools.logger import logger

IDLE_SLEEP_SECONDS = 5

requester = requesterModule.Requester(attempts=0, total_attempts=0)


def _feed_url(channel_id):
    if channel_id is None:
        return None
    c = connect_sqlite(db_path)
    try:
        row = c.execute('SELECT rss_link FROM channels WHERE id = ?', (int(channel_id),)).fetchone()
        return row[0] if row and row[0] else None
    finally:
        c.close()


def episode_transcript(episode, session) -> tuple[str, float]:
    """(text, what making it cost now): cached, the feed's, or Groq's."""
    cached = ai.transcript(episode['ref'])
    if cached is not None:
        return cached['text'], 0.0
    feed_url = _feed_url(episode['channel_id'])
    text = None
    if feed_url:
        try:
            text = transcript.from_feed(requester, get_rss_root(feed_url), episode['link'])
        except Exception as e:
            logger.warn('ai_watcher/feed transcript:', e)
    if text:
        ai.save_transcript(episode['ref'], text, 'feed', 0.0)
        return text, 0.0
    text, cost = transcript.from_audio(requester, session, episode['link'])
    ai.save_transcript(episode['ref'], text, 'groq', cost)
    return text, cost


def process(request, session, send=outer_sender) -> None:
    episode = ai.episode(request['ref'])
    if episode is None:
        raise summary.SummaryUnavailable('episode is not known any more')
    cached = ai.summary(request['ref'], request['lang'])
    if cached is not None:
        text, cost = cached['text'], 0.0
    else:
        transcript_text, cost = episode_transcript(episode, session)
        text, summary_cost = summary.summarize(
            transcript_text, episode['title'], episode['show'], request['lang'], session=session)
        cost += summary_cost
        ai.save_summary(request['ref'], request['lang'], text, cost)
    usage.record_ai(request['chat_id'], request['ref'], cost)
    send(request['chat_id'], [summary_message(episode, text)])


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
                process(request, session)
                ai.finish(request['id'], 'done')
            except Exception as e:
                logger.warn('ai_watcher/request', request['id'], e)
                if ai.retry_or_fail(request):
                    try:
                        outer_sender(request['chat_id'], [{
                            'type': 'text', 'text': get_message('summaryFailed', request['lang'])}])
                    except Exception as notify_error:
                        logger.warn('ai_watcher/notify', notify_error)
        except Exception as e:
            logger.err('ai_watcher/loop:', e)
            time.sleep(IDLE_SLEEP_SECONDS)
