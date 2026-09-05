import os
import re
import time

from config import work_dir
from lib.tools.logger import logger


def main(interval=24 * 60):  # minutes
    while True:
        for step in (clean_old_records, clean_old_logs, clean_old_outbox):
            try:
                step()
            except Exception as e:
                logger.err("clean_old_data/%s:" % step.__name__, e)
        time.sleep(interval * 60)


def clean_old_records():
    records_dir = work_dir + "/records"
    cleaner(records_dir, '^r.*')


def clean_old_logs():
    log_dir = work_dir + "/log"
    cleaner(log_dir, '.*\.log', 3)


def clean_old_outbox(database=None):
    """Drop old done/failed outbox rows. Does not VACUUM."""
    from app.core.sender import outbox
    from app.jobs import digest_outbox
    counts = outbox.purge_old(database=database)
    digest_counts = digest_outbox.purge_old(database=database)
    logger.log(
        "send_outbox purge done=%s failed=%s digest done=%s failed=%s" % (
            counts['done'], counts['failed'],
            digest_counts['done'], digest_counts['failed']))
    return counts


def cleaner(path, pattern=None, older_than_days=1):
    now = time.time()
    print("Cleaning... ", path, pattern)
    if not os.path.isdir(path):
        return
    for f in os.listdir(path):
        file_path = os.path.join(path, f)
        if re.match(pattern, f) is not None and os.path.isfile(file_path) \
                and os.stat(file_path).st_mtime < now - older_than_days * 86400:
            os.remove(file_path)
