# -*- coding: utf-8 -*-

import os.path
from typing import TypedDict

# import sys
import constants
import constant_texts

# Path to config file (bot work directory)
# BASE_DIR = os.path.dirname(sys.argv[0])
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
work_dir = BASE_DIR

apple_itunes_search = "https://itunes.apple.com/search"

creatorId = constants.creatorId
# agentId = creatorId
botId = constants.botId
donate_link = constants.donate_link

advertising_contact = constants.advertising_contact

transmitterBotToken = constants.transmitterBotToken

payment_login = constants.payment_login
payment_p1 = constants.payment_p1
payment_p2 = constants.payment_p2
payment_p1_test = constants.payment_p1_test
payment_p2_test = constants.payment_p2_test

app_api_id = constants.app_api_id
app_api_hash = constants.app_api_hash

server = constants.isServer
maintenance = constants.isUnderMaintenance
test = constants.isTest

threads_config = {
    'send': 4,
    'rec': 4,
    'update': 2
}

maxTgChannelsPerAccount = 5

perPage = 5

std_bitrate = None
balance_watcher_period = 'per_hour'
payment_service_watcher_period = 'per_hour'

tariff_period = 30 * 24
tariff_ref_period = 5 * 24
tariff_new_user_period = 14 * 24
tariff_secret_start_cmd_period = 2 * 24
tariff_ref_no_subscription_period = 3 * 24
tariff_ref_notifies = 20
tariff_ref_sub_period = 15 * 24

# максимальное число подписок и количества в обновлении
max_subscriptions_without_tariff = 15

# максимальная длина подкаста хэша для идентификации подкаста
maxPodcastDateCallDataHexLen = 15

yandex_disk_mail = constants.yandex_disk_mail
yandex_disk_backup_token = constants.yandex_disk_backup_token

creator_email = constants.yandex_disk_mail

special_paid_emails = constants.special_paid_emails
patreon_creator_access_token = constants.patreon_creator_access_token
patreon_subs_perpage = 100

crypto_bot_api_key = constants.crypto_bot_api_key
crypto_bot_api_key_test = constants.crypto_bot_api_key_test

amplitude_analytics_api_key = constants.amplitude_analytics_api_key

if server:
    if not test:
        token = constants.serverToken
        botName = constants.serverBotName
    else:
        token = constants.testToken
        botName = constants.testBotName
    # agentId = constants.serverAgentId
    # transmitterChatId = constants.serverTransmitterChatId
else:
    if not test:
        token = constants.localToken  # instafeed dev
        botName = constants.localBotName
    else:
        token = constants.testToken
        botName = constants.testBotName
    # agentId = constants.localAgentId
    # transmitterChatId = constants.localTransmitterChatId

database_name = constants.databaseName
db_path = os.path.join(BASE_DIR, 'db/' + database_name)

shelve_name = os.path.join(BASE_DIR, 'db/shelve.db')
telegram_cache_shelve_name = os.path.join(BASE_DIR, 'db/shelve_telegram_cache.db')
use_cache = True if server else False

noPhoto = constants.noPhoto

available_podcast_hoster_links = [
    'castos.com',
    'vk.com',
    'redcircle.com'
]

try:
    another_projects_texts = constant_texts.anotherProjectsTexts
except Exception:
    another_projects_texts = []
