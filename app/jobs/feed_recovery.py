"""Repair feed URLs outside the RSS circle and all send worker pools."""
import time

from db import feed_recovery as jobs
from lib.requests.requesterModule import Requester
from lib.requests.url import normalize_url
from lib.tools.logger import Logger

logger = Logger(file='feed_recovery')
requester = Requester(attempts=0, total_attempts=0)
IDLE_SECONDS = 10


def lookup_url(itunes_id):
    response = requester.get(
        'https://itunes.apple.com/lookup',
        params={'id': itunes_id, 'entity': 'podcast'}, timeout=(5, 15), verify=True)
    response.raise_for_status()
    for item in response.json().get('results', []):
        if str(item.get('collectionId')) == str(itunes_id) and item.get('feedUrl'):
            url = normalize_url(item['feedUrl'])
            if url.startswith(('http://', 'https://')):
                return url
    return None


def valid_feed(url):
    from app.service.podcast.rss import get_rss_root_with_status
    root, status, _validators = get_rss_root_with_status(url)
    return status == 'ok' and root is not False and any(
        item.find('enclosure') is not None and item.find('enclosure').get('url')
        for item in root.findall('item'))


def process_one(database=None, lookup=lookup_url, validate=valid_feed, now=None):
    job = jobs.claim(database=database, now=now)
    if job is None:
        return False
    channel = jobs.channel(job['channel_id'], database=database)
    candidate = None
    result = 'unavailable'
    try:
        if channel is not None:
            if channel['itunes_id']:
                try:
                    candidate = lookup(channel['itunes_id'])
                except Exception as e:
                    logger.warn('catalog lookup failed for channel', job['channel_id'], type(e).__name__)
                    result = 'catalog_unavailable'
            candidates = list(dict.fromkeys(u for u in (candidate, channel['rss_link']) if u))
            candidate = None
            for url in candidates:
                try:
                    if validate(url):
                        candidate = url
                        break
                except Exception as e:
                    logger.warn('feed validation failed for channel', job['channel_id'], type(e).__name__)
    except Exception as e:
        candidate = None
        logger.warn('feed validation failed for channel', job['channel_id'], type(e).__name__)
    recovered = jobs.finish(
        job, channel, new_url=candidate, result=result, database=database, now=now)
    logger.log('feed recovery channel', job['channel_id'],
               'result', 'recovered' if recovered else result)
    return True


def recovery_watcher():
    jobs.seed_legacy()
    while True:
        try:
            process_one()
        except Exception as e:
            logger.err('feed recovery job failed:', e)
        time.sleep(IDLE_SECONDS)


def send_pause_notice(database=None):
    from app.core.sender.outbox import OutboxRetryableError, flood_wait_seconds
    from app.i18n.messages import get_message
    from lib.markup import telegram_html
    from lib.telegram.general.message_master import outer_sender
    notice = jobs.next_notice(database=database)
    if notice is None:
        return False
    try:
        outer_sender(notice['user_telegram_id'], [{
            'type': 'text',
            'text': '<b>' + telegram_html.escape(telegram_html.plain_text(notice['name'])[:150]) + '</b>\n\n'
                    + get_message('feedPausedNotice', notice['lang']),
            'reply_markup': [[{
                'text': get_message('deliveryStatus', notice['lang']),
                'callback_data': {'tp': 'feedStatus'},
            }]],
        }], on_flood='raise')
    except OutboxRetryableError as e:
        jobs.finish_notice(notice, retry_after=flood_wait_seconds(e) or 60, database=database)
        return False
    except Exception as e:
        logger.warn('feed pause notice failed:', type(e).__name__)
        # Notices are best effort; an invalid chat must not hold every other
        # listener of this feed behind it. Flood waits alone are retried.
        jobs.finish_notice(notice, database=database)
        return False
    jobs.finish_notice(notice, database=database)
    return True


def notice_watcher():
    while True:
        try:
            send_pause_notice()
        except Exception as e:
            logger.err('feed pause notice job failed:', e)
        time.sleep(1)
