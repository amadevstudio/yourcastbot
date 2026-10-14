# -*- coding: utf-8 -*-
"""An ERR names where the exception was raised, not only where it was caught.

A handler that catches a whole route's failure used to log only its own line
(telebotAnswerer.py:145), so "'NoneType' object has no attribute 'get'"
could not be traced to the screen that raised it.

Run from the repo root: python lib/tools/test_logger_place.py
"""
import contextlib
import io
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config  # noqa: E402
from lib.tools.logger import Logger  # noqa: E402


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _raises():
    return None.get('x')


def _logged(fn):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            fn()
        except Exception as e:
            Logger().err("route:", e)
    return out.getvalue()


def main():
    config.server = False
    line = _logged(_raises)
    _assert("test_logger_place.py:" in line and " > test_logger_place.py:" in line,
            "caught and raised places are both named: %r" % line.strip())
    raised_at = line.split(" > ")[1].split()[0]
    _assert(raised_at == "test_logger_place.py:%d" % (_raises.__code__.co_firstlineno + 1),
            "the raised place is the line of the bad call")

    print("all logger place checks passed")


if __name__ == "__main__":
    main()
