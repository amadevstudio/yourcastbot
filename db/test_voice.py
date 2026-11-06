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
        # Reserved, but nothing is claimable until the audio is here; the final waits for every recording.
        assert ai.claim(database) is None and ai.seconds_used(901, 0, database) == 720
        waiting = voice.uploading(901, database)
        assert [w['ref'] for w in waiting] == refs and voice.uploading_chats(database) == [901]
        assert voice.progress(batch, database) == {'uploading': 12}
        for w in waiting[:-1]:
            voice.release(w['request_id'], 60, 60, database)
        assert voice.settle(database) == [] and voice.progress(batch, database) == {'uploading': 1, 'pending': 11}
        voice.release(waiting[-1]['request_id'], 60, 60, database)
        settled = voice.settle(database)
        assert len(settled) == 1 and not settled[0]['failed'] and settled[0]['batch'] == batch
        assert voice.settle(database) == [] and ai.seconds_used(901, 0, database) == 720
        assert voice.batch_of_request(waiting[0]['request_id'], database) == batch
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
        for w in voice.uploading(901, database):
            voice.release(w['request_id'], database=database)  # shared audio: free
        assert voice.settle(database)[0]['batch'] == batch
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
        # A recording longer than claimed is charged what it measured; a shorter one gives hours back.
        def start(ref, message, output, mode, expected):
            _, item, _ = voice.stage(902, ref, message, 60, 1000, database)
            voice.ready(item, 60, database)
            voice.select(voice.stage(902, ref, message, 60, 1000, database)[0], 902, output, database)
            ref_batch = voice.stage(902, ref, message, 60, 1000, database)[0]
            return ref_batch, voice.launch(ref_batch, 902, voice.batch(ref_batch, 902, database)['revision'], output,
                                           mode, 'original', 100000, expected, 'Voice messages', database)
        base = ai.seconds_used(902, 0, database)  # the automatic request above
        mine, _ = start('v_' + 'd' * 20, 300, 'transcript', 'each', 60)
        assert ai.seconds_used(902, 0, database) == base + 60
        only = voice.uploading(902, database)[0]
        voice.release(only['request_id'], 90, 90, database)
        assert ai.seconds_used(902, 0, database) == base + 90 and voice.items(mine, database)[0]['seconds'] == 90
        assert voice.settle(database)[0]['failed'] is False
        short = voice.uploading(902, database)
        assert not short
        # A recording that cannot be fetched fails its run and gives its hours back; nothing starts.
        c = ai.connect(database)
        c.execute("UPDATE ai_requests SET status='done' WHERE status IN ('pending','working')")
        c.execute("UPDATE voice_batches SET state='collecting' WHERE ref=?", (mine,))
        c.commit()
        c.close()
        _, item, _ = voice.stage(902, 'v_' + 'c' * 20, 301, 60, 1000, database)
        voice.ready(item, 60, database)
        voice.select(mine, 902, 'transcript', database)
        voice.launch(mine, 902, voice.batch(mine, 902, database)['revision'], 'transcript', 'all', 'original', 100000, 150, 'Voice messages', database)
        reserved = ai.seconds_used(902, 0, database)
        for w in voice.uploading(902, database):
            voice.fail_child(w['request_id'], database)
        assert ai.seconds_used(902, 0, database) < reserved
        failed = voice.settle(database)
        assert failed and failed[0]['failed'] and not voice.uploading_chats(database)
        # Audio that never comes is given up after an hour, with its hours.
        c = ai.connect(database)
        c.execute("UPDATE ai_requests SET status='done' WHERE status IN ('pending','working')")
        c.execute("UPDATE voice_batches SET state='collecting' WHERE ref=?", (mine,))
        c.commit()
        c.close()
        _, item, _ = voice.stage(902, 'v_' + 'b' * 20, 302, 60, 1000, database)
        voice.ready(item, 60, database)
        voice.select(mine, 902, 'summary', database)
        voice.launch(mine, 902, voice.batch(mine, 902, database)['revision'], 'summary', 'each', 'original', 100000, 600, 'Voice messages', database)
        reserved = ai.seconds_used(902, 0, database)
        assert voice.uploading_chats(database) == [902]
        voice.settle(database, now=time.time() + 4000)
        assert ai.seconds_used(902, 0, database) < reserved and not voice.uploading_chats(database)
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
