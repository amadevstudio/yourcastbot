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

    while True:
        result = subprocess.call([script, work_dir], env=env)
        if result != 0:
            logger.err('Yandex Disk backup failed, exit', result)
            send_message_to_creator(
                f'Yandex Disk backup failed (exit {result}). See backup/backup.log',
                level='error')
        time.sleep(interval * 60)
