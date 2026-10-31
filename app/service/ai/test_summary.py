# -*- coding: utf-8 -*-
"""AI summaries: the feed's transcript is found and read, OpenRouter is asked
for the summary and for Whisper with one key and its billed cost kept, quotas are hours of audio
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

from app.service.ai import openrouter, quota, summary, transcript  # noqa: E402
from db import ai, usage  # noqa: E402
from db.tariff_rows import running_plan_level  # noqa: E402

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
    _assert(transcript.transcript_text(vtt, 'text/vtt') == '[0:01] Hello there. Bye.',
            "VTT: voices and cue timings go, a time mark stays (the next cue is within 30 s)")
    srt = "1\n00:00:01,000 --> 00:00:04,000\nHello.\n\n2\n00:00:45,000 --> 00:00:47,000\nBye."
    _assert(transcript.transcript_text(srt) == '[0:01] Hello. [0:45] Bye.', "SRT: cue numbers go, marks 30 s apart")
    js = json.dumps({'segments': [{'body': 'Hello.'}, {'body': ' Bye. '}]})
    _assert(transcript.transcript_text(js, 'application/json') == 'Hello. Bye.', "podcast JSON segments")
    js = json.dumps({'segments': [{'startTime': 3725.5, 'body': 'Late.'}, {'startTime': 3730, 'body': 'Still.'}]})
    _assert(transcript.transcript_text(js, 'application/json') == '[1:02:05] Late. Still.',
            "JSON startTime: hours when past one")
    _assert(transcript.transcript_text('<p>Hello <b>there</b></p>', 'text/html') == 'Hello there',
            "HTML: no times, no marks")
    _assert(transcript.clock(65) == '1:05' and transcript.clock(3600) == '1:00:00', "times read as players show them")


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

    def post(self, url, headers=None, json=None, timeout=None, files=None, data=None):
        self.calls.append((url, headers, json if files is None else (files, data)))
        return self.response


def test_openrouter():
    openrouter.openrouter_api_key, summary.ai_summary_model, summary.ai_transcribe_model = \
        'k', 'vendor/some-model', 'vendor/some-stt'
    _assert(summary.enabled(), "on with the key and both models")
    _assert(summary.button_data('ab12') == {'tp': summary.ACTION, 'r': 'ab12'}, "the button names the episode")
    session = FakeSession(FakeResponse(200, {
        'choices': [{'message': {'content': ' Gist.\n• One '}, 'finish_reason': 'stop'}],
        'usage': {'prompt_tokens': 9000, 'completion_tokens': 300, 'cost': 0.0021}}))
    text, cost = summary.summarize('words ' * 10, 'Seven', 'Show', 'fa', session=session)
    url, headers, body = session.calls[0]
    _assert(url == openrouter.BASE_URL + 'chat/completions' and headers['Authorization'] == 'Bearer k',
            "OpenRouter's chat completions, our key")
    _assert(body['model'] == 'vendor/some-model', "the model from the config")
    _assert(body['usage'] == {'include': True}, "usage accounting asked for")
    _assert(body['reasoning'] == {'enabled': False}, "thinking off: it ate every token of the answer")
    _assert(body['messages'][0]['role'] == 'system' and '"fa"' in body['messages'][1]['content'],
            "the system prompt, and the user's own language")
    summary.summarize('words', 'Seven', 'Show', summary.ORIGINAL, session=session)
    _assert('language the episode is spoken in' in session.calls[1][2]['messages'][1]['content'],
            "or the episode's own")
    _assert(summary.summary_language(None, 'fa') == summary.ORIGINAL
            and summary.summary_language(summary.ORIGINAL, 'fa') == summary.ORIGINAL,
            "the episode's language by default")
    _assert(summary.summary_language(summary.MINE, 'pt-BR') == 'pt-br'
            and summary.summary_language(summary.MINE, None) == 'en', "the Telegram language when picked")
    _assert((text, cost) == ('Gist.\n• One', 0.0021), "the text and what OpenRouter billed")
    _assert('[12:40]' in summary.SYSTEM and 'never invent a time' in summary.SYSTEM,
            "the summary starts its points with the transcript's times, never made-up ones")
    long_text = 'x' * (summary.MAX_TRANSCRIPT_CHARS + 10)
    _assert(len(summary.bounded(long_text)) < summary.MAX_TRANSCRIPT_CHARS + 50
            and summary.bounded('short') == 'short', "a transcript past ~100k tokens is cut, a usual one is whole")
    _assert(summary.ask_button_data('ab12', 77) == {'tp': summary.ASK_ACTION, 'r': 'ab12', 'm': 77}
            and len(json.dumps(summary.ask_button_data('0123456789abcdef', 2 ** 31))) <= 64,
            "the Ask button names the episode and the audio, within 64 bytes")
    session = FakeSession(FakeResponse(200, {
        'choices': [{'message': {'content': ' At 12:40 they say so. '}}], 'usage': {'cost': 0.0007}}))
    answered = summary.answer('[12:40] words', 'Seven', 'Show', 'What do they say?', session=session)
    _assert(answered == ('At 12:40 they say so.', 0.0007), "an answer and what it cost")
    _assert(session.calls[0][2]['reasoning'] == {'enabled': False}, "thinking off for questions too")
    cut = FakeSession(FakeResponse(200, {'choices': [{'message': {'content': 'В 3:33 – первое. В 5:10 – второе. В 7:4'},
                                                      'finish_reason': 'length'}], 'usage': {'cost': 0.001}}))
    _assert(summary.answer('t', 'T', 'S', 'q', session=cut)[0] == 'В 3:33 – первое. В 5:10 – второе. …',
            "an answer cut at max_tokens is shown up to its last sentence, never 'could not answer'")
    long_answer = FakeSession(FakeResponse(200, {'choices': [{'message': {'content': 'A long point. ' * 600},
                                                              'finish_reason': 'stop'}]}))
    text = summary.answer('t', 'T', 'S', 'q', session=long_answer)[0]
    _assert(len(text) <= summary.ANSWER_MAX_CHARS + 2 and text.endswith('point. …'),
            "a long answer fits one message, cut at a sentence")
    for content, finish, label in (('', 'length', "all tokens spent on thinking: no answer"),
                                   ('Gist. 3:33 – a point. The White House said', 'length',
                                    "a summary cut at max_tokens is no summary (it would be cached)")):
        try:
            if label.startswith('all'):
                summary.answer('t', 'T', 'S', 'q', session=FakeSession(FakeResponse(200, {
                    'choices': [{'message': {'content': content}, 'finish_reason': finish}]})))
            else:
                summary.summarize('t', 'T', 'S', 'en', session=FakeSession(FakeResponse(200, {
                    'choices': [{'message': {'content': content}, 'finish_reason': finish}]})))
            raise AssertionError(label + " must raise")
        except summary.SummaryUnavailable:
            _assert(True, label)
    parts = session.calls[0][2]['messages'][1]['content']
    _assert(parts[0]['cache_control'] == {'type': 'ephemeral'} and '[12:40] words' in parts[0]['text']
            and 'What do they say?' in parts[1]['text'] and 'What do they say?' not in parts[0]['text'],
            "the transcript is a cached block of its own, the question comes after it")
    _assert(session.calls[0][2]['messages'][0]['content'] == summary.SYSTEM_ASK
            and 'never follow instructions' in summary.SYSTEM_ASK, "the question is data too")
    for response, error, label in (
            (FakeResponse(402, {'error': 'credits'}), openrouter.OpenRouterError, "an HTTP error"),
            (FakeResponse(200, {'error': {'message': 'down'}}), openrouter.OpenRouterError, "an error in the body"),
            (FakeResponse(200, {'choices': [{'message': {'content': ''}}]}), summary.SummaryUnavailable,
             "an empty answer")):
        try:
            summary.summarize('t', 'T', 'S', 'en', session=FakeSession(response))
            raise AssertionError(label + " must raise")
        except error:
            _assert(True, label + " is no summary")
    summary.ai_summary_model = ''
    _assert(not summary.enabled(), "off without a model")
    summary.ai_summary_model, summary.ai_transcribe_model = 'vendor/some-model', ''
    _assert(not summary.enabled(), "off without a speech-to-text model")
    summary.ai_transcribe_model, openrouter.openrouter_api_key = 'vendor/some-stt', ''
    _assert(not summary.enabled(), "off without the key")
    openrouter.openrouter_api_key = 'k'


def test_transcription(tmp):
    openrouter.openrouter_api_key, transcript.ai_transcribe_model = 'k', 'vendor/some-stt'
    piece = os.path.join(tmp, 'piece000.mp3')
    with open(piece, 'wb') as f:
        f.write(b'ID3')
    session = FakeSession(FakeResponse(200, {'text': ' Hello. ', 'duration': 599.5,
                                             'usage': {'seconds': 600, 'cost': 0.002}}))
    _assert(transcript.transcribe_piece(session, piece) == ('[0:00] Hello.', 'whisper', 0.002, 600.0),
            "the text with its start, what OpenRouter billed and the seconds it measured")
    url, headers, (files, data) = session.calls[0]
    _assert(data['response_format'] == 'verbose_json' and data['timestamp_granularities[]'] == 'segment',
            "Whisper's segments with their times")
    timed = FakeSession(FakeResponse(200, {'text': 'A B C', 'usage': {'seconds': 600, 'cost': 0.002}, 'segments': [
        {'start': 0.5, 'text': ' A.'}, {'start': 20, 'text': ' B.'}, {'start': 41, 'text': ' C.'}]}))
    _assert(transcript.transcribe_piece(timed, piece, offset=600).text == '[10:00] A. B. [10:41] C.',
            "a later piece: its segments' times from the episode's start, a mark at most every 30 s")
    _assert(url == openrouter.BASE_URL + 'audio/transcriptions' and headers['Authorization'] == 'Bearer k',
            "OpenRouter's transcription endpoint, the same key")
    _assert(data['model'] == 'vendor/some-stt' and files['file'][0] == 'piece000.mp3',
            "the configured model, the piece as a file")
    for response, label in ((FakeResponse(400, {'error': 'format'}), "an HTTP error"),
                            (FakeResponse(200, {'error': {'message': 'down'}}), "an error in the body")):
        try:
            transcript.transcribe_piece(FakeSession(response), piece)
            raise AssertionError(label + " must raise")
        except openrouter.OpenRouterError:
            _assert(True, label + " is no transcript")
    _assert(transcript.PIECE_SECONDS * 24000 / 8 < 25 * 1024 * 1024 and transcript.PIECE_SECONDS <= 600,
            "a piece is under the 25 MB upload cap and short enough for a 60 s provider timeout")


def test_queue_and_quota(db):
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER, lang TEXT);
        CREATE TABLE tariffs (id INTEGER PRIMARY KEY, level INTEGER);
        CREATE TABLE user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER, tariff_id INTEGER, time_left INTEGER);
        CREATE TABLE payment_history (user_id INTEGER, status TEXT);
        CREATE TABLE payment_service_user_data (user_id INTEGER, service_type TEXT, last_replenishment TEXT);
        INSERT INTO users VALUES (1, 501, 'ru'), (2, 502, 'en'), (3, 503, 'en'), (4, 504, 'en'), (5, 505, 'en');
        INSERT INTO tariffs VALUES (1, 1), (3, 3);
        INSERT INTO user_tariff_cs VALUES (1, 1, 1, 100), (2, 2, 0, 0), (3, 3, 3, 100), (4, 4, 3, 100), (5, 5, 3, 100);
        INSERT INTO payment_history VALUES (1, 'paid'), (3, 'paid'), (4, 'canceled');
        INSERT INTO payment_service_user_data VALUES (5, 'patreon', '2026-10-13');
    """)
    c.commit()
    c.close()
    _assert(running_plan_level(501, db) == 1 and running_plan_level(502, db) == 0, "plan levels")
    _assert(quota.seconds_needed({'seconds': 2700}) == 2700, "an episode takes its length")
    _assert(quota.seconds_needed({'seconds': 0}) == quota.UNKNOWN_SECONDS, "an hour when the feed has none")
    paid_relay, trial_relay = quota.check(503, 60, database=db), quota.check(504, 60, database=db)
    _assert((paid_relay.limit, paid_relay.trial, paid_relay.top_plan) == (30 * 3600, False, True),
            "a paid Relay has its 30 hours")
    _assert((trial_relay.limit, trial_relay.trial, trial_relay.top_plan) == (5 * 3600, True, False),
            "the welcome Relay nobody paid for has the trial's 5 hours (a canceled payment is no payment)")
    _assert(quota.check(505, 60, database=db).limit == 30 * 3600,
            "a patron credited before Patreon wrote payment rows has the plan's hours, not the trial's")
    _assert(quota.check(502, 60, database=db).limit == 0, "no plan, no new summaries")

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
    bronze = quota.check(501, hour, level=1, now=now, database=db)
    _assert((bronze.allowed, bronze.limit, bronze.used, bronze.needed) == (True, 5 * hour, 3 * hour, hour),
            "Bronze, 5 hours: 3 used; failed, served by a cached summary and old ones do not count")
    _assert(bronze.left == 2 * hour and not bronze.top_plan, "two hours left, a bigger plan exists")
    _assert(not quota.check(501, 3 * hour, level=1, now=now, database=db).allowed,
            "a three-hour episode does not fit the two hours left")
    request_id, new = ai.enqueue(501, 'r9', 'en', hour, db)
    _assert(new and ai.enqueue(501, 'r9', 'en', hour, db) == (request_id, False), "a second tap is the same request")
    _assert(quota.check(501, hour, level=1, now=now, database=db).used == 4 * hour, "one on its way counts")
    _assert(not quota.check(501, hour + 1, level=1, now=now, database=db).allowed, "the hour left is the limit")
    nothing = quota.check(502, 60, level=0, now=now, database=db)
    _assert((nothing.allowed, nothing.limit) == (False, 0), "no plan: no new summaries")

    claimed = ai.claim(db, now=now)
    _assert(claimed['id'] == request_id and claimed['attempts'] == 1, "claimed once")
    _assert(claimed['ui_lang'] == 'ru', "with the user's interface language for a notice")
    _assert(ai.claim(db, now=now) is None, "a leased request is not claimed twice")
    again = ai.claim(db, now=now + ai.LEASE_SECONDS + 1)
    _assert(again['id'] == request_id and again['attempts'] == 2, "a lease that ran out is claimed again")
    _assert(ai.retry_or_fail(again, db) is True, "after the second attempt it fails")
    _assert(ai.seconds_used(501, now - 86400, db) == 3 * hour, "a failed request gives its hour back")

    measured, _ = ai.enqueue(501, 'm', 'en', hour, db)
    ai.finish(measured, 'done', seconds=5400, database=db)
    _assert(ai.seconds_used(501, now - 86400, db) == 3 * hour + 5400, "charged what Whisper measured, not the estimate")

    ai.enqueue(503, 'reply', 'en', hour, db, reply_to=4321)
    c = sqlite3.connect(db)
    _assert(c.execute("SELECT reply_to FROM ai_requests WHERE ref='reply'").fetchone()[0] == 4321,
            "the summary will answer the audio message")
    c.close()

    old_db = db + '.old'
    c = sqlite3.connect(old_db)
    c.execute('CREATE TABLE ai_requests (id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL, ref TEXT NOT NULL, '
              'lang TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, '
              'created_at REAL NOT NULL, leased_until REAL, seconds INTEGER NOT NULL DEFAULT 0)')
    c.commit()
    c.close()
    ai.enqueue(1, 'x', 'en', 60, old_db, reply_to=5)
    _assert(sqlite3.connect(old_db).execute('SELECT reply_to FROM ai_requests').fetchone()[0] == 5,
            "a database from before gets the reply_to column")

    _assert(quota.questions(501, database=db) == (True, quota.QUESTIONS_PER_DAY, quota.QUESTIONS_PER_DAY, False),
            "a paid plan asks its questions a day")
    _assert(quota.questions(502, database=db)[:3] == (False, 0, 0), "no plan: no questions")
    for _ in range(quota.TRIAL_QUESTIONS_PER_DAY):
        usage.record_ask(504, 'ep', 0.001, db)
    usage.record_ask(504, 'ep', 0.001, db, at=now - 2 * 86400)
    _assert(quota.questions(504, database=db) == (False, quota.TRIAL_QUESTIONS_PER_DAY, 0, True),
            "a trial has fewer, counted over the last 24 hours")
    _assert(abs(usage.per_user(0, database=db)[504]['ai_usd'] - 0.006) < 1e-9, "questions are in the AI spend")


