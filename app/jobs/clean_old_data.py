import os
import re
import time

from config import work_dir


def main(interval=24 * 60):  # minutes
    while True:
        clean_old_records()
        clean_old_logs()
        time.sleep(interval * 60)


def clean_old_records():
    records_dir = work_dir + "/records"
    cleaner(records_dir, '^r.*')


def clean_old_logs():
    log_dir = work_dir + "/log"
    cleaner(log_dir, '.*\.log', 3)


def cleaner(path, pattern=None, older_than_days=1):
    now = time.time()
    print("Cleaning... ", path, pattern)
    for f in os.listdir(path):
        file_path = os.path.join(path, f)
        if re.match(pattern, f) is not None and os.path.isfile(file_path) \
                and os.stat(file_path).st_mtime < now - older_than_days * 86400:
            os.remove(file_path)
