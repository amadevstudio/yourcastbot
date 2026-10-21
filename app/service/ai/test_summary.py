# -*- coding: utf-8 -*-
"""AI summaries: the feed's transcript is found and read, OpenRouter is asked
for the configured model and its billed cost kept, quotas are hours of audio
(done and on their way, the measured length once known, nothing for a
cached summary), the queue leases once and retries once, a summary is made
once per episode and language.

Run from the repo root: python app/service/ai/test_summary.py
(the worker part runs where the bot's requirements are installed).
"""
import json
import os
import sqlite3
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.ai import summary, transcript  # noqa: E402
from db import ai, usage  # noqa: E402

LINK = 'https://cdn.example/show/ep7.mp3'
FEED = """<rss xmlns:podcast="https://podcastindex.org/namespace/1.0"><channel>
<item><title>Other</title><enclosure url="https://cdn.example/show/ep6.mp3"/>
  <podcast:transcript url="https://t.example/6.txt" type="text/plain"/></item>
<item><title>Seven</title><enclosure url="https://cdn.example/show/ep7.mp3"/>
  <podcast:transcript url="https://t.example/7.json" type="application/json"/>
  <podcast:transcript url="https://t.example/7.vtt" type="text/vtt"/></item>
</channel></rss>"""


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def test_transcripts():
    channel = ET.fromstring(FEED).find('channel')
    _assert(transcript.transcript_url(channel, LINK) == 'https://t.example/7.vtt',
            "the item with this enclosure, the most readable transcript type")
    _assert(transcript.transcript_url(channel, 'https://cdn.example/none.mp3') is None, "no item, no transcript")
    vtt = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:04.000\n<v Ann>Hello there.</v>\n\n00:00:05.000 --> 00:00:07.000\nBye."
    _assert(transcript.transcript_text(vtt, 'text/vtt') == 'Hello there. Bye.', "VTT: timings and voices go")
    srt = "1\n00:00:01,000 --> 00:00:04,000\nHello.\n\n2\n00:00:05,000 --> 00:00:07,000\nBye."
    _assert(transcript.transcript_text(srt) == 'Hello. Bye.', "SRT: cue numbers and timings go")
    js = json.dumps({'segments': [{'body': 'Hello.'}, {'body': ' Bye. '}]})
    _assert(transcript.transcript_text(js, 'application/json') == 'Hello. Bye.', "podcast JSON segments")
    _assert(transcript.transcript_text('<p>Hello <b>there</b></p>', 'text/html') == 'Hello there', "HTML")
    _assert(abs(transcript.groq_cost(1) - 10 / 3600 * 0.04) < 1e-12, "Groq bills at least 10 seconds")
    _assert(abs(transcript.groq_cost(2700) - 0.03) < 1e-9, "45 minutes cost $0.03")


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append((url, headers, json))
        return self.response


def test_openrouter():
    summary.openrouter_api_key, summary.ai_summary_model, summary.groq_api_key = 'k', 'vendor/some-model', 'g'
    _assert(summary.enabled(), "on with both keys and a model")
    session = FakeSession(FakeResponse(200, {
        'choices': [{'message': {'content': ' Gist.\n• One '}, 'finish_reason': 'stop'}],
        'usage': {'prompt_tokens': 9000, 'completion_tokens': 300, 'cost': 0.0021}}))
    text, cost = summary.summarize('words ' * 10, 'Seven', 'Show', 'fa', session=session)
    url, headers, body = session.calls[0]
    _assert(url == summary.OPENROUTER_URL and headers['Authorization'] == 'Bearer k', "OpenRouter, our key")
    _assert(body['model'] == 'vendor/some-model', "the model from the config")
    _assert(body['usage'] == {'include': True}, "usage accounting asked for")
    _assert(body['messages'][0]['role'] == 'system' and '"fa"' in body['messages'][1]['content'],
            "the system prompt, and the user's own language")
    _assert((text, cost) == ('Gist.\n• One', 0.0021), "the text and what OpenRouter billed")
    for response, label in ((FakeResponse(402, {'error': 'credits'}), "an HTTP error"),
                            (FakeResponse(200, {'error': {'message': 'down'}}), "an error in the body"),
                            (FakeResponse(200, {'choices': [{'message': {'content': ''}}]}), "an empty answer")):
        try:
            summary.summarize('t', 'T', 'S', 'en', session=FakeSession(response))
            raise AssertionError(label + " must raise")
        except summary.SummaryUnavailable:
            _assert(True, label + " is no summary")
    summary.ai_summary_model = ''
    _assert(not summary.enabled(), "off without a model")
    summary.ai_summary_model = 'vendor/some-model'