def test_auto(db):
    from app.service.ai import auto
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER, lang TEXT, flags TEXT);
        CREATE TABLE tariffs (id INTEGER PRIMARY KEY, level INTEGER);
        CREATE TABLE user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER, tariff_id INTEGER, time_left INTEGER);
        CREATE TABLE payment_history (user_id INTEGER, status TEXT);
        INSERT INTO users VALUES (1, 601, 'en', '{"auto_summary": 1}'), (2, 602, 'en', '{"auto_summary": 1}'),
            (3, 603, 'en', NULL), (4, 604, 'ru', '{"auto_summary": 1, "summary_language": "mine"}'),
            (5, 605, 'en', '{"auto_summary": 0}');
        INSERT INTO tariffs VALUES (3, 3);
        INSERT INTO user_tariff_cs VALUES (1, 1, 3, 100), (2, 2, 0, 0), (3, 3, 3, 100), (4, 4, 3, 100), (5, 5, 3, 100);
        INSERT INTO payment_history VALUES (1, 'paid'), (4, 'paid');
    """)
    c.commit()
    c.close()
    _assert(set(auto.wanted([601, 602, 603, 604, 605, '@channel'], db)) == {601, 602, 604},
            "only the chats that turned it on (a channel never)")
    saved = summary.enabled
    summary.enabled = lambda: True
    try:
        queued = auto.queue([601, 602, 603, 604, 605], 'new1', 1800, {604: 'pt-BR'}, {601: 11, 604: 44}, db)
    finally:
        summary.enabled = saved
    rows = {r[0]: r[1:] for r in sqlite3.connect(db).execute(
        "SELECT chat_id, lang, reply_to, auto, seconds FROM ai_requests WHERE ref='new1'")}
    _assert(queued == 2 and set(rows) == {601, 604}, "queued for a running plan that turned it on; no plan, nothing")
    _assert(rows[601] == ('original', 11, 1, 1800) and rows[604] == ('pt-br', 44, 1, 1800),
            "in the chat's summary language, answering the delivered audio, charged its length")
    from app.i18n.messages import get_message
    notices = []
    saved_send = auto._send
    auto._send = lambda chat_id, messages: notices.append((chat_id, messages[0]))
    summary.enabled = lambda: True
    try:
        _assert(auto.queue([601], 'long', 40 * 3600, {601: 'en'}, {601: 12}, db) == 0,
                "an episode past the plan's hours: none")
        _assert(len(notices) == 1 and notices[0][0] == 601 and notices[0][1]['reply_to'] == 12
                and notices[0][1]['text'].startswith(get_message('summaryAutoSkipped', 'en') + '\n\n')
                and '30 h of audio' in notices[0][1]['text'] and 'reply_markup' not in notices[0][1],
                "and says so, a reply to the audio, with what is left (a paid top plan: nothing to sell)")
        auto.queue([601], 'long2', 40 * 3600, {601: 'en'}, {}, db)
        _assert(len(notices) == 1, "once in 30 days")
        c = sqlite3.connect(db)
        c.execute("UPDATE users SET flags = json_set(flags, '$.summary_quota_noticed', ?) WHERE telegramId = 601",
                  (int(time.time()) - 31 * 86400,))
        c.commit()
        c.close()
        auto.queue([601], 'long3', 40 * 3600, {601: 'en'}, {}, db)
        _assert(len(notices) == 2 and 'reply_to' not in notices[1][1], "again after 30 days; no audio, no reply")
        auto.queue([602], 'long4', 40 * 3600, {}, {}, db)
        _assert(len(notices) == 2, "no plan: no notice (the plan-off notice said it)")
        auto._send = lambda chat_id, messages: (_ for _ in ()).throw(RuntimeError('blocked'))
        c = sqlite3.connect(db)
        c.execute("UPDATE users SET flags = json_remove(flags, '$.summary_quota_noticed') WHERE telegramId = 601")
        c.commit()
        c.close()
        _assert(auto.queue([601, 604], 'long5', 40 * 3600, {}, {}, db) == 0, "a failed notice fails nothing")
    finally:
        summary.enabled = saved
        auto._send = saved_send
    tap, _ = ai.enqueue(603, 'tapped', 'en', 60, db)
    claimed = ai.claim(db)
    _assert(claimed['id'] == tap, "a tap goes before the automatic ones queued earlier")
    ai.finish(tap, 'done', database=db)
    request_id, new = ai.enqueue(601, 'new1', 'original', 1800, db, reply_to=99)
    _assert(not new and sqlite3.connect(db).execute('SELECT auto, reply_to FROM ai_requests WHERE id=?',
                                                    (request_id,)).fetchone() == (0, 11),
            "a tap on one queued automatically makes it a tap, keeping its audio")
    _assert(ai.claim(db)['id'] == request_id, "and it goes first")


def test_hint(db):
    from app.service.ai import hint
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER, lang TEXT, flags TEXT);
        CREATE TABLE user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER, tariff_id INTEGER, time_left INTEGER);
        INSERT INTO users VALUES (1, 701, 'en', NULL), (2, 702, 'en', NULL), (3, 703, 'en', NULL),
            (4, 704, 'en', '{"auto_summary": 1}');
        INSERT INTO user_tariff_cs VALUES (1, 1, 3, 100), (2, 2, 0, 0), (3, 3, 3, 100), (4, 4, 3, 100);
    """)
    c.commit()
    c.close()
    ai.enqueue(703, 'ep', 'original', 60, db)
    _assert(hint.pending([701, 702, 703, 704, '@channel', -100500], db) == {701, 704},
            "the note: a plan running (a trial too), never asked for a summary; no plan, a channel: none")
    hint.mark(704, db)
    _assert(hint.pending([701, 704], db) == {701}, "once per user")
    _assert(sqlite3.connect(db).execute("SELECT flags FROM users WHERE id=4").fetchone()[0]
            == '{"auto_summary":1,"summary_hint_sent":1}', "the other flags stay")
    _assert(hint.pending([], db) == set(), "nobody delivered: no query")


