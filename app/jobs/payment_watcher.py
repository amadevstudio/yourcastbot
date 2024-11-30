import datetime
import time

from app.service.payment.patreonPaymentModule import check_patreon_accounts


def patreon_watcher(update_time):
    while True:
        if update_time == 'per_hour':
            delta = datetime.timedelta(hours=1)
            now = datetime.datetime.now()
            next_hour = (now + delta).replace(microsecond=0, second=0, minute=0)
            wait_seconds = (next_hour - now).seconds
        else:
            wait_seconds = 3600
        time.sleep(wait_seconds)
        time.sleep(1)  # bcs of repeats in 1 second
        check_patreon_accounts()
