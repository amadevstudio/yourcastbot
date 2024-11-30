import subprocess
import time

from config import work_dir, yandex_disk_backup_token, yandex_disk_mail


def main(interval=24 * 60):  # minutes
    while True:
        subprocess.call(
            f"{work_dir}/scripts/backup_to_yandex.sh "
            + f"{yandex_disk_backup_token} {yandex_disk_mail} {work_dir}",
            shell=True)
        time.sleep(interval * 60)