def test_worker(db):
    try:
        from app.jobs import ai_watcher
        from app.controller.builders import summaryModule
    except Exception as e:  # CI has no bot requirements
        print("skip worker (%s)" % e.__class__.__name__)
        return
    c = sqlite3.connect(db)
    c.execute('CREATE TABLE channels (id INTEGER PRIMARY KEY, rss_link TEXT)')
    c.execute("INSERT INTO channels VALUES (9, 'https://feed.example/rss')")
    c.commit()
    c.close()
    ai.remember_episode('ep7', LINK, 9, 'Seven &amp; more', 'Show', 2700, database=db)
    _assert(ai.episode('ep7', db)['feed_url'] == 'https://feed.example/rss', "the episode knows its feed")
    ai.save_transcript('ep7', 'words', 'feed', 0.0, database=db)
    ai.remember_episode('ep8', 'https://cdn.example/show/ep8.mp3', None, 'Eight', 'Show', database=db)
    ai.save_transcript('ep8', 'words', 'whisper', 0.01, 2712.4, database=db)
    _assert(ai.episode('ep8', db)['seconds'] == 0, "a feed without a length stores 0")
    ai.remember_episode('ep7', LINK, 9, 'Seven &amp; more', 'Show', 0, database=db)
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
    _assert(charged == [2700, 0, 2712], "charged: the feed's length, nothing for the cache, Whisper's measure")
    rows = usage.per_user(0, database=db)
    _assert(abs(rows[501]['ai_usd'] - 0.004) < 1e-9 and rows[502]['ai_usd'] == 0.0,
            "the new summary is charged to who asked, the cached one costs nothing")

    def down(*args, **kwargs):
        raise openrouter.OpenRouterError('chat/completions 502: down')

    saved = (ai_watcher.summary.summarize, ai_watcher.episode_transcript, ai.db_path, usage.db_path)
    ai_watcher.summary.summarize = down
    ai_watcher.episode_transcript = lambda episode, session, progress=None: transcript.Transcript(
        'words', 'whisper', 0.02, 3600.0)
    ai.db_path = usage.db_path = db
    try:
        ai_watcher.process({'chat_id': 503, 'ref': 'ep8', 'lang': 'en', 'seconds': 3600}, None, send=send)
        raise AssertionError("a failed summary must raise")
    except openrouter.OpenRouterError:
        pass
    finally:
        ai_watcher.summary.summarize, ai_watcher.episode_transcript, ai.db_path, usage.db_path = saved
    _assert(abs(usage.per_user(0, database=db)[503]['ai_usd'] - 0.02) < 1e-9,
            "Whisper is paid even when the summary fails: its cost is in the ledger")

    # a tap's status line: edited as the work goes, then into the summary (a reply to the audio stays one)
    edits, sent_new = [], []

    def edit(chat_id, message, message_id):
        if message_id == 666:
            raise RuntimeError('Bad Request: message to edit not found')
        edits.append((chat_id, message_id, message['text']))

    def whisper(episode, session, progress=None):
        progress('download')
        progress('transcribe', 1, 2)
        progress('transcribe', 2, 2)
        return transcript.Transcript('[0:00] words', 'whisper', 0.0, 600.0)
    saved = (ai_watcher.summary.summarize, ai_watcher.episode_transcript, ai.db_path, usage.db_path)
    ai_watcher.summary.summarize = lambda *a, **k: ('Gist.\n0:00 – a point', 0.001)
    ai_watcher.episode_transcript = whisper
    ai.db_path = usage.db_path = db
    try:
        request = {'chat_id': 504, 'ref': 'ep8', 'lang': 'it', 'seconds': 600, 'reply_to': 41, 'status_message': 42,
                   'ui_lang': 'en'}
        ai_watcher.process(request, None, send=lambda chat_id, messages: sent_new.append(messages[0]), edit=edit)
        _assert([text for _, _, text in edits[:4]] == [
            '📝 Summary: downloading the episode…', '📝 Summary: transcribing, part 1 of 2…',
            '📝 Summary: transcribing, part 2 of 2…', '📝 Summary: writing…'] and all(m == 42 for _, m, _ in edits),
                "the status line says what is being done: downloading, each part, writing")
        _assert('Gist.' in edits[-1][2] and sent_new == [], "and becomes the summary itself")
        edits.clear()
        ai_watcher.process(dict(request, status_message=666, chat_id=505), None,
                           send=lambda chat_id, messages: sent_new.append(messages[0]), edit=edit)
        _assert(len(sent_new) == 1 and sent_new[0]['reply_to'] == 41,
                "a status line that is gone: the summary comes as a new reply to the audio")
        sent_new.clear()
        ai_watcher.process(dict(request, status_message=None, chat_id=506), None,
                           send=lambda chat_id, messages: sent_new.append(messages[0]), edit=edit)
        _assert(edits == [] and len(sent_new) == 1, "no status line (an automatic summary): as before")
    finally:
        ai_watcher.summary.summarize, ai_watcher.episode_transcript, ai.db_path, usage.db_path = saved

    from app.service.ai import offer
    _assert(offer.length_text(5400, 'en') == '1 h 30 min', "hours and minutes")
    _assert(offer.length_text(2701, 'ru') == '46 мин', "minutes round up")
    _assert(offer.length_text(5 * 3600, 'de') == '5 Std.', "whole hours")
    top = summaryModule.offer_message('en', quota.Quota(False, 30 * 3600, 29 * 3600, 7200, 3))
    _assert('30 h of audio' in top['text'] and '1 h left' in top['text'] and 'runs 2 h' in top['text']
            and 'reply_markup' not in top, "the top plan hears what is left, no plans to sell")
    trial = summaryModule.offer_message('en', quota.Quota(False, 5 * 3600, 4 * 3600, 7200, 3, True))
    _assert('A paid plan gives more: Relay 30 h' in trial['text']
            and [b['callback_data']['tp'] for row in trial['reply_markup'] for b in row] == ['bs_stars', 'bs_trfs'],
            "a trial over its hours hears what paying gives, with the Stars page and change-plan")
    bronze = summaryModule.offer_message('en', quota.Quota(False, 5 * 3600, 4 * 3600, 7200, 1))
    tps = [b['callback_data']['tp'] for row in bronze['reply_markup'] for b in row]
    _assert(tps == ['bs_stars', 'bs_trfs'],
            "a running plan gets the Stars page and change-plan, never an invoice that only tops it up")

    message = summaryModule.summary_message({'show': 'Show', 'title': 'T'}, '12:40 – a point', 'ep7', 4321, 'en')
    _assert(message['reply_to'] == 4321 and message['reply_markup'][0][0]['callback_data'] == {
        'tp': 'ask', 'r': 'ep7', 'm': 4321}, "a summary answers the audio and carries Ask")
    _assert('reply_to' not in summaryModule.summary_message({'show': 'S', 'title': 'T'}, 'x'),
            "without an audio message it is a plain message, as before")
    sent = []
    saved = (ai_watcher.summary.summarize, ai.db_path, usage.db_path)
    ai_watcher.summary.summarize = lambda *a, **k: ('Gist.', 0.002)
    ai.db_path = usage.db_path = db
    try:
        ai_watcher.process({'chat_id': 501, 'ref': 'ep7', 'lang': 'de', 'seconds': 60, 'reply_to': 99,
                            'ui_lang': 'ru'}, None, send=lambda chat_id, structures: sent.append(structures[0]))
    finally:
        ai_watcher.summary.summarize, ai.db_path, usage.db_path = saved
    _assert(sent[0]['reply_to'] == 99 and sent[0]['reply_markup'][0][0]['text'] == '❓ Спросить о выпуске',
            "the worker's summary answers the audio, its button in the user's interface language")
    _assert(sent[0]['reply_markup'][0][1]['callback_data'] == {'tp': 'trn', 'r': 'ep7', 'm': 99}
            and sent[0]['reply_markup'][0][1]['text'] == '📥 Расшифровка',
            "next to Ask: the transcript, for the same episode and audio")
    test_ask(db, summaryModule)
    test_transcript_download(db, summaryModule)


