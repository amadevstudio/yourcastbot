# -*- coding: utf-8 -*-
"""Copy hardened payment PHP into the landing tree. Does not touch bot code."""
from __future__ import annotations

import os
import shutil
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(REPO, "deploy", "payment")
DEFAULT_SERVER = "/home/yourcast/server"

FILES = (
    ("crypto-bot/listener.php", "payment/crypto-bot/listener.php"),
    ("robokassa/result.php", "payment/robokassa/result.php"),
)
JUNK = (
    "payment/crypto-bot/testfile.txt",
    "payment/robokassa/testfile.txt",
)


def install(server_root: str = DEFAULT_SERVER) -> int:
    payment_dir = os.path.join(server_root, "payment")
    if not os.path.isdir(payment_dir):
        print("skip payment php: no", payment_dir)
        return 0
    for rel_src, rel_dst in FILES:
        src = os.path.join(SRC, rel_src)
        dst = os.path.join(server_root, rel_dst)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        os.chmod(dst, 0o644)
        print("installed", dst)
    for rel in JUNK:
        path = os.path.join(server_root, rel)
        if os.path.isfile(path):
            os.remove(path)
            print("removed", path)
    return 0


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SERVER
    raise SystemExit(install(root))