def test_queue_and_quota(db):
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER);
        CREATE TABLE tariffs (id INTEGER PRIMARY KEY, level INTEGER);
        CREATE TABLE user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER, tariff_id INTEGER, time_left INTEGER);
        INSERT INTO users VALUES (1, 501), (2, 502);
        INSERT INTO tariffs VALUES (1, 1), (3, 3);
        INSERT INTO user_tariff_cs VALUES (1, 1, 1, 100), (2, 2, 0, 0);
    """)
    c.commit()
    c.close()
    _assert(summary.plan_level(501, db) == 1 and summary.plan_level(502, db) == 0, "plan levels")
    _assert(summary.seconds_needed({'seconds': 2700}) == 2700, "an episode takes its length")
    _assert(summary.seconds_needed({'seconds': 0}) == summary.UNKNOWN_SECONDS, "an hour when the feed has none")
    _assert(summary.top_level() == 3, "Relay is the top plan")

    hour = 3600
    for i in range(3):
        done, _ = ai.enqueue(501, 'h%d' % i, 'en', hour, db)
        ai.finish(done, 'done', database=db)
    failed, _ = ai.enqueue(501, 'bad', 'en', hour, db)
    ai.finish(failed, 'failed', database=db)
    served, _ = ai.enqueue(501, 'served', 'en', hour, db)
    ai.finish(served, 'done', seconds=0, database=db)
    old, _ = ai.enqueue(501, 'old', 'en', hour, db)
    ai.finish(old, 'done', database=db)
    c = sqlite3.connect(db)
    c.execute('UPDATE ai_requests SET created_at=created_at-? WHERE id=?', (40 * 86400, old))
    c.commit()
    c.close()

    now = time.time()
    quota = summary.quota(501, hour, level=1, now=now, database=db)
    _assert((quota.allowed, quota.limit, quota.used, quota.needed) == (True, 5 * hour, 3 * hour, hour),
            "Bronze, 5 hours: 3 used; failed, served by a cached summary and old ones do not count")
    _assert(not summary.quota(501, 3 * hour, level=1, now=now, database=db).allowed,
            "a three-hour episode does not fit the two hours left")
    request_id, new = ai.enqueue(501, 'r9', 'en', hour, db)
    _assert(new and ai.enqueue(501, 'r9', 'en', hour, db) == (request_id, False), "a second tap is the same request")
    _assert(summary.quota(501, hour, level=1, now=now, database=db).used == 4 * hour, "one on its way counts")
    _assert(not summary.quota(501, hour + 1, level=1, now=now, database=db).allowed, "the hour left is the limit")
    nothing = summary.quota(502, 60, level=0, now=now, database=db)
    _assert((nothing.allowed, nothing.limit) == (False, 0), "no plan: no new summaries")

    claimed = ai.claim(db, now=now)
    _assert(claimed['id'] == request_id and claimed['attempts'] == 1, "claimed once")
    _assert(ai.claim(db, now=now) is None, "a leased request is not claimed twice")
    again = ai.claim(db, now=now + ai.LEASE_SECONDS + 1)
    _assert(again['id'] == request_id and again['attempts'] == 2, "a lease that ran out is claimed again")
    _assert(ai.retry_or_fail(again, db) is True, "after the second attempt it fails")
    _assert(ai.seconds_used(501, now - 86400, db) == 3 * hour, "a failed request gives its hour back")

    measured, _ = ai.enqueue(501, 'm', 'en', hour, db)
    ai.finish(measured, 'done', seconds=5400, database=db)
    _assert(ai.seconds_used(501, now - 86400, db) == 3 * hour + 5400, "charged what Groq measured, not the estimate")


def test_worker(db):
    try:
        from app.jobs import ai_watcher
        from app.controller.builders import summaryModule
    except Exception as e:  # CI has no bot requirements
        print("skip worker (%s)" % e.__class__.__name__)
        return
    ai.remember_episode('ep7', LINK, None, 'Seven &amp; more', 'Show', 2700, database=db)
    ai.save_transcript('ep7', 'words', 'feed', 0.0, database=db)
    ai.remember_episode('ep8', 'https://cdn.example/show/ep8.mp3', None, 'Eight', 'Show', database=db)
    ai.save_transcript('ep8', 'words', 'groq', 0.03, 2712.4, database=db)
    _assert(ai.episode('ep8', db)['seconds'] == 0, "a feed without a length stores 0")
    ai.remember_episode('ep7', LINK, None, 'Seven &amp; more', 'Show', 0, database=db)
    _assert(ai.episode('ep7', db)['seconds'] == 2700, "a later delivery without a length keeps the known one")
    sent, asked = [], []

    def summarize(text, title, show, language, session=None):
        asked.append(language)
        return 'Gist.', 0.002

    saved = (ai_watcher.summary.summarize, ai.db_path, usage.db_path)
    ai_watcher.summary.summarize = summarize
    ai.db_path = usage.db_path = db  # the worker's default database
    try:
        send = lambda chat_id, structures: sent.append((chat_id, structures[0]['text']))  # noqa: E731
        charged = [
            ai_watcher.process({'chat_id': 501, 'ref': 'ep7', 'lang': 'ru', 'seconds': 2700}, None, send=send),
            ai_watcher.process({'chat_id': 502, 'ref': 'ep7', 'lang': 'ru', 'seconds': 2700}, None, send=send),
            ai_watcher.process({'chat_id': 501, 'ref': 'ep8', 'lang': 'ru', 'seconds': 3600}, None, send=send)]
    finally:
        ai_watcher.summary.summarize, ai.db_path, usage.db_path = saved
    _assert(asked == ['ru', 'ru'], "one summary per episode and language, then the cache")
    _assert([chat for chat, _ in sent] == [501, 502, 501], "every asker gets it")
    _assert('Seven &amp; more' in sent[0][1] and 'Gist.' in sent[0][1], "the title is escaped once")
    _assert(charged == [2700, 0, 2712], "charged: the feed's length, nothing for the cache, Groq's measure")
    rows = usage.per_user(0, database=db)
    _assert(abs(rows[501]['ai_usd'] - 0.004) < 1e-9 and rows[502]['ai_usd'] == 0.0,
            "the new summary is charged to who asked, the cached one costs nothing")

    _assert(summaryModule.length_text(5400, 'en') == '1 h 30 min', "hours and minutes")
    _assert(summaryModule.length_text(2701, 'ru') == '46 мин', "minutes round up")
    _assert(summaryModule.length_text(5 * 3600, 'de') == '5 Std.', "whole hours")
    top = summaryModule.offer_message('en', summary.Quota(False, 30 * 3600, 29 * 3600, 7200, 3))
    _assert('30 h of audio' in top['text'] and '1 h left' in top['text'] and 'runs 2 h' in top['text']
            and 'reply_markup' not in top, "the top plan hears what is left, no plans to sell")


def main():
    test_transcripts()
    test_openrouter()
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, 'test.sqlite')
        test_queue_and_quota(db)
        test_worker(os.path.join(tmp, 'worker.sqlite'))
    print("all AI summary checks passed")


if __name__ == "__main__":
    main()