class Tap:
    def __init__(self, data, message_id=10):
        self.data = json.dumps(data)
        self.message_id = message_id


def test_ask(db, module):
    from types import SimpleNamespace
    states, sent, rendered, toasts, answered = {}, [], [], [], []
    fake_storage = SimpleNamespace(
        set_user_state_data=lambda chat, route, data: states.__setitem__((chat, route), data),
        get_user_state_data=lambda chat, route: states.get((chat, route)))

    def answer(text, title, show, question, session=None):
        answered.append((text, question))
        return 'At 0:00 they say so.', 0.0009

    from app.service.record import free_limit
    saved = (module.storage, module.outer_sender, module.render_messages, module.notify, module.summary.answer,
             module.summary.enabled, ai.db_path, usage.db_path, module.ai_quota.questions, free_limit.plans_offer)
    free_limit.plans_offer = lambda lang: ('Relay – 250 Stars', [[{'text': 'Relay', 'callback_data': {
        'tp': 'bs_stars_pay'}}], [{'text': 'Plans', 'callback_data': {'tp': 'bs_trfs'}}]])
    module.storage = fake_storage
    module.outer_sender = lambda chat, structures: sent.append(structures[0])
    module.render_messages = lambda chat, structures, resending=False: rendered.append(structures[0])
    module.notify = lambda call, message, text, alert=False: toasts.append(text)
    module.summary.answer = answer
    module.summary.enabled = lambda: True
    ai.db_path = usage.db_path = db
    left = [quota.Questions(True, 5, 5)]
    module.ai_quota.questions = lambda chat_id: left[0]
    try:
        tap = {'chat_id': 501, 'language_code': 'en', 'message': Tap({}, 10)}
        ai.remember_episode('nots', LINK, 9, 'No transcript', 'Show', database=db)
        _assert(module.ask(dict(tap, callback=Tap({'tp': 'ask', 'r': 'nots', 'm': 4}))) is False
                and 'summary first' in toasts[-1], "no transcript yet: get the summary first")
        left[0] = quota.Questions(False, 0, 0)
        module.ask(dict(tap, callback=Tap({'tp': 'ask', 'r': 'ep7', 'm': 4})))
        _assert('come with a plan' in sent[-1]['text']
                and [b['callback_data']['tp'] for row in sent[-1]['reply_markup'] for b in row][-1] == 'bs_trfs',
                "no plan: the plans, as for summaries")
        left[0] = quota.Questions(True, 5, 3)
        module.ask(dict(tap, callback=Tap({'tp': 'ask', 'r': 'ep7', 'm': 4})))
        opened = dict(states[(501, 'ask')])
        _assert(opened.pop('at') > 0 and opened == {'ref': 'ep7', 'audio': 4} and 'left today: 3' in rendered[-1]['text']
                and rendered[-1]['reply_markup'][0][0]['callback_data'] == {'tp': 'askDone'},
                "Ask opens the question screen with what is left and Done")
        module.ask({'chat_id': 501, 'language_code': 'en', 'callback': None,
                    'message': SimpleNamespace(text='What <b>do</b> they say?')})
        _assert(answered and answered[-1][1] == 'What <b>do</b> they say?', "the text is the question")
        _assert(sent[-1]['reply_to'] == 4 and 'What &lt;b&gt;do&lt;/b&gt; they say?' in sent[-1]['text']
                and 'At 0:00 they say so.' in sent[-1]['text'], "the answer replies to the audio, the question escaped")
        _assert(usage.count_since(501, 'ask', 0, db) == 1, "the question is counted")
        left[0] = quota.Questions(False, 5, 0)
        module.ask({'chat_id': 501, 'language_code': 'en', 'callback': None, 'message': SimpleNamespace(text='More?')})
        _assert(len(answered) == 1 and 'No questions left' in sent[-1]['text'] and 'reply_markup' not in sent[-1],
                "over the day's limit: no model call; a paid plan has nothing bigger to buy here")
        left[0] = quota.Questions(False, 5, 0, True)
        module.ask(dict(tap, callback=Tap({'tp': 'ask', 'r': 'ep7', 'm': 4})))
        _assert('A paid plan gives 20 questions a day' in sent[-1]['text']
                and [b['callback_data']['tp'] for row in sent[-1]['reply_markup'] for b in row] == ['bs_stars', 'bs_trfs'],
                "a trial at its limit hears what paying gives, with the Stars page and change-plan")
        left[0] = quota.Questions(False, 5, 0)

        import app.controller.builders as builders
        searched = []
        fake_search = SimpleNamespace(search=lambda data: searched.append((data['route_name'], data['message'].text)))
        saved_search = (sys.modules.get('app.controller.builders.searchModule'), getattr(builders, 'searchModule', None))
        sys.modules['app.controller.builders.searchModule'] = builders.searchModule = fake_search
        module.storage.add_user_state = lambda chat, route: states.__setitem__((chat, 'route'), route)
        try:
            states[(501, 'ask')] = dict(states[(501, 'ask')], at=time.time() - summary.ASK_IDLE_SECONDS - 1)
            left[0] = quota.Questions(True, 5, 5)
            module.ask({'chat_id': 501, 'language_code': 'en', 'callback': None, 'united_data': {'ref': 'ep7'},
                        'route_name': 'ask', 'message': SimpleNamespace(text='lex fridman')})
        finally:
            for name, value in (('sys', saved_search[0]), ('attr', saved_search[1])):
                if name == 'sys':
                    if value is None:
                        sys.modules.pop('app.controller.builders.searchModule', None)
                    else:
                        sys.modules['app.controller.builders.searchModule'] = value
                elif value is None:
                    del builders.searchModule
                else:
                    builders.searchModule = value
        _assert(searched == [('search', 'lex fridman')] and states[(501, 'route')] == 'search' and len(answered) == 1,
                "half an hour after the last question a text is a search again, no model call")
        states[(501, 'ask')] = {'ref': 'ep7', 'audio': 4, 'at': time.time()}
        sys.modules['app.controller.builders.searchModule'] = builders.searchModule = fake_search
        try:
            module.ask({'chat_id': 501, 'language_code': 'en', 'callback': None, 'united_data': {}, 'route_name': 'ask',
                        'message': SimpleNamespace(text='https://podcasts.apple.com/us/podcast/x/id123')})
        finally:
            sys.modules['app.controller.builders.searchModule'] = builders.searchModule = saved_search[0] or fake_search
        _assert(searched[-1][1].startswith('https://podcasts.apple.com') and len(answered) == 1,
                "a podcast link is not a question: search opens it, as before Ask")
        states[(501, 'ask')] = {'ref': 'ep7', 'audio': 4, 'at': time.time()}
        module.ask({'chat_id': 501, 'language_code': 'en', 'callback': None, 'message': SimpleNamespace(text='')})
        _assert(sent[-1]['text'] == 'Please type the question.' and len(answered) == 1,
                "a voice message or a photo: asked to type it, no model call")

        menus, markups = [], []
        import agent.bot_telebot as telebot_agent
        from app.controller.builders import menuModule
        saved_menu = (menuModule.construct_menu_message, telebot_agent.bot)
        menuModule.construct_menu_message = lambda lang, chat: [{'type': 'text', 'text': 'Menu'}]
        telebot_agent.bot = SimpleNamespace(edit_message_reply_markup=lambda chat, mid, reply_markup=None:
                                            markups.append((chat, mid, reply_markup)))
        module.storage.clear_user_storage = lambda chat: states.clear()
        module.render_messages = lambda chat, structures, resending=False: menus.append((structures[0], resending))
        from app.controller.builders import podcastModule
        pages, saved_page = [], podcastModule.channel_query
        podcastModule.channel_query = lambda page: pages.append(
            (page['callback'], json.loads(page['message'].text), dict(states)))
        stack = []
        module.storage.add_user_state = lambda chat, name: stack.append(name) or states.__setitem__((chat, 'route'), name)
        done = {'chat_id': 501, 'language_code': 'en', 'message': Tap({}, 77),
                'callback': SimpleNamespace(data='{"tp": "askDone"}', message=Tap({}, 77))}
        try:
            module.finish_ask(done)
            _assert(markups == [(501, 77, None)] and not menus and stack == ['menu', 'podcast']
                    and pages == [(None, {'id': 9}, {(501, 'route'): 'menu'})],
                    "Done: its button goes, the questions end, the episode's podcast page comes as a new message"
                    " (Back on it: the menu)")
            stack.clear()
            module.finish_ask(done)  # the state is gone (an old Done button): nothing to go back to
        finally:
            menuModule.construct_menu_message, telebot_agent.bot = saved_menu
            podcastModule.channel_query = saved_page
        _assert(len(pages) == 1 and menus == [({'type': 'text', 'text': 'Menu'}, True)] and stack == ['menu']
                and states == {(501, 'route'): 'menu'},
                "Done with the podcast not known: the menu comes as a new message")
        states.clear()
        left[0] = quota.Questions(True, 5, 5)
        module.render_outdated_screen = lambda data: rendered.append({'text': 'outdated'}) or False
        module.ask({'chat_id': 501, 'language_code': 'en', 'callback': None, 'message': SimpleNamespace(text='Q')})
        _assert(rendered[-1]['text'] == 'outdated' and len(answered) == 1, "a lost state is an outdated screen")
    finally:
        (module.storage, module.outer_sender, module.render_messages, module.notify, module.summary.answer,
         module.summary.enabled, ai.db_path, usage.db_path, module.ai_quota.questions, free_limit.plans_offer) = saved


