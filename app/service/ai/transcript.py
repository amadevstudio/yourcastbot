# -*- coding: utf-8 -*-
"""An episode's transcript: the one its feed publishes, else Whisper through OpenRouter.

1. The feed's <podcast:transcript> for the item with this enclosure: free.
2. Otherwise the audio is downloaded (through DiskBudget, as every episode
   file), turned into mono 16 kHz 24 kbps pieces of at most 10 minutes by
   ffmpeg (~2 MB each: under OpenRouter's 25 MB upload cap and well inside
   the 60 s a provider gets per request; ffmpeg streams, it does not hold
   the episode in memory as pydub would) and each piece transcribed by
   OpenRouter's /audio/transcriptions with config.ai_transcribe_model
   (e.g. openai/whisper-large-v3-turbo, ~$0.012 per audio hour). The cost is
   what OpenRouter bills for each piece.

The text carries time marks, "[12:40]", at most every MARK_SECONDS (Whisper's
segments, a VTT/SRT cue, a JSON segment's startTime or start, a time on a line
of its own in plain text): the summary and the answers to questions point to
the moment, and Telegram turns a time in a reply to the audio into a link that
plays from there. An HTML transcript, or plain text without times, has no
marks. A speaker the feed names (a VTT voice, "Speaker 2:" in front of a cue,
JSON speaker) starts a turn: a mark and the label once, so the file reads as a
dialog.

Whisper guesses the language from the first 30 s of each piece, and a guess on
an intro or music decodes the whole piece in the wrong language: it translates
(a Turkish lesson came back as broken English with loops, 2026-11-02). So the
language is given to it (`speech_language`): three 30 s samples from the middle
of the episode are asked what language they are; the feed's <language> when
two of them say it, else the samples' language when all three agree (a feed can
name the wrong one: a Persian show says "en"), else nothing (Whisper guesses,
as before). The samples cost a few hundredths of a cent.
"""
import base64
import glob
import json
import os
import re
import subprocess
import tempfile
import time
from collections import Counter
from typing import NamedTuple

from app.service.ai import openrouter
from config import ai_transcribe_model, work_dir
from lib.markup import telegram_html
from lib.requests.url import normalize_url
from lib.system.disk_budget import BudgetedDownload, DiskBudget
from lib.tools.logger import logger

PODCAST_NS = '{https://podcastindex.org/namespace/1.0}'
# readable first: plain text, then subtitles, then JSON and HTML
TYPE_ORDER = ('text/plain', 'text/vtt', 'application/x-subrip', 'application/srt',
              'application/json', 'text/html')
PIECE_SECONDS = 10 * 60
MARK_SECONDS = 30
# with speakers each piece after the first starts this early: a model numbers the speakers of each piece
# anew, and the words both pieces heard tell which is which
OVERLAP_SECONDS = 30
# diarization is each provider's own option; OpenRouter forwards only the serving provider's
SPEAKER_OPTIONS = {'xai': {'diarize': True}, 'elevenlabs': {'diarize': True}, 'deepgram': {'diarize': True},
                   'azure': {'diarization': {'enabled': True}}}
_SENTENCE_END = ('.', '!', '?', '…', '。', '؟')
LANGUAGE_SAMPLES = (0.3, 0.5, 0.7)  # where the language samples start, as parts of the episode
SAMPLE_SECONDS = 30
_LANGUAGE_CODE = re.compile(r'^[a-z]{2,3}$')
WHISPER, SPEAKERS = 'whisper', 'speakers'  # Transcript.source of what we made (SPEAKERS: a paid model)

_TIMING = re.compile(r'^\s*(\d+\s*$|[\d:.,]+\s*-->\s*[\d:.,]+.*$|WEBVTT.*$|NOTE\b.*$)')
_VOICE = re.compile(r'<v\s+[^>]*>|</v>')
_VOICE_NAME = re.compile(r'\s*<v\s+([^>]+)>')
_SPEAKER_LABEL = re.compile(r'\s*(speaker[ _]?\d+)\s*:\s*(.*)$', re.IGNORECASE)
# a line that is only a time: "00:01:11" before its paragraph (omny's TextWithTimestamps)
_STAMP_LINE = re.compile(r'^\s*\[?((?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d+)?)\]?\s*$')


class TranscriptUnavailable(Exception):
    pass


