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

import config  # noqa: E402
from app.i18n.messages import get_message  # noqa: E402
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
    _assert(transcript.transcript_text(vtt, 'text/vtt') == '[0:01] Ann: Hello there. Bye.',
            "VTT: a voice names the turn, cue timings go, a time mark stays (the next cue is within 30 s)")
    vtt = ("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n<v Speaker 1>Hi,\n\n00:00:03.000 --> 00:00:05.000\n"
           "<v Speaker 1>Ann.\n\n00:00:05.500 --> 00:00:06.000\n<v Speaker 2>Hey.")
    _assert(transcript.transcript_text(vtt, 'text/vtt') == '[0:01] Speaker 1: Hi, Ann. [0:05] Speaker 2: Hey.',
            "a change of speaker is a mark and a label, even within 30 s; the same speaker goes on unlabelled")
    srt = ("1\n00:00:01,000 --> 00:00:02,000\nSpeaker 0: \n\n2\n00:00:03,000 --> 00:00:04,000\nSpeaker 0: One.\n\n"
           "3\n00:00:04,000 --> 00:00:05,000\nSpeaker 0: Two.\n\n4\n00:00:06,000 --> 00:00:07,000\nNote: three.")
    _assert(transcript.transcript_text(srt) == '[0:03] Speaker 0: One. Two. Note: three.',
            "SRT with 'Speaker 0:' per cue: one label a turn; an empty cue goes; 'Note:' is text, not a speaker")
    plain = "00:00:01\nSpeaker 1: Happy Samhain.\n\n00:01:11\nSpeaker 2: Welcome.\n\n00:01:21\nSpeaker 1: Hey."
    _assert(transcript.transcript_text(plain, 'text/plain')
            == '[0:01] Speaker 1: Happy Samhain. [1:11] Speaker 2: Welcome. [1:21] Speaker 1: Hey.',
            "plain text with a time on a line of its own (omny's TextWithTimestamps): marks, not text")
    srt = "1\n00:00:01,000 --> 00:00:04,000\nHello.\n\n2\n00:00:45,000 --> 00:00:47,000\nBye."
    _assert(transcript.transcript_text(srt) == '[0:01] Hello. [0:45] Bye.', "SRT: cue numbers go, marks 30 s apart")
    js = json.dumps({'segments': [{'body': 'Hello.'}, {'body': ' Bye. '}]})
    _assert(transcript.transcript_text(js, 'application/json') == 'Hello. Bye.', "podcast JSON segments")
    js = json.dumps({'segments': [{'startTime': 3725.5, 'body': 'Late.'}, {'startTime': 3730, 'body': 'Still.'}]})
    _assert(transcript.transcript_text(js, 'application/json') == '[1:02:05] Late. Still.',
            "JSON startTime: hours when past one")
    js = json.dumps({'segments': [{'startTime': 1, 'speaker': 'Ann', 'body': 'Hi.'},
                                  {'startTime': 2, 'speaker': 'Bob', 'body': 'Yo.'}]})
    _assert(transcript.transcript_text(js, 'application/json') == '[0:01] Ann: Hi. [0:02] Bob: Yo.',
            "JSON speaker: turns")
    js = json.dumps([{'start': 3.5, 'end': 3.8, 'text': ''}, {'start': 11.8, 'text': 'Push me'},
                     {'start': 45, 'text': 'Later.'}])
    _assert(transcript.transcript_text(js, 'application/json') == '[0:11] Push me [0:45] Later.',
            "a bare JSON list of {start, text} (podigee)")
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
    summary.summarize('[0:00] Hi. [0:31] More.', 'Seven', 'Show', summary.ORIGINAL, session=session)
    marked, plain = session.calls[2][2]['messages'][1]['content'], session.calls[1][2]['messages'][1]['content']
    _assert(summary.WITH_MARKS in marked and summary.WITHOUT_MARKS not in marked
            and summary.WITHOUT_MARKS in plain and summary.WITH_MARKS not in plain
            and 'never invent a time' in summary.WITH_MARKS and '12:40' not in summary.SYSTEM,
            "the code says whether the transcript has times (the model once wrote it had none into a summary)")
    _assert('never a word about the transcript' in summary.SYSTEM, "and the summary says nothing about its format")
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


def test_language(tmp):
    """Whisper is told the language: the feed's when two samples hear it, else the samples' when all three
    agree, else nothing."""
    channel = ET.fromstring('<rss><channel><language>en-US</language></channel></rss>').find('channel')
    _assert(transcript.feed_language(channel) == 'en' and transcript.feed_language(None) == ''
            and transcript.feed_language(ET.fromstring('<channel><language>English</language></channel>')) == '',
            "the feed's language as a code; a name or none is no language")
    choose = transcript.choose_language
    _assert(choose(['tr', 'az', 'tr'], 'tr') == 'tr', "two samples say the feed's language (a Turkish lesson)")
    _assert(choose(['fa', 'fa', 'fa'], 'en') == 'fa', "the feed is wrong, the samples all agree: the samples")
    _assert(choose(['en', 'fr', 'en'], 'fr') is None and choose(['en', 'fr', 'en']) is None,
            "the samples disagree and do not confirm the feed: Whisper guesses, as before")
    _assert(choose(['de', 'de', ''], 'de') == 'de' and choose(['de', 'de', '']) is None,
            "a sample that could not be asked counts as no answer")
    piece = os.path.join(tmp, 'piece000.mp3')
    with open(piece, 'wb') as f:
        f.write(b'ID3')
    session = FakeSession(FakeResponse(200, {'text': 'Merhaba.', 'usage': {'seconds': 600, 'cost': 0.002}}))
    transcript.transcribe_piece(session, piece, language='tr')
    _assert(session.calls[0][2][1]['language'] == 'tr', "the language goes with the piece")
    transcript.transcribe_piece(session, piece)
    _assert('language' not in session.calls[1][2][1], "none: Whisper guesses")
    detect = FakeSession(FakeResponse(200, {'text': 'x', 'language': 'TR', 'usage': {'cost': 0.0001}}))
    _assert(transcript.detect_language(detect, piece) == ('tr', 0.0001), "a sample's language, as a code")

    saved = (transcript._duration, transcript.subprocess.run, transcript.detect_language)
    answers = iter([('tr', 0.0001), ('az', 0.0001), ('tr', 0.0001)])
    transcript._duration = lambda path: 540.0
    transcript.subprocess.run = lambda *a, **k: None
    transcript.detect_language = lambda session, path: next(answers)
    try:
        language, cost = transcript.speech_language(None, piece, tmp, 'tr')
        _assert(language == 'tr' and abs(cost - 0.0003) < 1e-9, "three samples asked, their cost counted")

        def broken(session, path):
            raise openrouter.OpenRouterError('down')
        transcript.detect_language = broken
        _assert(transcript.speech_language(None, piece, tmp, 'tr') == (None, 0.0),
                "samples that cannot be asked: no language, the transcript goes on")
        transcript._duration = lambda path: 60.0
        _assert(transcript.speech_language(None, piece, tmp, 'en') == (None, 0.0),
                "too short to sample: Whisper guesses (the feed's word alone can be wrong)")
    finally:
        transcript._duration, transcript.subprocess.run, transcript.detect_language = saved


