# -*- coding: utf-8 -*-
"""Insert the admin nginx snippet include into the live site config.

Idempotent. Does not touch payment PHP locations.
"""
from __future__ import annotations

import sys

MARKER = "include /etc/nginx/snippets/yourcast-admin.conf;"
NEEDLE = "root /home/yourcast/server;"
INCLUDE_LINE = "    include /etc/nginx/snippets/yourcast-admin.conf;"


def ensure(path: str) -> bool:
    text = open(path, encoding="utf-8").read()
    if MARKER in text:
        print("nginx admin include already present")
        return False
    if NEEDLE not in text:
        raise SystemExit("did not find %r in %s" % (NEEDLE, path))
    updated = text.replace(NEEDLE, NEEDLE + "\n" + INCLUDE_LINE)
    open(path, "w", encoding="utf-8").write(updated)
    print("inserted admin include into", path)
    return True


if __name__ == "__main__":
    ensure(sys.argv[1] if len(sys.argv) > 1 else "/etc/nginx/sites-enabled/yourcast")