class Transcript(NamedTuple):
    text: str
    source: str  # 'feed', WHISPER or SPEAKERS (made with who speaks)
    cost_usd: float  # what making it cost
    seconds: float  # the audio Whisper measured, 0 for the feed's


def transcript_url(channel_root, link) -> str | None:
    """The feed's transcript for the item whose enclosure is `link`, the most readable type."""
    if channel_root is None or channel_root is False:
        return None
    wanted = normalize_url(link)
    for item in channel_root.iter('item'):
        enclosure = item.find('enclosure')
        if enclosure is None or normalize_url(enclosure.attrib.get('url', '')) != wanted:
            continue
        found = {}
        for node in item.iter(PODCAST_NS + 'transcript'):
            kind = (node.attrib.get('type') or '').split(';')[0].strip().lower()
            if node.attrib.get('url'):
                found.setdefault(kind, node.attrib['url'])
        for kind in TYPE_ORDER:
            if kind in found:
                return found[kind]
        return next(iter(found.values()), None)
    return None


def clock(seconds) -> str:
    """'7:05', '1:02:15'."""
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return '%d:%02d:%02d' % (hours, minutes, secs) if hours else '%d:%02d' % (minutes, secs)


def timed(parts) -> str:
    """[(start seconds or None, text[, speaker])] -> one text with a [m:ss] mark at most every
    MARK_SECONDS, and at every change of speaker: "[1:02] Speaker 2: ..." starts a turn, the same
    speaker's next parts go on without the label (a file reads as a dialog, one line a turn)."""
    out, last, speaker = [], None, None
    for start, text, *who in parts:
        text = str(text or '').strip()
        who = str(who[0] or '').strip() if who else ''
        if not text:
            continue
        turn = bool(who) and who != speaker
        if start is not None and (last is None or start - last >= MARK_SECONDS or turn):
            out.append('[%s]' % clock(start))
            last = start
        if turn:
            out.append(who + ':')
            speaker = who
        out.append(text)
    return re.sub(r'\s+', ' ', ' '.join(out)).strip()


def _speaker(line) -> tuple[str, str]:
    """(speaker, text) of a cue line: a VTT voice (<v Ann>) or "Speaker 2:" / "SPEAKER_01:" in
    front; '' when it names none. Only these: "Note: ..." is text."""
    voice = _VOICE_NAME.match(line)
    if voice:
        return voice.group(1).strip(), _VOICE.sub('', line[voice.end():])
    label = _SPEAKER_LABEL.match(_VOICE.sub('', line))
    if label:
        return label.group(1), label.group(2)
    return '', _VOICE.sub('', line)


def _stamp_seconds(stamp) -> float:
    total = 0.0
    for part in stamp.strip().replace(',', '.').split(':'):
        total = total * 60 + float(part)
    return total


def transcript_text(body: str, content_type: str = '') -> str:
    """Text of a transcript file with time marks: no cue numbers, timings or tags."""
    body = body.lstrip('﻿')
    stripped = body.lstrip()
    if 'json' in content_type or stripped.startswith(('{', '[')):
        try:
            data = json.loads(body)
            # the Podcast Index's {"segments": [{startTime, body, speaker}]}, or a bare list of
            # {start, text} (podigee)
            segments = data if isinstance(data, list) else data.get('segments') or []
            parts = []
            for s in segments:
                start = s.get('startTime', s.get('start'))
                parts.append((start if isinstance(start, (int, float)) else None,
                              s.get('body', s.get('text', '')), s.get('speaker')))
            return timed(parts)
        except (ValueError, AttributeError):
            pass
    if 'html' in content_type or stripped.startswith('<'):
        return re.sub(r'\s+', ' ', telegram_html.plain_text(body)).strip()
    parts, start = [], None
    for line in body.splitlines():
        if '-->' in line:
            try:
                start = _stamp_seconds(line.split('-->')[0])
            except ValueError:
                start = None
            continue
        stamp = _STAMP_LINE.match(line)
        if stamp:
            start = _stamp_seconds(stamp.group(1))
            continue
        if _TIMING.match(line) or not line.strip():
            continue
        speaker, text = _speaker(line)
        if text.strip():
            parts.append((start, text, speaker))
            start = None  # the cue's later lines are its own
    return timed(parts)


