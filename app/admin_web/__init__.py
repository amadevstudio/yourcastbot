# -*- coding: utf-8 -*-
"""HTTP admin panel (FastAPI) and mailing jobs.

The PHP pages under /home/yourcast/server were a blocking shell_exec around
scripts/send_message.py. This package is the replacement: a localhost API
plus a jobs-role worker. Rec/circle/send pools are not used for broadcasts.
"""
