"""Keep the latest feed episode as a text reference, before updater early returns."""
from hashlib import sha256

from app.controller.types_helpers.recs import rec_callback_data_identifier
from app.service.record.helpers import get_record_uniq_id
from config import maxPodcastDateCallDataHexLen
from db import listening


def remember_latest(root, channel, database=None):
    item = root.find('item')
    if item is None:
        return None
    def value(tag):
        node = item.find(tag)
        return str(node.text) if node is not None else ''
    guid, date, title = value('guid'), value('pubDate'), value('title')
    raw_id = get_record_uniq_id(guid, date, title)
    # Updater strips line breaks/outer spaces from dates, while rec hashes
    # use the original date. Keep both contracts, without moving either cursor.
    cursor = get_record_uniq_id(guid, date.replace('\n', '').strip(), title)
    callback = rec_callback_data_identifier(channel['id'], None, None,
        sha256(raw_id.encode('utf-8')).hexdigest()[:maxPodcastDateCallDataHexLen], 1)
    return listening.remember(title, root.findtext('title') or channel['name'], callback,
                              database, channel_id=channel['id'], cursor=cursor)
