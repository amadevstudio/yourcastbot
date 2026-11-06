"""Collections: no pre-confirmation charges, immutable membership, atomic reservations and privacy."""
import concurrent.futures
from pathlib import Path
import sqlite3
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db import ai, voice


def main():
    with tempfile.TemporaryDirectory() as directory:
        database = str(Path(directory) / 'voice.sqlite')
        c = sqlite3.connect(database)
        c.executescript('CREATE TABLE channels (id INTEGER PRIMARY KEY, rss_link TEXT); '
                       'CREATE TABLE users (telegramId INTEGER, lang TEXT); '
                       "INSERT INTO users VALUES (901,'en'),(902,'ru');")
        c.close()
        refs = []
        for number in range(12):
            ref = 'v_' + ('%020x' % number)
            ai.remember_voice(ref, 901, 'Voice message', 60, database)
            batch, item, new = voice.stage(901, ref, 100 + number, 60, 1000, database)
            voice.ready(item, 60, database)
            refs.append(ref)
        assert len(voice.items(batch, database)) == 12
        assert ai.seconds_used(901, 0, database) == 0 and ai.claim(database) is None
        assert voice.batch(batch, 902, database) is None
        assert ai.accessible_episode(refs[0], 902, database) is None
        assert voice.quote(batch, 901, database)[2] == 720
        voice.select(batch, 901, 'summary', database)
        revision = voice.batch(batch, 901, database)['revision']
        try:
            voice.launch(batch, 901, revision, 'summary', 'each', 'original', 719, 720, 'Voice messages', database)
            raise AssertionError('overbooked quota')
        except voice.BatchChanged:
            pass
        assert voice.batch(batch, 901, database)['state'] == 'collecting'
        assert ai.seconds_used(901, 0, database) == 0
        # Two processes clicking the same preview reserve the entire batch once.
        def launch(_):
            return voice.launch(batch, 901, revision, 'summary', 'each', 'original', 720, 720, 'Voice messages', database)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            started = list(pool.map(launch, range(2)))
        assert sorted(new for _, new in started) == [False, True]
        assert started[0][0] == started[1][0] and ai.seconds_used(901, 0, database) == 720
        assert voice.batch(batch, 901, database)['state'] == 'frozen'
        next_batch, next_item, _ = voice.stage(901, 'v_' + 'f' * 20, 200, 60, 1000, database)
        assert next_batch != batch and len(voice.items(batch, database)) == 12
        # Claim order remains manual FIFO ahead of automatic episodes, and a retry retains its place.
        automatic, _ = ai.enqueue(902, 'automatic', 'en', 60, database, auto=True)
        first = ai.claim(database)
        assert first['ref'] == refs[0]
        assert not ai.retry_or_fail(first, database)
        assert ai.claim(database)['id'] == first['id']
        ai.finish(first['id'], 'done', database=database)
        ai.save_transcript(refs[0], 'Synthetic speech 1', 'whisper', 0, 60, database)
        for ref in refs[1:]:
            request = ai.claim(database)
            assert request['ref'] == ref
            ai.finish(request['id'], 'done', database=database)
            ai.save_transcript(ref, 'Synthetic speech', 'whisper', 0, 60, database)
        final = ai.claim(database)
        assert final['kind'] == voice.FINISH
        assert all(row['request_status'] == 'done' for row in voice.run_items(final['id'], database))
        ai.finish(final['id'], 'done', database=database)
        assert ai.claim(database)['id'] == automatic
        # The other representation does not reserve the audio twice.
        voice.select(batch, 901, 'transcript', database)
        assert voice.quote(batch, 901, database)[2] == 0
        voice.launch(batch, 901, revision, 'transcript', 'all', 'original', 720, 0, 'Voice messages', database)
        assert ai.seconds_used(901, 0, database) == 720
        # A click on an old preview must not include recordings added after it was shown.
        voice.ready(next_item, 60, database)
        voice.select(next_batch, 901, 'summary', database)
        old = voice.batch(next_batch, 901, database)['revision']
        _, extra, _ = voice.stage(901, 'v_' + 'e' * 20, 201, 60, 1000, database)
        voice.ready(extra, 60, database)
        try:
            voice.launch(next_batch, 901, old, 'summary', 'all', 'original', 5000, 60, 'Voice messages', database)
            raise AssertionError('stale preview launched')
        except voice.BatchChanged:
            pass
        assert voice.batch(next_batch, 901, database)['state'] == 'collecting'
        # Hourly cleanup expires drafts independently of completed private text; billing survives.
        voice.cleanup(database, now=time.time() + 2 * 86400)
        assert voice.batch(next_batch, 901, database) is None
        assert voice.batch(batch, 901, database)
        voice.cleanup(database, now=time.time() + 8 * 86400)
        ai.prune_voices(database, now=time.time() + 8 * 86400)
        assert voice.batch(batch, 901, database) is None and ai.transcript(refs[0], database) is None
        assert ai.seconds_used(901, 0, database) == 720
    print('all voice collection database checks passed')


if __name__ == '__main__':
    main()
