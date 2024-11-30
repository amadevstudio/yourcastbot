import json
from typing import Tuple

from app.repository.storage import storage
from app.service.podcast.podcast import set_last_date
from app.service.podcast.rss import get_rss_root
from app.service.record.helpers import get_record_uniq_id
from config import db_path
from db.sqliteAdapter import SQLighter
from lib.requests import requesterModule
from lib.tools.logger import logger

requester = requesterModule.Requester()


def add_sub(u_tg_id, podcast_id, service_id, service_name='itunes') -> Tuple[str | None, int | None]:
    last_date, pc_name = None, None

    if service_name == 'itunes':
        api_url_base = 'https://itunes.apple.com/lookup'
        payload = {'entity': 'podcast', 'id': service_id}

        response = requester.get(api_url_base, params=payload)

        rss_link = ""
        for result in json.loads(response.content.decode('utf-8'))["results"]:
            if "feedUrl" in result:
                last_date = str(result["releaseDate"])
                rss_link = result["feedUrl"]
                pc_name = result["collectionName"]
                break
        if rss_link == "":
            return None, None

    elif service_name == 'rss':
        last_date = None
        pc_name = None
        rss_link = service_id

    else:
        logger.warn("Error! Service " + service_name + " is unknown!")
        return None, None

    return add_sub_rss(
        u_tg_id, podcast_id, service_id, service_name, rss_link,
        additional_info={"lastDate": last_date, "pcName": pc_name})


def add_sub_rss(
        u_tg_id, podcast_id, service_id, service_name, rss_link,
        additional_info: dict = None) -> Tuple[str | None, int | None]:
    if additional_info is None:
        additional_info = {}

    root = get_rss_root(rss_link)
    if root is False:
        logger.warn("mainf/addSub unsuccessful", flush=True)
        return None, None

    if 'lastDate' in additional_info:
        last_date = additional_info['lastDate']
    else:
        last_date = None

    if 'pcName' in additional_info:
        pc_name = additional_info['pcName']
    else:
        pc_name = None

    last_guid = ""
    last_pub_date = ""
    last_record_title = ""
    # recCount = 0
    flag = False
    for channel_descr in root.getchildren():
        if channel_descr.tag == "title" and pc_name is None:
            pc_name = str(channel_descr.text)

        # получение lastDate из RSS в формате itunes
        elif channel_descr.tag in ["lastBuildDate", "pubDate"] and last_date is None:
            last_date = str(channel_descr.text)

        if channel_descr.tag == "item":
            for itemParam in channel_descr.getchildren():
                if itemParam.tag == "guid":
                    last_guid = str(itemParam.text)
                elif itemParam.tag == "pubDate":
                    last_pub_date = str(itemParam.text)
                elif itemParam.tag == "title":
                    last_record_title = str(itemParam.text)
                flag = True
        if flag:
            break

    # pgd = lastGuid + "_" + lastPubDate
    pgd = get_record_uniq_id(last_guid, last_pub_date, last_record_title)

    # не всегда в rss присутствует lastBuildDate
    last_date = set_last_date(last_date, last_pub_date)

    notify = True

    db_users = SQLighter(db_path)
    db_users.add_sub(
        u_tg_id, podcast_id, service_id, rss_link,
        pc_name, pgd, last_date, notify, service_name)
    new_channel = db_users.get_channel_by_service_tg(
        u_tg_id, service_id, service_name)
    db_users.close()

    podcast_data = storage.get_user_state_data(u_tg_id, 'podcast')
    if podcast_data is None:
        podcast_data = {}
    podcast_data["id"] = new_channel["id"]
    podcast_data["subscribed"] = True
    podcast_data["notify"] = notify
    podcast_data['mark'] = None
    podcast_data["have_new_episodes"] = False
    storage.set_user_state_data(u_tg_id, 'podcast', podcast_data)

    return pc_name, podcast_data['id']


def remove_sub(u_tg_id, podcast_id, service_id, service_name='itunes') -> Tuple[str, int | None]:
    db_users = SQLighter(db_path)
    pc_name = db_users.remove_sub(u_tg_id, podcast_id, service_id, service_name)
    db_users.close()

    podcast_data = storage.get_user_state_data(u_tg_id, 'podcast')
    podcast_data["id"] = None
    podcast_data["subscribed"] = False
    podcast_data["notify"] = False
    podcast_data['mark'] = None
    podcast_data["have_new_episodes"] = False
    storage.set_user_state_data(u_tg_id, 'podcast', podcast_data)

    return pc_name, podcast_data['id']