def test_speakers(tmp):
    """The paid model: who speaks, kept apart across pieces by the words their overlap shares."""
    saved_overlap, transcript.OVERLAP_SECONDS = transcript.OVERLAP_SECONDS, 30  # the cases below overlap 30 s
    try:
        _speakers(tmp)
    finally:
        transcript.OVERLAP_SECONDS = saved_overlap
    _assert(transcript.SPEAKER_PIECE_SECONDS >= 30 * 60 and transcript.OVERLAP_SECONDS >= 120,
            "long pieces and a long overlap: few joins, and most speakers heard in each")


def _speakers(tmp):
    piece = os.path.join(tmp, 'piece001.mp3')
    with open(piece, 'wb') as f:
        f.write(b'ID3')
    session = FakeSession(FakeResponse(200, {'usage': {'seconds': 630, 'cost': 0.0175}, 'words': [
        {'word': 'Hi,', 'start': 1.0, 'speaker': 0}, {'word': ' ', 'start': 1.2, 'type': 'spacing'},
        {'word': 'you.', 'start': 1.4, 'speaker': 0}, {'word': 'Yes.', 'start': 2.0, 'speaker': 1}]}))
    words, cost, seconds = transcript.transcribe_speaker_piece(session, piece, 570.0, 'x-ai/grok-stt-1.0')
    _assert(words == [(571.0, 'Hi,', 0), (571.4, 'you.', 0), (572.0, 'Yes.', 1)] and (cost, seconds) == (0.0175, 630),
            "the words with their speakers, from the episode's start; spacing goes")
    url, headers, body = session.calls[0]
    _assert(body['model'] == 'x-ai/grok-stt-1.0' and body['input_audio']['format'] == 'mp3'
            and body['timestamp_granularities'] == ['segment', 'word']
            and body['provider']['options']['xai'] == {'diarize': True},
            "JSON with the audio inline, words, and the provider's own diarization switch")
    plain = FakeSession(FakeResponse(200, {'segments': [{'start': 3, 'text': 'No words.'}]}))
    _assert(transcript.transcribe_speaker_piece(plain, piece, 0.0, 'm')[0] == [(3.0, 'No words.', None)],
            "no words: the segments, still timed")

    # piece 2 numbers the speakers the other way round; the overlap (570-600 s) says who is who
    first = [(560.0, 'So', 0), (561.0, 'what', 0), (575.0, 'I', 1), (575.5, 'think', 1), (576.0, 'so', 1),
             (590.0, 'Right', 0), (590.5, 'then', 0)]
    second = [(575.1, 'I', 0), (575.6, 'think', 0), (576.1, 'so', 0), (590.1, 'Right', 1), (590.4, 'then', 1),
              (601.0, 'Next.', 1), (603.0, 'Okay.', 0), (604.0, 'New', 2), (605.0, 'voice.', 2)]
    merged = transcript.merge_speakers([(0.0, first), (570.0, second)])
    _assert([w for w in merged if w[0] >= 600] == [(601.0, 'Next.', 0), (603.0, 'Okay.', 1), (604.0, 'New', 2),
                                                    (605.0, 'voice.', 2)],
            "a speaker keeps their number across pieces; one not heard in the overlap is new")
    _assert(sum(1 for w in merged if 570 <= w[0] < 600) == 5, "the overlap's words come once, from the piece before")
    one = [(10.0, 'Hi', 1), (575.0, 'I', 0), (575.5, 'think', 0)]
    two = [(575.1, 'I', 5), (575.6, 'think', 5), (610.0, 'Yes.', 7)]
    merged = transcript.merge_speakers([(0.0, one), (570.0, two)])
    _assert(merged[-1] == (610.0, 'Yes.', 0), "a piece's only unmatched speaker against the only known one it "
            "did not match: that one, by elimination")
    quiet = [(560.0, 'A', 0), (561.0, 'B', 1), (562.0, 'C', 2), (575.0, 'x', 0), (575.5, 'y', 0)]
    again = [(575.1, 'x', 0), (575.6, 'y', 0), (601.0, 'D', 1), (602.0, 'E', 2)]
    merged = transcript.merge_speakers([(0.0, quiet), (570.0, again)])
    _assert({w[2] for w in merged if w[0] >= 600} == {3, 4}, "two unmatched against two: no guess, new speakers")
    text = transcript.speaker_text([(0.0, 'Hello', 0), (0.4, 'there.', 0), (31.0, 'Still', 0), (32.0, 'me.', 0),
                                    (40.0, 'Mid', 0), (61.0, 'sentence', 0), (62.0, 'here.', 0), (63.0, 'Hi.', 1)])
    _assert(text == '[0:00] Speaker 1: Hello there. [0:31] Still me. Mid sentence here. [1:03] Speaker 2: Hi.',
            "a turn for each speaker, marks only where a sentence starts, at most every 30 s")


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

    summary_id, _ = ai.enqueue(506, 'both', 'original', hour, db)
    transcript_id, new = ai.enqueue(506, 'both', '', hour, db, kind=ai.TRANSCRIPT)
    _assert(new and transcript_id != summary_id
            and ai.enqueue(506, 'both', '', hour, db, kind=ai.TRANSCRIPT) == (transcript_id, False),
            "a transcript is a request of its own next to the summary; a second tap is the same one")
    _assert(ai.audio_paid(506, 'both', db) and not ai.audio_paid(506, 'both', db, done_only=True),
            "on its way, the audio counts as paid for a tap; for the worker only once done")
    ai.finish(summary_id, 'done', seconds=1800, database=db)
    _assert(ai.audio_paid(506, 'both', db, exclude=transcript_id, done_only=True)
            and not ai.audio_paid(506, 'both', db, exclude=summary_id, done_only=True),
            "a done request charged seconds pays the audio; a request does not pay for itself")
    _assert(not ai.audio_paid(507, 'both', db) and not ai.audio_paid(501, 'served', db),
            "another chat's request, or one a cached summary served (0 s), pays nothing")

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
    _assert(sqlite3.connect(old_db).execute('SELECT reply_to, kind FROM ai_requests').fetchone() == (5, 'summary'),
            "a database from before gets the reply_to and kind columns, its requests summaries")

    bronze = config.ai_questions_per_day[1]
    _assert(quota.questions(501, database=db)[:4] == (True, bronze, bronze, False),
            "a paid plan asks its plan's questions a day")
    _assert(quota.most_questions_per_day() == max(config.ai_questions_per_day.values()),
            "'up to': the most a plan gives")
    _assert(quota.questions(502, database=db)[:3] == (False, 0, 0), "no plan: no questions")
    for _ in range(config.ai_trial_questions_per_day):
        usage.record_ask(504, 'ep', 0.001, db)
    usage.record_ask(504, 'ep', 0.001, db, at=now - 2 * 86400)
    _assert(quota.questions(504, database=db)[:4] == (False, config.ai_trial_questions_per_day, 0, True),
            "a trial has fewer, counted over the last 24 hours")
    _assert(abs(usage.per_user(0, database=db)[504]['ai_usd'] - 0.006) < 1e-9, "questions are in the AI spend")
    # the 30 days' count: a day with questions left still stops at it
    for day in range(1, config.ai_trial_questions_per_month // config.ai_trial_questions_per_day + 1):
        for _ in range(config.ai_trial_questions_per_day):
            usage.record_ask(504, 'ep', 0.001, db, at=now - day * 86400 - 3600)
    month = quota.questions(504, now=now + 86401, database=db)
    _assert(month[:3] == (False, config.ai_trial_questions_per_day, 0) and month.month_limit == config.ai_trial_questions_per_month,
            "a trial stops at its 30 days' questions, a day with questions left or not")
    _assert(quota.questions(504, now=now + 40 * 86400, database=db).allowed, "past 30 days they come back")


def test_budget(db):
    """The owner's rule: no plan costs more in AI than it brings. A plan paid for stops at its budget
    (a share of its price at what reaches us); the paid model has its hours per plan; a trial has neither."""
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER, lang TEXT);
        CREATE TABLE tariffs (id INTEGER PRIMARY KEY, level INTEGER, price INTEGER);
        CREATE TABLE user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER, tariff_id INTEGER, time_left INTEGER);
        CREATE TABLE payment_history (user_id INTEGER, status TEXT);
        INSERT INTO users VALUES (1, 601, 'en'), (3, 603, 'en'), (4, 604, 'en');
        INSERT INTO tariffs VALUES (1, 1, 100), (3, 3, 500);
        INSERT INTO user_tariff_cs VALUES (1, 1, 1, 100), (3, 3, 3, 100), (4, 4, 3, 100);
        INSERT INTO payment_history VALUES (1, 'paid'), (3, 'paid');
    """)
    c.commit()
    c.close()
    share = config.payout_share.get('telegramStars', 1.0) * config.ai_budget_share
    _assert(share <= 1, "a plan's AI budget is never more than what the plan brings")
    bronze = quota.budget(601, database=db)
    _assert(abs(bronze.limit - 1.0 * share) < 1e-9 and bronze.spent == 0, "Bronze's budget: its price at the share")
    _assert(quota.budget(604, database=db) is None, "a trial has its own few hours, no budget")
    _assert(quota.check(601, 1800, database=db).allowed and quota.questions(601, database=db).allowed,
            "within the budget: as before")

    usage.record_ai(601, 'ep', bronze.limit - 0.005, db)
    over = quota.check(601, 1800, database=db)
    _assert(not over.allowed and over.budget and over.used == 0,
            "a summary that would pass the budget is refused, though the hours are there")
    asked = quota.questions(601, database=db)
    _assert(not asked.allowed and asked.budget and asked.left > 0, "so is a question")
    _assert(not quota.paid_transcribe_fits(601, 600, database=db), "and the paid model")
    from app.service.ai.offer import budget_message
    _assert(budget_message('en', 3)['text'] == get_message('aiBudgetSpent', 'en'),
            "the top plan hears that its AI for the 30 days is spent, nothing to sell")
    usage.record_ai(604, 'ep', 5.0, db)
    _assert(quota.check(604, 1800, database=db).allowed, "a trial is not stopped by money spent")

    relay_paid = config.ai_paid_transcribe_hours_per_month[3] * 3600
    _assert(quota.paid_transcribe_fits(603, 3600, database=db), "Relay: the paid model within its hours")
    request_id, _ = ai.enqueue(603, 'long', 'en', 3600, db)
    ai.note_paid_seconds(request_id, relay_paid - 1800, db)
    _assert(ai.paid_seconds_used(603, 0, db) == relay_paid - 1800, "the paid model's seconds are counted")
    _assert(not quota.paid_transcribe_fits(603, 3600, database=db) and quota.paid_transcribe_fits(603, 1200, database=db),
            "past the plan's hours of the paid model: Whisper")
    _assert(not quota.paid_transcribe_fits(604, 60, database=db), "a trial has no hours of the paid model")


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
        CREATE TABLE tariffs (id INTEGER PRIMARY KEY, level INTEGER, price INTEGER);
        INSERT INTO tariffs VALUES (3, 3, 500);
        CREATE TABLE payment_history (user_id INTEGER, status TEXT);
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

    def summarize(text, title, show, language, session=None, model=None):
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
    ai_watcher.episode_transcript = lambda episode, session, progress=None, speakers=False: (transcript.Transcript(
        'words', 'whisper', 0.02, 3600.0), True)
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

    def whisper(episode, session, progress=None, speakers=False):
        progress('download')
        progress('transcribe', 1, 2)
        progress('transcribe', 2, 2)
        return transcript.Transcript('[0:00] words', 'whisper', 0.0, 600.0), True
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

    test_transcript_requests(db, ai_watcher)

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
    from app.service.record import free_limit
    saved_plans, free_limit.plans_offer = free_limit.plans_offer, lambda language_code: (
        'Plans.', [[{'text': 'Relay', 'callback_data': {'tp': 'bs_stars_pay'}}]])  # the storefront reads tariffs
    try:
        for_plans = summaryModule.offer_message('en', quota.Quota(False, 0, 0, 3600, 0), transcript=True)
    finally:
        free_limit.plans_offer = saved_plans
    _assert(for_plans['text'].startswith('Transcripts come with a plan') and 'the podcast publishes' in for_plans['text']
            and for_plans['reply_markup'], "no plan, asked for a transcript: the plans, said for transcripts")
    over = summaryModule.offer_message('en', quota.Quota(False, 5 * 3600, 4 * 3600, 7200, 3, True), transcript=True)
    _assert(over['text'].startswith('Transcripts and summaries count by episode length')
            and [b['callback_data']['tp'] for row in over['reply_markup'] for b in row] == ['bs_stars', 'bs_trfs'],
            "over the hours: the same storefront rules as a summary, the text names transcripts")
    test_ask(db, summaryModule)
    test_plan_text()
    test_feed_transcript(db, summaryModule)
    test_transcript_button(db, summaryModule)


class Tap:
    def __init__(self, data, message_id=10):
        self.data = json.dumps(data)
        self.message_id = message_id


def test_plan_text():
    """A plan's description says its AI: hours, questions a day, the paid model's hours among them."""
    from app.service.ai import paid_models
    from app.service.payment import paymentModule
    saved = (summary.enabled, paid_models.transcribe_model)
    summary.enabled = lambda: True
    paid_models.transcribe_model = lambda with_speakers: 'paid/stt' if with_speakers else 'whisper'
    try:
        text = paymentModule.ai_plan_text(2, 'en')
        _assert(text == '\n' + get_message('trf_descr_ai', 'en').format(
            hours=config.ai_summary_hours_per_month[2], questions=config.ai_questions_per_day[2],
            month=config.ai_questions_per_month[2]) + ' '
                + get_message('trf_descr_ai_paid', 'en').format(paid=config.ai_paid_transcribe_hours_per_month[2]),
                "Silver: its hours, its questions, its hours of the paid model")
        paid_models.transcribe_model = lambda with_speakers: 'whisper'
        _assert(get_message('trf_descr_ai_paid', 'en').format(paid=config.ai_paid_transcribe_hours_per_month[3])
                not in paymentModule.ai_plan_text(3, 'en'),
                "no paid model configured: no promise of it")
        _assert(paymentModule.ai_plan_text(0, 'en') == '', "no plan, no line")
        summary.enabled = lambda: False
        _assert(paymentModule.ai_plan_text(3, 'en') == '', "AI off: no line")
    finally:
        summary.enabled, paid_models.transcribe_model = saved


def test_ask(db, module):
    from types import SimpleNamespace
    states, sent, rendered, toasts, answered = {}, [], [], [], []
    fake_storage = SimpleNamespace(
        set_user_state_data=lambda chat, route, data: states.__setitem__((chat, route), data),
        get_user_state_data=lambda chat, route: states.get((chat, route)))

    def answer(text, title, show, question, session=None, model=None):
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
        _assert('A paid plan gives up to 20 questions a day' in sent[-1]['text']
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


def test_feed_transcript(db, module):
    """The transcript a feed publishes, read at a tap from the feed's last copy, cached for everyone;
    a feed that cannot be read now is no transcript, never an error."""
    from app.service.podcast import rss
    asked = []

    class Requester:
        def get(self, url, timeout=None):
            asked.append((url, timeout))
            return SimpleResponse(200, 'WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nFrom the feed.', 'text/vtt')

    def feed(url, etag=None, last_modified=None, cached=False):
        asked.append((url, cached))
        return ET.fromstring(FEED), 'ok', {}

    saved = (rss.get_rss_root_with_status, ai.db_path)
    rss.get_rss_root_with_status = feed
    ai.db_path = db
    try:
        episode = {'ref': 'f7', 'link': LINK, 'feed_url': 'https://feed.example/rss'}
        found = transcript.from_episode_feed(Requester(), episode, cached=True, timeout=(5, 20))
        _assert(found == transcript.Transcript('[0:01] From the feed.', 'feed', 0.0, 0.0)
                and asked == [('https://feed.example/rss', True), ('https://t.example/7.vtt', (5, 20))],
                "the feed's last copy names the item's transcript, read with the tap's short timeout")
        _assert(transcript.from_episode_feed(Requester(), dict(episode, feed_url=None)) is None,
                "a channel that is gone: no feed, no transcript")
        from lib.requests import requesterModule
        real_requester, requesterModule.Requester = requesterModule.Requester, lambda **kwargs: Requester()
        try:
            ai.remember_episode('f7', LINK, 9, 'Seven', 'Show', database=db)
            found = module._feed_transcript(ai.episode('f7', db))
            _assert(found.source == 'feed' and ai.transcript('f7', db)['text'] == '[0:01] From the feed.',
                    "a tap caches the feed's transcript: free for the next tap and for a summary")
            rss.get_rss_root_with_status = lambda *a, **k: (_ for _ in ()).throw(TimeoutError('slow host'))
            _assert(module._feed_transcript(ai.episode('f7', db)) is None, "a feed that times out: none, no error")
        finally:
            requesterModule.Requester = real_requester
    finally:
        rss.get_rss_root_with_status, ai.db_path = saved


class SimpleResponse:
    def __init__(self, status, text, content_type):
        self.status_code, self.text, self.headers = status, text, {'Content-Type': content_type}


def test_transcript_requests(db, ai_watcher):
    """A transcript request: no model call, the file replies to the audio, the status line goes; charged
    what Whisper measured, nothing for a transcript made before or the feed's. A summary after a
    transcript the chat paid for costs no more hours."""
    files, edits, deleted = [], [], []

    def whisper(episode, session, progress=None, speakers=False):
        progress('download')
        progress('transcribe', 1, 1)
        return transcript.Transcript('[0:00] spoken words', 'whisper', 0.03, 1830.4), True

    def no_model(*args, **kwargs):
        raise AssertionError('a transcript request never calls the model')

    saved = (ai_watcher.summary.summarize, ai_watcher.episode_transcript, ai.db_path, usage.db_path)
    ai_watcher.summary.summarize = no_model
    ai_watcher.episode_transcript = whisper
    ai.db_path = usage.db_path = db
    send_file = lambda chat_id, episode, text, source, lang, reply_to, over_quota=False: files.append(  # noqa: E731
        (chat_id, episode['ref'], text, source, lang, reply_to)) or True
    edit = lambda chat_id, message, message_id: edits.append((message_id, message['text']))  # noqa: E731
    delete = lambda chat_id, message_id: deleted.append(message_id)  # noqa: E731
    try:
        ai.remember_episode('t1', 'https://cdn.example/show/t1.mp3', 9, 'Tee', 'Show', 1800, database=db)
        request_id, _ = ai.enqueue(520, 't1', '', 1800, db, reply_to=61, status_message=62, kind=ai.TRANSCRIPT)
        request = {'id': request_id, 'chat_id': 520, 'ref': 't1', 'lang': '', 'seconds': 1800, 'kind': ai.TRANSCRIPT,
                   'reply_to': 61, 'status_message': 62, 'ui_lang': 'en'}
        charged = ai_watcher.process(request, None, edit=edit, send_file=send_file, delete=delete)
        ai.finish(request_id, 'done', seconds=charged, database=db)
        _assert(charged == 1830, "a new transcript is charged what Whisper measured")
        _assert(files == [(520, 't1', '[0:00] spoken words', 'whisper', 'en', 61)],
                "the file replies to the audio, in the user's language")
        _assert([text for _, text in edits] == ['📥 Transcript: downloading the episode…',
                                                '📥 Transcript: transcribing, part 1 of 1…'] and deleted == [62],
                "its status line says it is a transcript, and goes when the file comes")
        _assert(abs(usage.per_user(0, database=db)[520]['ai_usd'] - 0.03) < 1e-9
                and usage.count_since(520, 'transcript', 0, db) == 1 and usage.count_since(520, 'ai', 0, db) == 0,
                "Whisper's cost is in the AI spend, the file is a transcript in the ledger, not a summary")

        # the same chat's summary of it: the transcript is cached and paid for, only the model call
        ai.save_transcript('t1', '[0:00] spoken words', 'whisper', 0.03, 1830.4, database=db)
        ai_watcher.summary.summarize = lambda *a, **k: ('Gist.', 0.002)
        ai_watcher.episode_transcript = lambda episode, session, progress=None, speakers=False: (
            transcript.Transcript('[0:00] spoken words', 'whisper', 0.0, 1830.4), False)
        mine, _ = ai.enqueue(520, 't1', 'original', 0, db)
        theirs, _ = ai.enqueue(521, 't1', 'original', 1800, db)
        sent = []
        send = lambda chat_id, structures: sent.append(chat_id)  # noqa: E731
        _assert(ai_watcher.process({'id': mine, 'chat_id': 520, 'ref': 't1', 'lang': 'original', 'seconds': 0},
                                   None, send=send) == 0,
                "a summary after the chat's own transcript costs no more hours")
        c = sqlite3.connect(db)  # the summary just made would serve the next chat: it must be new
        c.execute("DELETE FROM ai_summaries WHERE ref='t1'")
        c.commit()
        c.close()
        _assert(ai_watcher.process({'id': theirs, 'chat_id': 521, 'ref': 't1', 'lang': 'original', 'seconds': 1800},
                                   None, send=send) == 1830,
                "another chat's summary of it is charged the audio, as before")

        # a transcript made before, or the feed's: free
        ai_watcher.summary.summarize = no_model
        files.clear()
        cached = ai_watcher.process({'id': 0, 'chat_id': 522, 'ref': 't1', 'lang': '', 'seconds': 1800,
                                     'kind': ai.TRANSCRIPT}, None, edit=edit, send_file=send_file, delete=delete)
        ai_watcher.episode_transcript = lambda episode, session, progress=None, speakers=False: (
            transcript.Transcript('the feed text', 'feed', 0.0, 0.0), False)
        ai.remember_episode('t2', 'https://cdn.example/show/t2.mp3', 9, 'Two', 'Show', 1800, database=db)
        feed = ai_watcher.process({'id': 0, 'chat_id': 522, 'ref': 't2', 'lang': '', 'seconds': 1800,
                                   'kind': ai.TRANSCRIPT}, None, edit=edit, send_file=send_file, delete=delete)
        _assert((cached, feed) == (0, 0) and [f[3] for f in files] == ['whisper', 'feed'],
                "made before, or the feed's: the file, nothing charged")
        _assert(ai_watcher.FAILED[ai.TRANSCRIPT] == 'transcriptFailed', "a failed transcript says so, not 'summary'")
    finally:
        ai_watcher.summary.summarize, ai_watcher.episode_transcript, ai.db_path, usage.db_path = saved

    # the better models: Whisper's cached transcript is made again with speakers; the feed's or one with
    # speakers is not; the summary goes to the paid model
    made = []

    def from_audio(requester, session, link, progress=None, speakers_model=None, feed_language=''):
        made.append(speakers_model)
        return transcript.Transcript('[0:00] Speaker 1: Hi.', 'speakers' if speakers_model else 'whisper', 0.02, 600.0)
    saved = (ai_watcher.transcript.from_audio, ai_watcher.transcript.episode_feed, ai.db_path,
             ai_watcher.paid_models.transcribe_model)
    ai_watcher.transcript.from_audio = from_audio
    ai_watcher.transcript.episode_feed = lambda episode: None
    ai_watcher.paid_models.transcribe_model = lambda with_speakers: 'x-ai/grok-stt-1.0' if with_speakers else 'w'
    ai.db_path = db
    try:
        ai.remember_episode('u1', 'https://cdn.example/show/u1.mp3', 9, 'U', 'Show', 600, database=db)
        ai.save_transcript('u1', '[0:00] Hi.', 'whisper', 0.003, 600.0, database=db)
        episode = ai.episode('u1', db)
        found, was_made = ai_watcher.episode_transcript(episode, None)
        _assert((found.source, was_made, made) == ('whisper', False, []), "without them the cache serves")
        found, was_made = ai_watcher.episode_transcript(episode, None, speakers=True)
        _assert((found.source, was_made, made) == ('speakers', True, ['x-ai/grok-stt-1.0'])
                and ai.transcript('u1', db)['source'] == 'speakers',
                "with them Whisper's is made again with speakers, and cached for everyone")
        found, was_made = ai_watcher.episode_transcript(episode, None, speakers=True)
        _assert((found.source, was_made, len(made)) == ('speakers', False, 1), "one with speakers is not made again")
        ai.save_transcript('u1', 'From the feed.', 'feed', 0.0, database=db)
        _assert(ai_watcher.episode_transcript(episode, None, speakers=True)[0].source == 'feed' and len(made) == 1,
                "nor the feed's")
    finally:
        (ai_watcher.transcript.from_audio, ai_watcher.transcript.episode_feed, ai.db_path,
         ai_watcher.paid_models.transcribe_model) = saved

    models = []
    saved = (ai_watcher.summary.summarize, ai_watcher.episode_transcript, ai_watcher.paid_models.summary_model,
             ai_watcher.paid_models.speakers, ai_watcher.paid_models.speakers_fit, ai.db_path, usage.db_path)
    ai_watcher.summary.summarize = lambda *a, **k: models.append(k.get('model')) or ('Gist.', 0.01)
    ai_watcher.episode_transcript = lambda episode, session, progress=None, speakers=False: (
        models.append(('speakers', speakers)) or transcript.Transcript('t', 'feed', 0.0, 0.0), False)
    ai_watcher.paid_models.summary_model = lambda chat_id, database=None: 'paid/strong' if chat_id == 530 else 'base'
    ai_watcher.paid_models.speakers = lambda chat_id, database=None: chat_id == 530
    ai_watcher.paid_models.speakers_fit = lambda chat_id, seconds, database=None: chat_id == 530
    ai.db_path = usage.db_path = db
    try:
        ai.remember_episode('u2', 'https://cdn.example/show/u2.mp3', 9, 'U2', 'Show', 600, database=db)
        ai_watcher.process({'chat_id': 530, 'ref': 'u2', 'lang': 'xx', 'seconds': 600}, None, send=lambda *a: None)
        c = sqlite3.connect(db)
        c.execute("DELETE FROM ai_summaries WHERE ref='u2'")
        c.commit()
        c.close()
        ai_watcher.process({'chat_id': 531, 'ref': 'u2', 'lang': 'xx', 'seconds': 600}, None, send=lambda *a: None)
        _assert(models == [('speakers', True), 'paid/strong', ('speakers', False), 'base'],
                "a paying chat with them: transcript with speakers, summary by the paid model; others as before")
        request_id, _ = ai.enqueue(530, 'u3', 'xx', 600, db)
        made_now = transcript.Transcript('t', transcript.SPEAKERS, 0.02, 590.0)
        ai_watcher._note_paid({'id': request_id}, made_now, False)
        ai_watcher._note_paid({'id': request_id}, transcript.Transcript('t', 'whisper', 0.0, 590.0), True)
        _assert(ai.paid_seconds_used(530, 0, db) == 0, "only what the paid model made now counts")
        ai_watcher._note_paid({'id': request_id}, made_now, True)
        _assert(ai.paid_seconds_used(530, 0, db) == 590, "toward the chat's hours of the paid model")
    finally:
        (ai_watcher.summary.summarize, ai_watcher.episode_transcript, ai_watcher.paid_models.summary_model,
         ai_watcher.paid_models.speakers, ai_watcher.paid_models.speakers_fit, ai.db_path, usage.db_path) = saved


def test_transcript_button(db, module):
    """Transcript under the audio and under a summary: the file at once when it is made or the feed has it;
    else only the transcript is queued, charged like a summary; without the hours, the offer."""
    from types import SimpleNamespace
    import agent.bot_telebot as telebot_agent
    from app.i18n.messages import get_message
    from lib.telegram.telebot.types import ApiTelegramException
    documents, toasts, screens, statuses, deleted, feeds = [], [], [], [], [], []
    plans = {}

    def send_document(chat_id, document, **kwargs):
        documents.append(dict(kwargs, chat_id=chat_id, body=document.read().decode('utf-8')))

    def check(chat_id, needed):
        level = plans.get(chat_id, 0)
        limit = 30 * 3600 if level else 0
        return quota.Quota(limit > 0 and needed <= limit, limit, 0, needed, level)

    def feed_transcript(episode):
        feeds.append(episode['ref'])
        if episode['ref'] != 'feedy':
            return None
        ai.save_transcript('feedy', 'Words from the feed.', 'feed', 0.0, database=db)
        return transcript.Transcript('Words from the feed.', 'feed', 0.0, 0.0)

    def status_line(chat_id, text, reply_to=None):
        statuses.append((chat_id, text, reply_to))
        return 700 + len(statuses)

    saved = (telebot_agent.bot, module.notify, module.render_messages, module.status_line, module.message_deleter,
             module._feed_transcript, module.ai_quota.check, summary.enabled, ai.db_path, usage.db_path,
             module.offer_message)
    module.offer_message = lambda language_code, q, transcript=False: {  # its text: test_worker
        'type': 'text', 'text': 'offer transcript=%s limit=%s' % (transcript, q.limit)}
    telebot_agent.bot = SimpleNamespace(send_document=send_document)
    module.notify = lambda call, message, text, alert=False: toasts.append((text, alert))
    module.render_messages = lambda chat_id, messages, **kwargs: screens.append((chat_id, messages[0]))
    module.status_line = status_line
    module.message_deleter = lambda chat_id, message_id: deleted.append(message_id)
    module._feed_transcript = feed_transcript
    module.ai_quota.check = check
    summary.enabled = lambda: True
    ai.db_path = usage.db_path = db
    try:
        ai.remember_episode('ep9', 'https://cdn.example/show/ep9.mp3', 9, 'Q&amp;A: <b>why</b>/how?', 'Show',
                            database=db)
        ai.save_transcript('ep9', '[0:00] Hello there. [0:31] Second part. [1:02:15] Late.', 'whisper', 0.01,
                           database=db)
        tap = {'chat_id': 501, 'language_code': 'en', 'message': Tap({}, 55)}
        module.request_transcript(dict(tap, callback=Tap({'tp': 'trn', 'r': 'ep9', 'm': 4})))
        document = documents[-1]
        _assert(toasts[-1] == ('', False) and document['chat_id'] == 501 and document['reply_to_message_id'] == 4
                and document['allow_sending_without_reply'] is True,
                "under a summary: the file replies to the audio it names (sent anyway if the audio is gone)")
        _assert(document['visible_file_name'] == 'Q&A why how.txt',
                "the file is named after the episode, without characters a file name cannot hold")
        _assert(document['body'] == 'Show\nQ&A: why/how?\nhttps://cdn.example/show/ep9.mp3\n\n'
                '[0:00] Hello there.\n[0:31] Second part.\n[1:02:15] Late.\n',
                "the show, the title and the audio's link, then a line for each time mark")
        _assert(document['caption'] == '📄 <b>Show – Q&amp;A: why/how?</b>\nTranscribed automatically: it may have '
                'mistakes.' and document['parse_mode'] == 'HTML',
                "the caption names the episode (escaped) and says Whisper's text may have mistakes")
        _assert(feeds == [] and statuses == [] and usage.count_since(501, 'transcript', 0, db) == 1,
                "made before: free, the feed is not read, nothing queued; the file is in the ledger")
        module.request_transcript(dict(tap, callback=Tap({'tp': 'trn', 'r': 'ep9'})))
        _assert(documents[-1]['reply_to_message_id'] == 55,
                "under the audio: the button is on the audio, the file replies to it")

        ai.remember_episode('feedy', 'https://cdn.example/show/feedy.mp3', 9, 'Feedy', 'Show', 1800, database=db)
        module.request_transcript(dict(tap, chat_id=502, callback=Tap({'tp': 'trn', 'r': 'feedy'})))
        _assert(feeds == ['feedy'] and documents[-1]['chat_id'] == 502 and 'mistakes' not in documents[-1]['caption']
                and documents[-1]['body'].endswith('\n\nWords from the feed.\n') and statuses == [] and screens == [],
                "the feed publishes it: the file at once, even without a plan, and no Whisper claim")
        _assert(ai.transcript('feedy', db)['source'] == 'feed', "and it is cached for the next tap and for summaries")

        ai.remember_episode('long', 'https://cdn.example/show/long.mp3', 9, 'Long', 'Show', 2700, database=db)
        module.request_transcript(dict(tap, chat_id=503, callback=Tap({'tp': 'trn', 'r': 'long'})))
        _assert(statuses == [] and screens[-1] == (503, {'type': 'text', 'text': 'offer transcript=True limit=0'}),
                "no plan, nothing to read for free: the plans, said for transcripts; nothing queued")
        plans[504] = 3
        count = len(documents)
        module.request_transcript(dict(tap, chat_id=504, callback=Tap({'tp': 'trn', 'r': 'long'})))
        module.request_transcript(dict(tap, chat_id=504, callback=Tap({'tp': 'trn', 'r': 'long'})))
        c = sqlite3.connect(db)
        rows = c.execute("SELECT kind, seconds, reply_to, status_message, lang FROM ai_requests "
                         "WHERE chat_id=504").fetchall()
        c.close()
        _assert(len(documents) == count and rows == [('transcript', 2700, 55, 701, '')],
                "a plan with hours: only the transcript is queued, charged the episode's length, with its status line")
        _assert(statuses[0] == (504, get_message('transcriptStatusQueued', 'en'), 55) and deleted == [702],
                "the status line answers the audio; a second tap is the same request, its line goes")

        plans[505] = 1
        done, _ = ai.enqueue(505, 'long', 'original', 2700, db)
        ai.finish(done, 'done', database=db)
        module.request_transcript(dict(tap, chat_id=505, callback=Tap({'tp': 'trn', 'r': 'long'})))
        c = sqlite3.connect(db)
        charged = c.execute("SELECT seconds FROM ai_requests WHERE chat_id=505 AND kind='transcript'").fetchone()
        c.close()
        _assert(charged == (0,), "the chat paid for this audio with a summary: its transcript costs no more hours")

        # the better models: a paying chat gets Whisper's transcript made again, with speakers, within its hours
        saved_paid = (module.paid_models.speakers, module.paid_models.speakers_fit, module.paid_models.transcript_note)
        module.paid_models.speakers = lambda chat_id, database=None: chat_id in (506, 507, 508)
        # 508: past its hours of the paid model or its plan's budget
        module.paid_models.speakers_fit = lambda chat_id, seconds, database=None: chat_id in (506, 507)
        module.paid_models.transcript_note = lambda chat_id, source, lang, database=None, over_quota=False: (
            'OVER' if over_quota else '')
        try:
            plans[506] = 3
            count = len(documents)
            module.request_transcript(dict(tap, chat_id=506, callback=Tap({'tp': 'trn', 'r': 'ep9'})))
            c = sqlite3.connect(db)
            rows = c.execute("SELECT kind FROM ai_requests WHERE chat_id=506").fetchall()
            c.close()
            _assert(len(documents) == count and rows == [('transcript',)],
                    "a paying chat with them: Whisper's transcript is queued to be made again, not sent")
            plans[507] = 0
            module.request_transcript(dict(tap, chat_id=507, callback=Tap({'tp': 'trn', 'r': 'ep9'})))
            _assert(len(documents) == count + 1 and documents[-1]['chat_id'] == 507
                    and documents[-1]['caption'].endswith('\n\nOVER'),
                    "over its hours: Whisper's file, saying why")
            plans[508] = 3
            module.request_transcript(dict(tap, chat_id=508, callback=Tap({'tp': 'trn', 'r': 'ep9'})))
            _assert(documents[-1]['chat_id'] == 508 and documents[-1]['caption'].endswith('\n\nOVER'),
                    "past the paid model's hours or the budget: Whisper's file, saying why, nothing queued")
            module.request_transcript(dict(tap, chat_id=506, callback=Tap({'tp': 'trn', 'r': 'feedy'})))
            _assert(documents[-1]['chat_id'] == 506 and documents[-1]['body'].endswith('Words from the feed.\n'),
                    "the feed's transcript is the publisher's: a paying chat gets it as everyone does")
        finally:
            module.paid_models.speakers, module.paid_models.speakers_fit, module.paid_models.transcript_note = saved_paid

        count = len(documents)
        module.request_transcript(dict(tap, callback=Tap({'tp': 'trn', 'r': 'gone'})))
        _assert(len(documents) == count and toasts[-1][0] == get_message('screenOutdated', 'en'),
                "an unknown episode: an outdated screen")
        summary.enabled = lambda: False
        module.request_transcript(dict(tap, callback=Tap({'tp': 'trn', 'r': 'ep9'})))
        _assert(len(documents) == count and toasts[-1][0] == get_message('summaryUnavailable', 'en'),
                "AI off: a toast, nothing sent")
        summary.enabled = lambda: True

        name, body = module.transcript_file({'show': 'S', 'title': 'T', 'link': 'L'},
                                            ' '.join(['Sentence number %d is here.' % i for i in range(100)]))
        paragraphs = body.decode('utf-8').split('\n\n')[1:]
        _assert(name == 'T.txt' and len(paragraphs) > 3 and all(p.rstrip().endswith('.') for p in paragraphs)
                and all(len(p) < 2 * module.PARAGRAPH_CHARS for p in paragraphs),
                "a transcript without time marks comes in paragraphs broken after a sentence, not one long line")

        def flood(chat_id, document, **kwargs):
            raise ApiTelegramException('sendDocument', SimpleNamespace(status_code=429, reason='', text=''), {
                'error_code': 429, 'description': 'Too Many Requests: retry after 7'})
        telebot_agent.bot = SimpleNamespace(send_document=flood)
        before = usage.count_since(501, 'transcript', 0, db)
        module.request_transcript(dict(tap, callback=Tap({'tp': 'trn', 'r': 'ep9', 'm': 4})))  # does not raise
        _assert(usage.count_since(501, 'transcript', 0, db) == before, "a file Telegram did not take is not counted")
        _assert(len(json.dumps(summary.transcript_button_data('0123456789abcdef', 2 ** 31), separators=(',', ':')))
                <= 64, "the button's data fits Telegram's 64 bytes")
    finally:
        (telebot_agent.bot, module.notify, module.render_messages, module.status_line, module.message_deleter,
         module._feed_transcript, module.ai_quota.check, summary.enabled, ai.db_path, usage.db_path,
         module.offer_message) = saved


def main():
    test_transcripts()
    test_openrouter()
    with tempfile.TemporaryDirectory() as tmp:
        test_transcription(tmp)
        test_speakers(tmp)
        test_language(tmp)
        db = os.path.join(tmp, 'test.sqlite')
        test_queue_and_quota(db)
        test_budget(os.path.join(tmp, 'budget.sqlite'))
        test_auto(os.path.join(tmp, 'auto.sqlite'))
        test_hint(os.path.join(tmp, 'hint.sqlite'))
        test_worker(os.path.join(tmp, 'worker.sqlite'))
    print("all AI summary checks passed")


if __name__ == "__main__":
    main()
