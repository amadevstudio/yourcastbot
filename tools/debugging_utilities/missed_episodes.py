# -*- coding: utf-8 -*-
"""Which episodes a chat missed in one hour. Read-only: DB and logs.

Run on the server from the repo root:

    venv/bin/python tools/debugging_utilities/missed_episodes.py <telegram_id> [YYYY-MM-DD HH]
    venv/bin/python tools/debugging_utilities/missed_episodes.py --audit
    venv/bin/python tools/debugging_utilities/missed_episodes.py --refetches [hours]
    venv/bin/python tools/debugging_utilities/missed_episodes.py --feed <channel_id>

The hour is server-local, like the logs. Without it the hour of the chat's
last nosub digest is used. The same reports are served read-only at
GET /api/diag/missed?tg=..., /api/diag/audit and /api/diag/refetches?hours=...;
see app/admin_web/diag.py.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.admin_web import diag  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    conn = diag.connect_ro()
    try:
        if sys.argv[1] == "--audit":
            diag.audit(conn)
            return
        if sys.argv[1] == "--feed":
            diag.feed_probe(conn, int(sys.argv[2]))
            return
        if sys.argv[1] == "--refetches":
            diag.refetches(conn, hours=int(sys.argv[2]) if len(sys.argv) > 2 else 24)
            return
        hour = diag.parse_hour(" ".join(sys.argv[2:4])) if len(sys.argv) >= 3 else None
        diag.report(conn, int(sys.argv[1]), hour=hour)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
