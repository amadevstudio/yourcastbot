"""A consistent copy of a live SQLite database, for the nightly backup.

The bot keeps writing while the backup runs, and the database is in WAL
mode: the newest changes sit in `-wal` until a checkpoint moves them into
the main file. `tar` over the live files reads them at different moments
("file changed as we read it"), so an archive could hold a main file and a
WAL that do not match. SQLite's backup API copies the database as one read
transaction (WAL included) into a single self-contained file; the copy is
checked before it may be archived.

Usage: python3 scripts/db_snapshot.py SRC.db DST.db
Python 3.8+ standard library only: the backup script runs it with the
system python3, not the bot's venv.
"""
import os
import sqlite3
import sys


class SnapshotError(Exception):
    pass


def snapshot(src, dst):
    """Copy src into dst (replaced) and check the copy. Returns dst's size."""
    if os.path.exists(dst):
        os.remove(dst)
    try:
        # mode=ro: a missing source fails here instead of becoming an empty db.
        source = sqlite3.connect('file:%s?mode=ro' % src, uri=True, timeout=60)
    except sqlite3.Error as e:
        raise SnapshotError('cannot open %s: %s' % (src, e))
    target = sqlite3.connect(dst)
    try:
        # pages=-1: the whole database in one step, one read transaction.
        source.backup(target, pages=-1)
        target.execute('PRAGMA journal_mode=DELETE')
        result = [row[0] for row in target.execute('PRAGMA integrity_check')]
    except sqlite3.Error as e:
        raise SnapshotError('copy of %s failed: %s' % (src, e))
    finally:
        target.close()
        source.close()
    if result != ['ok']:
        raise SnapshotError('copy of %s is not intact: %s' % (src, '; '.join(result[:5])))
    return os.path.getsize(dst)


def main(argv):
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print('usage: db_snapshot.py SRC.db DST.db', file=sys.stderr)
        return 2
    src, dst = argv[1], argv[2]
    try:
        size = snapshot(src, dst)
    except SnapshotError as e:
        if os.path.exists(dst):
            os.remove(dst)
        print(e, file=sys.stderr)
        return 1
    print('%s: %d bytes, integrity ok' % (os.path.basename(dst), size))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
