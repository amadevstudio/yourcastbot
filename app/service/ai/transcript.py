# -*- coding: utf-8 -*-
"""An episode's transcript: the one its feed publishes, else Groq Whisper.

1. The feed's <podcast:transcript> for the item with this enclosure: free.
2. Otherwise the audio is downloaded (through DiskBudget, as every episode
   file), turned into mono 16 kHz 24 kbps pieces of at most 30 minutes by
   ffmpeg (a 30-minute piece is ~5 MB, under Groq's upload limit; ffmpeg
   streams, it does not hold the episode in memory as pydub would) and each
   piece transcribed by whisper-large-v3-turbo, $0.04 per audio hour.
"""
import glob
import json
import os
import re
import subprocess
import tempfile
import time

from config import groq_api_key, work_dir
from lib.markup import telegram_html
from lib.requests.url import normalize_url
from lib.system.disk_budget import BudgetedDownload, DiskBudget

PODCAST_NS = '{https://podcastindex.org/namespace/1.0}'
# readable first: plain text, then subtitles, then JSON and HTML
TYPE_ORDER = ('text/plain', 'text/vtt', 'application/x-subrip', 'application/srt',
              'application/json', 'text/html')
GROQ_URL = 'https://api.groq.com/openai/v1/audio/transcriptions'
GROQ_MODEL = 'whisper-large-v3-turbo'
GROQ_USD_PER_HOUR = 0.04
GROQ_MIN_SECONDS = 10  # Groq bills at least 10 s a request
PIECE_SECONDS = 30 * 60
HTTP_TIMEOUT = 300

_TIMING = re.compile(r'^\s*(\d+\s*$|[\d:.,]+\s*-->\s*[\d:.,]+.*$|WEBVTT.*$|NOTE\b.*$)')
_VOICE = re.compile(r'<v\s+[^>]*>|</v>')


class TranscriptUnavailable(Exception):
    pass


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


def transcript_text(body: str, content_type: str = '') -> str:
    """Plain text of a transcript file: no timings, cue numbers or tags."""
    body = body.lstrip('﻿')
    stripped = body.lstrip()
    if 'json' in content_type or stripped.startswith('{'):
        try:
            data = json.loads(body)
            segments = data.get('segments') or []
            return ' '.join(str(s.get('body', '')).strip() for s in segments if s.get('body')).strip()
        except (ValueError, AttributeError):
            pass
    if 'html' in content_type or stripped.startswith('<'):
        return re.sub(r'\s+', ' ', telegram_html.plain_text(body)).strip()
    lines = []
    for line in body.splitlines():
        if _TIMING.match(line) or not line.strip():
            continue
        lines.append(_VOICE.sub('', line).strip())
    return re.sub(r'\s+', ' ', ' '.join(lines)).strip()


def from_feed(requester, channel_root, link) -> str | None:
    url = transcript_url(channel_root, link)
    if url is None:
        return None
    response = requester.get(url, timeout=60)
    if response is None or response.status_code != 200:
        return None
    text = transcript_text(response.text, response.headers.get('Content-Type', ''))
    return text or None


def split_audio(path, out_dir) -> list[str]:
    """Mono 16 kHz 24 kbps mp3 pieces of at most PIECE_SECONDS, in order."""
    pattern = os.path.join(out_dir, 'piece%03d.mp3')
    subprocess.run(
        ['nice', '-n', '10', 'ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', path,
         '-vn', '-ac', '1', '-ar', '16000', '-b:a', '24k',
         '-f', 'segment', '-segment_time', str(PIECE_SECONDS), pattern],
        check=True, timeout=1800)
    return sorted(glob.glob(os.path.join(out_dir, 'piece*.mp3')))


def groq_cost(seconds) -> float:
    return max(float(seconds), GROQ_MIN_SECONDS) / 3600 * GROQ_USD_PER_HOUR


def transcribe_piece(session, path) -> tuple[str, float]:
    """(text, audio seconds) of one piece."""
    with open(path, 'rb') as audio:
        response = session.post(
            GROQ_URL, headers={'Authorization': 'Bearer ' + groq_api_key},
            files={'file': (os.path.basename(path), audio, 'audio/mpeg')},
            data={'model': GROQ_MODEL, 'response_format': 'verbose_json'},
            timeout=HTTP_TIMEOUT)
    if response.status_code != 200:
        raise TranscriptUnavailable('groq %s: %s' % (response.status_code, response.text[:200]))
    data = response.json()
    return str(data.get('text') or '').strip(), float(data.get('duration') or 0)


def from_audio(requester, session, link, budget: DiskBudget | None = None) -> tuple[str, float]:
    """(text, cost USD) by Groq Whisper. The file and its pieces are deleted after."""
    if not groq_api_key:
        raise TranscriptUnavailable('no Groq key')
    budget = budget or DiskBudget(os.path.join(work_dir, 'records'))
    name = 'r_ai_%d.audio' % time.time_ns()
    download = BudgetedDownload(budget, os.path.join(work_dir, 'records', name))
    try:
        download.fetch(requester, link)
        with tempfile.TemporaryDirectory(dir=os.path.join(work_dir, 'records'), prefix='r_ai_') as pieces_dir:
            texts, cost = [], 0.0
            for piece in split_audio(download.path, pieces_dir):
                text, seconds = transcribe_piece(session, piece)
                texts.append(text)
                cost += groq_cost(seconds)
                os.remove(piece)
    finally:
        download.close()
    text = ' '.join(t for t in texts if t).strip()
    if not text:
        raise TranscriptUnavailable('empty transcript')
    return text, cost