def from_feed(requester, channel_root, link, timeout=60) -> Transcript | None:
    url = transcript_url(channel_root, link)
    if url is None:
        return None
    response = requester.get(url, timeout=timeout)
    if response is None or response.status_code != 200:
        return None
    text = transcript_text(response.text, response.headers.get('Content-Type', ''))
    return Transcript(text, 'feed', 0.0, 0.0) if text else None


def episode_feed(episode, cached=False):
    """The channel element of the episode's feed (episode: db/ai.episode); None without a feed or when
    it cannot be read. `cached`: the feed's last copy (feed_cache), for a tap; the worker asks the host."""
    if not episode.get('feed_url'):
        return None
    from app.service.podcast.rss import get_rss_root_with_status
    root, _status, _validators = get_rss_root_with_status(episode['feed_url'], cached=cached)
    return None if root is False else root


def from_episode_feed(requester, episode, cached=False, timeout=60) -> Transcript | None:
    """The transcript the episode's feed publishes, None when it has none."""
    root = episode_feed(episode, cached)
    return from_feed(requester, root, episode['link'], timeout) if root is not None else None


def feed_language(channel_root) -> str:
    """The feed's <language> as a code ('en-US' -> 'en'); '' when it names none."""
    if channel_root is None or channel_root is False:
        return ''
    code = str(channel_root.findtext('language') or '').strip().lower().replace('_', '-').split('-')[0]
    return code if _LANGUAGE_CODE.match(code) else ''


def _duration(path) -> float:
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                           check=True, capture_output=True, text=True, timeout=60)
    return float(probe.stdout.strip())


def detect_language(session, path) -> tuple[str, float]:
    """(the language Whisper hears in a short sample, '' when it says none; USD)."""
    with open(path, 'rb') as audio:
        body = openrouter.post(
            'audio/transcriptions', session, files={'file': (os.path.basename(path), audio, 'audio/mpeg')},
            data={'model': ai_transcribe_model, 'response_format': 'verbose_json'})
    code = str(body.get('language') or '').strip().lower()
    return (code if _LANGUAGE_CODE.match(code) else ''), openrouter.cost(body)


def choose_language(heard, feed='') -> str | None:
    """What Whisper is told: the feed's language when two samples say it, else the samples' when they
    all agree, else None (it guesses)."""
    heard = [code for code in heard if code]
    if feed and heard.count(feed) >= 2:
        return feed
    if len(heard) == len(LANGUAGE_SAMPLES) and len(set(heard)) == 1:
        return heard[0]
    return None


def speech_language(session, path, out_dir, feed='') -> tuple[str | None, float]:
    """(the language to give Whisper for this audio, or None; what asking cost). Never raises: a sample
    that cannot be cut or asked counts as no answer."""
    heard, cost = [], 0.0
    try:
        duration = _duration(path)
    except (subprocess.SubprocessError, ValueError, OSError) as e:
        logger.warn('transcript language: no duration:', type(e).__name__, e)
        return None, 0.0
    if duration < SAMPLE_SECONDS * 3:
        return None, 0.0  # too short to sample (and a feed can be wrong): Whisper guesses
    for number, part in enumerate(LANGUAGE_SAMPLES):
        sample = os.path.join(out_dir, 'language%d.mp3' % number)
        try:
            subprocess.run(['nice', '-n', '10', 'ffmpeg', '-nostdin', '-loglevel', 'error', '-y',
                            '-ss', '%.1f' % (duration * part), '-t', str(SAMPLE_SECONDS), '-i', path,
                            '-vn', '-ac', '1', '-ar', '16000', '-b:a', '24k', sample], check=True, timeout=120)
            code, sample_cost = detect_language(session, sample)
            heard.append(code)
            cost += sample_cost
        except Exception as e:
            logger.warn('transcript language: sample', number, type(e).__name__, e)
            heard.append('')
        finally:
            if os.path.exists(sample):
                os.remove(sample)
    chosen = choose_language(heard, feed)
    logger.log('transcript language: feed %r, heard %s, chosen %r' % (feed, heard, chosen))
    return chosen, cost


def split_audio(path, out_dir) -> list[str]:
    """Mono 16 kHz 24 kbps mp3 pieces of at most PIECE_SECONDS, in order."""
    pattern = os.path.join(out_dir, 'piece%03d.mp3')
    subprocess.run(
        ['nice', '-n', '10', 'ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', path,
         '-vn', '-ac', '1', '-ar', '16000', '-b:a', '24k',
         '-f', 'segment', '-segment_time', str(PIECE_SECONDS), pattern],
        check=True, timeout=1800)
    return sorted(glob.glob(os.path.join(out_dir, 'piece*.mp3')))


