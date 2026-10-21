"""Repair feed URLs outside the RSS circle and all send worker pools."""
import time

from db import feed_recovery as jobs
from lib.tools.logger import Logger

logger = Logger(file='feed_recovery')
IDLE_SECONDS = 10
JOB_GAP_SECONDS = 2


def lookup_url(itunes_id):
    """The feed URLs Apple and the Podcast Index give for this id, Apple's first."""
    from app.service.podcast import catalog
    return catalog.feed_urls(itunes_id)


def valid_feed(url):
    from app.service.podcast.rss import get_rss_root_with_status
    root, status, _validators = get_rss_root_with_status(url)
    return status == 'ok' and root is not False and any(
        item.find('enclosure') is not None and item.find('enclosure').get('url')
        for item in root.findall('item'))


def _valid(validate, url, channel_id):
    try:
        return bool(url) and validate(url)
    except Exception as e:
        logger.warn('feed validation failed for channel', channel_id, type(e).__name__)
        return False


def process_one(database=None, lookup=lookup_url, validate=valid_feed, now=None):
    job = jobs.claim(database=database, now=now)
    if job is None:
        return False
    channel = jobs.channel(job['channel_id'], database=database)
    candidate = None
    result = 'unavailable'
    try:
        # The stored URL first. A feed that answers keeps its address: the
        # catalog's feedUrl may render other guids/dates, and every cursor
        # of the channel would read as "behind" or skip an episode.
        if channel is not None and _valid(validate, channel['rss_link'], job['channel_id']):
            candidate = channel['rss_link']
        elif channel is not None and channel['itunes_id']:
            found = None
            try:
                found = lookup(channel['itunes_id'])
            except Exception as e:
                logger.warn('catalog lookup failed for channel', job['channel_id'], type(e).__name__)
                result = 'catalog_unavailable'
            for url in ([found] if isinstance(found, str) else found or []):
                if url != channel['rss_link'] and _valid(validate, url, job['channel_id']):
                    candidate = url
                    break
    except Exception as e:
        candidate = None
        logger.warn('feed validation failed for channel', job['channel_id'], type(e).__name__)
    recovered = jobs.finish(
        job, channel, new_url=candidate, result=result, database=database, now=now)
    logger.log('feed recovery channel', job['channel_id'],
               'result', 'recovered' if recovered else result)
    return True


def recovery_watcher():
    # A dead thread restarts the whole jobs role: a locked database at start
    # retries the seed on the next turn instead.
    seeded = False
    while True:
        busy = False
        try:
            if not seeded:
                jobs.seed_legacy()
                seeded = True
            busy = process_one()
        except Exception as e:
            logger.err('feed recovery job failed:', e)
        # A backlog after a CDN outage drains at one check per JOB_GAP_SECONDS,
        # still gentle on iTunes lookup and the feed hosts.
        time.sleep(JOB_GAP_SECONDS if busy else IDLE_SECONDS)


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
