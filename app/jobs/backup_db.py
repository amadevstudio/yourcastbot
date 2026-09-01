import datetime
import os
import subprocess
import time

from app.controller.builders.adminModule import send_message_to_creator
from config import work_dir, yandex_disk_backup_token
from lib.tools.logger import logger

# One successful backup per local calendar day, at this time.
# Restarts must not start another PUT.
BACKUP_HOUR = 0
BACKUP_MINUTE = 15
_LAST_SUCCESS = os.path.join(work_dir, 'backup', 'last_success')


def _today():
    return datetime.date.today().isoformat()


def _last_success_day():
    try:
        with open(_LAST_SUCCESS) as f:
            return f.read().strip()
    except OSError:
        return ''


def _seconds_until_next_run():
    now = datetime.datetime.now()
    today_slot = now.replace(
        hour=BACKUP_HOUR, minute=BACKUP_MINUTE, second=0, microsecond=0)
    if _last_success_day() == _today():
        target = today_slot + datetime.timedelta(days=1)
        return max(60.0, (target - now).total_seconds())
    if now < today_slot:
        return max(60.0, (today_slot - now).total_seconds())
    return 0.0


def main(interval=24 * 60):  # interval kept for call-site compat; schedule is daily
    script = os.path.join(work_dir, 'scripts', 'backup_to_yandex.sh')
    env = os.environ.copy()
    env['YANDEX_DISK_BACKUP_TOKEN'] = yandex_disk_backup_token

    fail_streak = 0
    fail_day = ''
    while True:
        wait = _seconds_until_next_run()
        if wait:
            nxt = datetime.datetime.now() + datetime.timedelta(seconds=wait)
            logger.log('Next Yandex backup at', nxt.strftime('%Y-%m-%d %H:%M'))
            time.sleep(wait)
            continue

        if fail_day != _today():
            fail_streak = 0
            fail_day = _today()

        result = subprocess.call([script, work_dir], env=env)
        if result != 0:
            fail_streak += 1
            logger.err('Yandex Disk backup failed, exit', result)
            send_message_to_creator(
                f'Yandex Disk backup failed (exit {result}). See backup/backup.log',
                level='error')
            # Same day's backup, not a second daily run.
            if fail_streak < 3:
                time.sleep(30 * 60)
            else:
                time.sleep(_seconds_until_next_run() or interval * 60)
        else:
            if fail_streak:
                send_message_to_creator('Yandex Disk backup succeeded', level='info')
            fail_streak = 0
            time.sleep(_seconds_until_next_run() or interval * 60)