def transcribe_piece(session, path, offset=0.0, language=None) -> Transcript:
    """One piece; `offset`: where it starts in the episode, for its time marks; `language`: what it is
    spoken in (speech_language), else Whisper guesses."""
    data = {'model': ai_transcribe_model, 'response_format': 'verbose_json', 'timestamp_granularities[]': 'segment'}
    if language:
        data['language'] = language
    with open(path, 'rb') as audio:
        body = openrouter.post(
            'audio/transcriptions', session,
            files={'file': (os.path.basename(path), audio, 'audio/mpeg')}, data=data)
    seconds = float((body.get('usage') or {}).get('seconds') or body.get('duration') or 0)
    segments = [s for s in body.get('segments') or [] if isinstance(s, dict)]
    if segments:
        text = timed((offset + float(s.get('start') or 0), s.get('text')) for s in segments)
    else:
        text = timed([(offset, body.get('text'))])
    return Transcript(text, WHISPER, openrouter.cost(body), seconds)


def split_overlapping(path, out_dir) -> list[tuple[str, float]]:
    """[(piece, where it starts)]: mono 16 kHz 24 kbps mp3 pieces up to each PIECE_SECONDS mark, every one
    after the first OVERLAP_SECONDS longer at its start."""
    whole = os.path.join(out_dir, 'whole.mp3')
    subprocess.run(
        ['nice', '-n', '10', 'ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', path,
         '-vn', '-ac', '1', '-ar', '16000', '-b:a', '24k', whole], check=True, timeout=1800)
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', whole],
                           check=True, capture_output=True, text=True, timeout=60)
    try:
        duration = float(probe.stdout.strip())
    except ValueError:
        raise TranscriptUnavailable('no duration: %r' % probe.stdout[:100])
    pieces, number = [], 0
    while number * PIECE_SECONDS < duration:
        start = max(0.0, number * PIECE_SECONDS - OVERLAP_SECONDS)
        piece = os.path.join(out_dir, 'piece%03d.mp3' % number)
        subprocess.run(['nice', '-n', '10', 'ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-ss', '%.3f' % start,
                        '-t', '%.3f' % ((number + 1) * PIECE_SECONDS - start), '-i', whole, '-c', 'copy', piece],
                       check=True, timeout=600)
        pieces.append((piece, start))
        number += 1
    os.remove(whole)
    return pieces


def transcribe_speaker_piece(session, path, offset, model) -> tuple[list, float, float]:
    """([(start in the episode, word, the piece's speaker number or None)], USD, seconds) of one piece."""
    with open(path, 'rb') as audio:
        data = base64.b64encode(audio.read()).decode()
    body = openrouter.post('audio/transcriptions', session, json={
        'model': model, 'response_format': 'verbose_json', 'timestamp_granularities': ['segment', 'word'],
        'input_audio': {'data': data, 'format': 'mp3'}, 'provider': {'options': SPEAKER_OPTIONS}})
    words = []
    for word in body.get('words') or []:
        if not isinstance(word, dict) or word.get('type') == 'spacing':
            continue
        try:
            words.append((offset + float(word.get('start') or 0), str(word.get('word') or word.get('text') or ''),
                          word.get('speaker')))
        except (TypeError, ValueError):
            continue
    if not any(text.strip() for _, text, _ in words):  # no words: the segments, still timed
        words = [(offset + float(s.get('start') or 0), str(s.get('text') or ''), s.get('speaker'))
                 for s in body.get('segments') or [] if isinstance(s, dict)]
    seconds = float((body.get('usage') or {}).get('seconds') or body.get('duration') or 0)
    return [w for w in words if w[1].strip()], openrouter.cost(body), seconds


def _same_word(text) -> str:
    return re.sub(r'\W+', '', text.lower())


