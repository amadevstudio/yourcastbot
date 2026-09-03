# -*- coding: utf-8 -*-
"""In-process supervisor: one command starts bot, updater, and jobs.

python main.py (no --role) stays the only start/deploy entry. Children are
separate processes so an updater/jobs crash does not take down receive.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from lib.tools.logger import logger

ROLES: tuple[str, ...] = ("bot", "updater", "jobs")

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAIN_PY = os.path.join(_REPO_ROOT, "main.py")
UPDATER_CRASH_FLAG = os.path.join(_REPO_ROOT, "db", "updater_crash.flag")

CommandForRole = Callable[[str], Sequence[str]]


def default_command_for_role(role: str) -> List[str]:
    return [sys.executable, MAIN_PY, "--role", role]


def mark_updater_crashed() -> None:
    os.makedirs(os.path.dirname(UPDATER_CRASH_FLAG), exist_ok=True)
    with open(UPDATER_CRASH_FLAG, "w") as fh:
        fh.write("1\n")


def consume_updater_crash_flag() -> bool:
    try:
        os.remove(UPDATER_CRASH_FLAG)
        return True
    except FileNotFoundError:
        return False


@dataclass
class ChildState:
    role: str
    proc: subprocess.Popen
    restarts: int = 0
    started_at: float = field(default_factory=time.time)
    backoff: float = 1.0


class ProcessSupervisor:
    def __init__(
            self,
            roles: Iterable[str] = ROLES,
            command_for_role: CommandForRole = default_command_for_role,
            poll_interval: float = 1.0,
            min_backoff: float = 1.0,
            max_backoff: float = 60.0,
            stable_after: float = 60.0,
            extra_env: Optional[Dict[str, str]] = None,
            on_child_exit: Optional[Callable[[str, int], None]] = None,
    ):
        self.roles = tuple(roles)
        self.command_for_role = command_for_role
        self.poll_interval = poll_interval
        self.min_backoff = min_backoff
        self.max_backoff = max_backoff
        self.stable_after = stable_after
        self.extra_env = extra_env or {}
        self.on_child_exit = on_child_exit
        self.children: Dict[str, ChildState] = {}
        self._stop = False

    def request_stop(self) -> None:
        self._stop = True

    def spawn(self, role: str, restarts: int = 0, backoff: float | None = None) -> ChildState:
        env = os.environ.copy()
        env.update(self.extra_env)
        env["YOURCAST_ROLE"] = role
        env["YOURCAST_RESTART_COUNT"] = str(restarts)
        cmd = list(self.command_for_role(role))
        logger.log("Supervisor starting", role, cmd)
        proc = subprocess.Popen(
            cmd,
            cwd=_REPO_ROOT,
            env=env,
            start_new_session=True,
        )
        wait = self.min_backoff if backoff is None else backoff
        state = ChildState(
            role=role, proc=proc, restarts=restarts,
            started_at=time.time(), backoff=wait)
        self.children[role] = state
        return state

    def start_all(self) -> None:
        for role in self.roles:
            self.spawn(role)

    def reap_and_restart(self) -> None:
        for role in list(self.roles):
            state = self.children.get(role)
            if state is None:
                if not self._stop:
                    self.spawn(role)
                continue
            code = state.proc.poll()
            if code is None:
                if time.time() - state.started_at >= self.stable_after:
                    state.backoff = self.min_backoff
                continue
            if self.on_child_exit is not None:
                self.on_child_exit(role, int(code))
            logger.err(
                "Supervisor: role exited", role, "code", code,
                "restarts", state.restarts)
            if role == "updater":
                mark_updater_crashed()
            if self._stop:
                continue
            delay = state.backoff
            deadline = time.time() + delay
            while time.time() < deadline and not self._stop:
                time.sleep(min(0.2, max(0.0, deadline - time.time())))
            if self._stop:
                continue
            next_backoff = min(self.max_backoff, max(self.min_backoff, delay * 2))
            self.spawn(role, restarts=state.restarts + 1, backoff=next_backoff)

    def terminate_all(self, timeout: float = 15.0) -> None:
        self._stop = True
        for state in self.children.values():
            if state.proc.poll() is None:
                try:
                    os.killpg(state.proc.pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError, OSError):
                    try:
                        state.proc.terminate()
                    except OSError:
                        pass
        deadline = time.time() + timeout
        for state in self.children.values():
            remaining = max(0.0, deadline - time.time())
            try:
                state.proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(state.proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    try:
                        state.proc.kill()
                    except OSError:
                        pass
                try:
                    state.proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass

    def run(self) -> None:
        self.start_all()
        try:
            while not self._stop:
                self.reap_and_restart()
                time.sleep(self.poll_interval)
        finally:
            self.terminate_all()


def run_supervisor(
        roles: Iterable[str] = ROLES,
        command_for_role: CommandForRole = default_command_for_role,
        **kwargs
) -> None:
    supervisor = ProcessSupervisor(
        roles=roles, command_for_role=command_for_role, **kwargs)

    def _handle(signum, _frame):
        logger.log("Supervisor received signal", signum, "stopping children")
        supervisor.request_stop()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)
    supervisor.run()
