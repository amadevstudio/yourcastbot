import os
import subprocess
import time

from app.controller.builders.adminModule import send_message_to_creator
from config import work_dir, yandex_disk_backup_token
from lib.tools.logger import logger


def main(interval=24 * 60):  # minutes
    script = os.path.join(work_dir, 'scripts', 'backup_to_yandex.sh')
    env = os.environ.copy()
    env['YANDEX_DISK_BACKUP_TOKEN'] = yandex_disk_backup_token

    fail_streak = 0
    while True:
        result = subprocess.call([script, work_dir], env=env)
        if result != 0:
            fail_streak += 1
            logger.err('Yandex Disk backup failed, exit', result)
            send_message_to_creator(
                f'Yandex Disk backup failed (exit {result}). See backup/backup.log',
                level='error')
            # A 135MB PUT can time out; retry soon instead of waiting a full day.
            time.sleep(30 * 60 if fail_streak < 3 else interval * 60)
        else:
            if fail_streak:
                send_message_to_creator('Yandex Disk backup succeeded', level='info')
            fail_streak = 0
            time.sleep(interval * 60)