def test_transcript_download(db, module):
    """The Transcript button under a summary: the cached transcript as a text file replying to the audio."""
    from types import SimpleNamespace
    import agent.bot_telebot as telebot_agent
    from lib.telegram.telebot.types import ApiTelegramException
    documents, toasts = [], []

    def send_document(chat_id, document, **kwargs):
        documents.append(dict(kwargs, chat_id=chat_id, body=document.read().decode('utf-8')))

    saved = (telebot_agent.bot, module.notify, ai.db_path)
    telebot_agent.bot = SimpleNamespace(send_document=send_document)
    module.notify = lambda call, message, text, alert=False: toasts.append((text, alert))
    ai.db_path = db
    try:
        ai.remember_episode('ep9', 'https://cdn.example/show/ep9.mp3', 9, 'Q&amp;A: <b>why</b>/how?', 'Show',
                            database=db)
        ai.save_transcript('ep9', '[0:00] Hello there. [0:31] Second part. [1:02:15] Late.', 'whisper', 0.01,
                           database=db)
        tap = {'chat_id': 501, 'language_code': 'en', 'message': Tap({}, 55)}
        module.send_transcript(dict(tap, callback=Tap({'tp': 'trn', 'r': 'ep9', 'm': 4})))
        document = documents[-1]
        _assert(toasts[-1] == ('', False) and document['chat_id'] == 501 and document['reply_to_message_id'] == 4
                and document['allow_sending_without_reply'] is True,
                "the file replies to the audio (sent anyway if the audio is gone)")
        _assert(document['visible_file_name'] == 'Q&A why how.txt',
                "the file is named after the episode, without characters a file name cannot hold")
        _assert(document['body'] == 'Show\nQ&A: why/how?\nhttps://cdn.example/show/ep9.mp3\n\n'
                '[0:00] Hello there.\n[0:31] Second part.\n[1:02:15] Late.\n',
                "the show, the title and the audio's link, then a line for each time mark")
        _assert(document['caption'] == '📄 <b>Show – Q&amp;A: why/how?</b>\nTranscribed automatically: it may have '
                'mistakes.' and document['parse_mode'] == 'HTML',
                "the caption names the episode (escaped) and says Whisper's text may have mistakes")
        module.send_transcript(dict(tap, callback=Tap({'tp': 'trn', 'r': 'ep7'})))
        _assert('mistakes' not in documents[-1]['caption'] and documents[-1]['reply_to_message_id'] is None
                and documents[-1]['body'].endswith('\n\nwords\n'),
                "the feed's own transcript makes no such claim; no audio known: a plain message")
        name, body = module.transcript_file({'show': 'S', 'title': 'T', 'link': 'L'}, {
            'text': ' '.join(['Sentence number %d is here.' % i for i in range(100)])})
        paragraphs = body.decode('utf-8').split('\n\n')[1:]
        _assert(name == 'T.txt' and len(paragraphs) > 3 and all(p.rstrip().endswith('.') for p in paragraphs)
                and all(len(p) < 2 * module.PARAGRAPH_CHARS for p in paragraphs),
                "a transcript without time marks comes in paragraphs broken after a sentence, not one long line")
        count = len(documents)
        module.send_transcript(dict(tap, callback=Tap({'tp': 'trn', 'r': 'nots', 'm': 4})))
        _assert(len(documents) == count and toasts[-1][1] is True and 'Tap "Summary"' in toasts[-1][0],
                "no transcript (pruned): an alert that the Summary button makes it again, no file")
        module.send_transcript(dict(tap, callback=Tap({'tp': 'trn', 'r': 'gone'})))
        from app.i18n.messages import get_message
        _assert(len(documents) == count and toasts[-1][0] == get_message('screenOutdated', 'en'),
                "an unknown episode: an outdated screen")

        def flood(chat_id, document, **kwargs):
            raise ApiTelegramException('sendDocument', SimpleNamespace(status_code=429, reason='', text=''), {
                'error_code': 429, 'description': 'Too Many Requests: retry after 7'})
        telebot_agent.bot = SimpleNamespace(send_document=flood)
        module.send_transcript(dict(tap, callback=Tap({'tp': 'trn', 'r': 'ep9', 'm': 4})))  # does not raise
        _assert(len(json.dumps(summary.transcript_button_data('0123456789abcdef', 2 ** 31), separators=(',', ':')))
                <= 64, "the button's data fits Telegram's 64 bytes")
    finally:
        telebot_agent.bot, module.notify, ai.db_path = saved


def main():
    test_transcripts()
    test_openrouter()
    with tempfile.TemporaryDirectory() as tmp:
        test_transcription(tmp)
        db = os.path.join(tmp, 'test.sqlite')
        test_queue_and_quota(db)
        test_auto(os.path.join(tmp, 'auto.sqlite'))
        test_hint(os.path.join(tmp, 'hint.sqlite'))
        test_worker(os.path.join(tmp, 'worker.sqlite'))
    print("all AI summary checks passed")


if __name__ == "__main__":
    main()
