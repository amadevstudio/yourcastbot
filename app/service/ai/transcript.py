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
"""
import glob
import json
import os
import re
import subprocess
import tempfile
import time
from typing import NamedTuple

from app.service.ai import openrouter
from config import ai_transcribe_model, work_dir
from lib.markup import telegram_html
from lib.requests.url import normalize_url
from lib.system.disk_budget import BudgetedDownload, DiskBudget

PODCAST_NS = '{https://podcastindex.org/namespace/1.0}'
# readable first: plain text, then subtitles, then JSON and HTML
TYPE_ORDER = ('text/plain', 'text/vtt', 'application/x-subrip', 'application/srt',
              'application/json', 'text/html')
PIECE_SECONDS = 10 * 60
MARK_SECONDS = 30

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
    source: str  # 'feed' or 'whisper'
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


def from_episode_feed(requester, episode, cached=False, timeout=60) -> Transcript | None:
    """The transcript the episode's feed publishes (episode: db/ai.episode), None when it has none.
    `cached`: the feed's last copy (feed_cache), for a tap; the worker asks the host."""
    if not episode.get('feed_url'):
        return None
    from app.service.podcast.rss import get_rss_root_with_status
    root, _status, _validators = get_rss_root_with_status(episode['feed_url'], cached=cached)
    return from_feed(requester, root, episode['link'], timeout) if root is not False else None


def split_audio(path, out_dir) -> list[str]:
    """Mono 16 kHz 24 kbps mp3 pieces of at most PIECE_SECONDS, in order."""
    pattern = os.path.join(out_dir, 'piece%03d.mp3')
    subprocess.run(
        ['nice', '-n', '10', 'ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', path,
         '-vn', '-ac', '1', '-ar', '16000', '-b:a', '24k',
         '-f', 'segment', '-segment_time', str(PIECE_SECONDS), pattern],
        check=True, timeout=1800)
    return sorted(glob.glob(os.path.join(out_dir, 'piece*.mp3')))


def transcribe_piece(session, path, offset=0.0) -> Transcript:
    """One piece; `offset`: where it starts in the episode, for its time marks."""
    with open(path, 'rb') as audio:
        body = openrouter.post(
            'audio/transcriptions', session,
            files={'file': (os.path.basename(path), audio, 'audio/mpeg')},
            data={'model': ai_transcribe_model, 'response_format': 'verbose_json',
                  'timestamp_granularities[]': 'segment'})
    seconds = float((body.get('usage') or {}).get('seconds') or body.get('duration') or 0)
    segments = [s for s in body.get('segments') or [] if isinstance(s, dict)]
    if segments:
        text = timed((offset + float(s.get('start') or 0), s.get('text')) for s in segments)
    else:
        text = timed([(offset, body.get('text'))])
    return Transcript(text, 'whisper', openrouter.cost(body), seconds)


def from_audio(requester, session, link, budget: DiskBudget | None = None, progress=None) -> Transcript:
    """Whisper on the episode's audio. The file and its pieces are deleted after.
    `progress(stage, done, total)`: 'download', then 'transcribe' before each piece."""
    progress = progress or (lambda *args: None)
    budget = budget or DiskBudget(os.path.join(work_dir, 'records'))
    name = 'r_ai_%d.audio' % time.time_ns()
    download = BudgetedDownload(budget, os.path.join(work_dir, 'records', name))
    try:
        progress('download', 0, 0)
        download.fetch(requester, link)
        with tempfile.TemporaryDirectory(dir=os.path.join(work_dir, 'records'), prefix='r_ai_') as pieces_dir:
            pieces, offset = [], 0.0
            paths = split_audio(download.path, pieces_dir)
            for number, path in enumerate(paths, 1):
                progress('transcribe', number, len(paths))
                pieces.append(transcribe_piece(session, path, offset))
                offset += pieces[-1].seconds or PIECE_SECONDS
                os.remove(path)
    finally:
        download.close()
    text = ' '.join(piece.text for piece in pieces if piece.text).strip()
    if not text:
        raise TranscriptUnavailable('empty transcript')
    return Transcript(text, 'whisper', sum(piece.cost_usd for piece in pieces),
                      sum(piece.seconds for piece in pieces))
