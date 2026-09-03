# -*- coding: utf-8 -*-
"""Process supervisor: one parent, independent children.

Uses dummy child processes only — does not start Telegram.
Run from the repo root: python app/core/test_process_supervisor.py
"""
import os
import sys
import tempfile
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.core.process_supervisor import (  # noqa: E402
    ProcessSupervisor, consume_updater_crash_flag, mark_updater_crashed)
from lib.python.file_lock import InterprocessLock  # noqa: E402

_CHILD = r"""
import os, sys, time
role = os.environ["YOURCAST_ROLE"]
path = os.environ["TEST_DIR"]
with open(os.path.join(path, role + ".started"), "a") as fh:
    fh.write(str(os.getpid()) + "\n")
if role == "crashy":
    lines = open(os.path.join(path, "crashy.started")).read().strip().splitlines()
    if len(lines) < 2:
        time.sleep(0.05)
        sys.exit(3)
time.sleep(60)
"""


def _wait(pred, timeout, label):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return
        time.sleep(0.05)
    raise AssertionError("timeout waiting for %s" % label)


def _pids(path, role):
    started = os.path.join(path, role + ".started")
    if not os.path.exists(started):
        return []
    return [int(x) for x in open(started).read().split() if x.strip()]


def test_restarts_only_the_crashed_role():
    tmpdir = tempfile.mkdtemp(prefix="yourcast_supervisor_")
    extra = {"TEST_DIR": tmpdir}

    def command_for_role(_role):
        return [sys.executable, "-c", _CHILD]

    supervisor = ProcessSupervisor(
        roles=("stable", "crashy"),
        command_for_role=command_for_role,
        poll_interval=0.05,
        min_backoff=0.05,
        max_backoff=0.2,
        stable_after=30,
        extra_env=extra,
    )
    thread = threading.Thread(target=supervisor.run, daemon=True)
    thread.start()
    try:
        _wait(lambda: len(_pids(tmpdir, "stable")) >= 1, 5, "stable start")
        _wait(lambda: len(_pids(tmpdir, "crashy")) >= 1, 5, "crashy start")
        stable_pid = _pids(tmpdir, "stable")[0]
        _wait(lambda: len(_pids(tmpdir, "crashy")) >= 2, 8, "crashy restart")
        time.sleep(0.3)
        assert _pids(tmpdir, "stable") == [stable_pid], (
            "stable role was restarted: %r" % _pids(tmpdir, "stable"))
        crashy = supervisor.children["crashy"].proc
        stable = supervisor.children["stable"].proc
        assert crashy.poll() is None
        assert stable.poll() is None
        assert crashy.pid != stable_pid
        print("ok  crashed role restarted, stable pid unchanged:", stable_pid)
    finally:
        supervisor.request_stop()
        supervisor.terminate_all(timeout=5)
        thread.join(timeout=6)


def test_stop_terminates_children():
    tmpdir = tempfile.mkdtemp(prefix="yourcast_supervisor_stop_")

    def command_for_role(_role):
        return [sys.executable, "-c", _CHILD]

    supervisor = ProcessSupervisor(
        roles=("stable",),
        command_for_role=command_for_role,
        poll_interval=0.05,
        extra_env={"TEST_DIR": tmpdir},
    )
    supervisor.start_all()
    _wait(lambda: len(_pids(tmpdir, "stable")) >= 1, 5, "stable start")
    proc = supervisor.children["stable"].proc
    supervisor.terminate_all(timeout=5)
    _wait(lambda: proc.poll() is not None, 5, "child exit after stop")
    print("ok  terminate_all stops children, code", proc.poll())


def test_updater_crash_flag():
    if os.path.exists(
            os.path.join(_ROOT, "db", "updater_crash.flag")):
        consume_updater_crash_flag()
    assert consume_updater_crash_flag() is False
    mark_updater_crashed()
    assert consume_updater_crash_flag() is True
    assert consume_updater_crash_flag() is False
    print("ok  updater crash flag is one-shot")


def test_interprocess_lock_nested_and_multiprocess():
    tmpdir = tempfile.mkdtemp(prefix="yourcast_lock_")
    lock_path = os.path.join(tmpdir, "x.lock")
    counter_path = os.path.join(tmpdir, "counter")
    open(counter_path, "w").write("0")
    lock = InterprocessLock(lock_path)
    with lock:
        with lock:
            pass
    print("ok  nested lock")

    worker = r"""
import os, sys, time
sys.path.insert(0, os.environ["ROOT"])
from lib.python.file_lock import InterprocessLock
lock = InterprocessLock(os.environ["LOCK"])
counter = os.environ["COUNTER"]
for _ in range(20):
    with lock:
        n = int(open(counter).read() or "0")
        time.sleep(0.001)
        open(counter, "w").write(str(n + 1))
"""
    env = os.environ.copy()
    env["ROOT"] = _ROOT
    env["LOCK"] = lock_path
    env["COUNTER"] = counter_path
    procs = []
    import subprocess
    for _ in range(3):
        procs.append(subprocess.Popen(
            [sys.executable, "-c", worker], env=env))
    for proc in procs:
        assert proc.wait(timeout=10) == 0
    total = int(open(counter_path).read())
    assert total == 60, total
    print("ok  interprocess lock counter", total)


def main():
    test_updater_crash_flag()
    test_interprocess_lock_nested_and_multiprocess()
    test_restarts_only_the_crashed_role()
    test_stop_terminates_children()
    print("all process supervisor checks passed")


if __name__ == "__main__":
    main()