def merge_speakers(pieces) -> list[tuple[float, str, int | None]]:
    """[(start, word, speaker numbered for the whole episode)] from [(piece start, its words)] in order.
    A piece's speaker is the one of the piece before who said the same words in their overlap (two such
    words at least); a speaker not heard there is a new one. The overlap's words come from the piece before."""
    out, known = [], 0
    for index, (offset, words) in enumerate(pieces):
        mapping = {}
        if index:
            boundary = offset + OVERLAP_SECONDS
            heard = [(start, _same_word(text), speaker) for start, text, speaker in out
                     if start >= offset - 1 and speaker is not None]
            votes = Counter()
            for start, text, speaker in words:
                if start >= boundary:
                    break
                key = _same_word(text)
                match = min((h for h in heard if h[1] == key and key and abs(h[0] - start) <= 1.0),
                            key=lambda h: abs(h[0] - start), default=None)
                if match is not None and speaker is not None:
                    votes[(speaker, match[2])] += 1
            for (speaker, episode_speaker), count in votes.most_common():
                if count >= 2 and speaker not in mapping and episode_speaker not in mapping.values():
                    mapping[speaker] = episode_speaker
            words = [w for w in words if w[0] >= boundary]
        for start, text, speaker in words:
            if speaker is not None and speaker not in mapping:
                mapping[speaker], known = known, known + 1
            out.append((start, text, None if speaker is None else mapping[speaker]))
    return out


def _joined(words) -> str:
    text = ''
    for word in words:
        if not text or word[:1].isspace() or text[-1:].isspace() or not re.match(r'\w', word):
            text += word
        else:
            text += ' ' + word
    return text


def speaker_text(words) -> str:
    """The text of merge_speakers' words: a turn for each change of speaker ("Speaker 2: ..."), marks at
    the start of a sentence at most every MARK_SECONDS (a mark in mid-sentence reads badly)."""
    parts, current, ended = [], None, True
    for start, text, speaker in words:
        label = 'Speaker %d' % (speaker + 1) if speaker is not None else ''
        if current is None or label != current[2] or ended:
            current = [start, [], label]
            parts.append(current)
        current[1].append(text)
        ended = text.rstrip().endswith(_SENTENCE_END)
    return timed((start, _joined(texts), label) for start, texts, label in parts)


def from_audio(requester, session, link, budget: DiskBudget | None = None, progress=None,
               speakers_model=None, feed_language='') -> Transcript:
    """Whisper on the episode's audio, told its language (speech_language, `feed_language` the feed's
    word for it), or with `speakers_model` (a model that labels speakers, the paid one) the text with who
    speaks. The file and its pieces are deleted after.
    `progress(stage, done, total)`: 'download', then 'transcribe' before each piece."""
    progress = progress or (lambda *args: None)
    budget = budget or DiskBudget(os.path.join(work_dir, 'records'))
    name = 'r_ai_%d.audio' % time.time_ns()
    download = BudgetedDownload(budget, os.path.join(work_dir, 'records', name))
    try:
        progress('download', 0, 0)
        download.fetch(requester, link)
        with tempfile.TemporaryDirectory(dir=os.path.join(work_dir, 'records'), prefix='r_ai_') as pieces_dir:
            if speakers_model:
                return _with_speakers(session, download.path, pieces_dir, speakers_model, progress)
            language, language_cost = speech_language(session, download.path, pieces_dir, feed_language)
            pieces, offset = [], 0.0
            paths = split_audio(download.path, pieces_dir)
            for number, path in enumerate(paths, 1):
                progress('transcribe', number, len(paths))
                pieces.append(transcribe_piece(session, path, offset, language))
                offset += pieces[-1].seconds or PIECE_SECONDS
                os.remove(path)
    finally:
        download.close()
    text = ' '.join(piece.text for piece in pieces if piece.text).strip()
    if not text:
        raise TranscriptUnavailable('empty transcript')
    return Transcript(text, WHISPER, language_cost + sum(piece.cost_usd for piece in pieces),
                      sum(piece.seconds for piece in pieces))


def _with_speakers(session, path, pieces_dir, model, progress) -> Transcript:
    pieces, cost, seconds = [], 0.0, 0.0
    split = split_overlapping(path, pieces_dir)
    for number, (piece, offset) in enumerate(split, 1):
        progress('transcribe', number, len(split))
        words, piece_cost, piece_seconds = transcribe_speaker_piece(session, piece, offset, model)
        pieces.append((offset, words))
        cost += piece_cost
        # the audio is the episode's once: an overlap is billed, not counted against the plan's hours
        seconds += max(0.0, piece_seconds - (OVERLAP_SECONDS if offset else 0.0))
        os.remove(piece)
    text = speaker_text(merge_speakers(pieces))
    if not text:
        raise TranscriptUnavailable('empty transcript')
    return Transcript(text, SPEAKERS, cost, seconds)
