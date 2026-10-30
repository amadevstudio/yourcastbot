# -*- coding: utf-8 -*-
"""The creator hears that the bot started: `python main.py`, the supervisor (a
deploy, supervisorctl restart, a server reboot).

A deploy is a clean stop and says nothing else on purpose (app/jobs/updater_resume.py:
#restarted is kept for a circle cut short), so the creator could not tell a deploy
went through. This says which commit runs and how the last run ended: the
updater's clean-stop mark is read, not taken (the updater takes it when it starts).
A role the supervisor restarts is main._announce_restart_if_needed.
Sent on the server only, off the start path: it never delays or fails a start.
Lock: python app/core/test_start_notice.py
"""
import os
import subprocess
import threading

from lib.tools.logger import logger

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _head_from_files(root):
    """The commit without git (it refuses a tree another user owns): .git/HEAD and its ref."""
    git = os.path.join(root, '.git')
    head = open(os.path.join(git, 'HEAD')).read().strip()
    if not head.startswith('ref: '):
        return head[:7]
    ref = head[5:]
    path = os.path.join(git, ref)
    if os.path.exists(path):
        return open(path).read().strip()[:7]
    for line in open(os.path.join(git, 'packed-refs')):
        if line.strip().endswith(' ' + ref):
            return line.split()[0][:7]
    return '?'


def version(root=_ROOT):
    """(short commit, its subject); ('?', '') when neither git nor .git can say."""
    try:
        out = subprocess.run(['git', 'log', '-1', '--format=%h%n%s%n%b'], cwd=root, capture_output=True,
                             text=True, timeout=5)
        lines = [line.strip() for line in out.stdout.strip().split('\n')]
        if lines and lines[0]:
            subject = lines[1] if len(lines) > 1 else ''
            body = [line for line in lines[2:] if line]
            if subject.startswith('Merge pull request') and body:
                subject = '%s (%s)' % (body[0], subject.split(' from ')[0][len('Merge pull request '):])
            return lines[0], subject
    except Exception:
        pass
    try:
        return _head_from_files(root), ''
    except Exception:
        return '?', ''


def start_text(sha, subject, roles, clean_stop) -> str:
    text = "🔄 Бот запускается: %s %s\nРоли: %s" % (sha, subject, ", ".join(roles))
    if clean_stop:
        return text + "\nПрошлый запуск остановлен штатно (деплой или рестарт)."
    return text + "\nШтатной остановки не было: сбой, kill или перезагрузка сервера."


def announce_start(roles, database=None, send=None, wait=False):
    """Tell the creator, in a thread of its own (wait: in this one, for tests)."""
    import config
    if not config.server and send is None:
        return

    try:
        # read now, before the updater child starts and takes the mark
        from app.jobs.updater_resume import CLEAN_STOP_KEY
        from db import runtime_kv
        clean = runtime_kv.get_kv(CLEAN_STOP_KEY, database=database) == "1"
    except Exception as e:
        logger.err("Start notice: clean stop unknown:", e)
        clean = False

    def run():
        try:
            sha, subject = version()
            sender = send
            if sender is None:
                from app.controller.builders.adminModule import send_message_to_creator as sender
            sender(start_text(sha, subject, roles, clean), level='info')
        except Exception as e:
            logger.err("Start notice:", e)

    if wait:
        run()
    else:
        threading.Thread(target=run, name="Start notice", daemon=True).start()
