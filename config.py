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
storageChatId = getattr(constants, 'storageChatId', None) or creatorId
# Download and re-upload episodes of podcasts added by a bare RSS link (not
# found in iTunes). Off: those go by URL only, bigger files get a link.
trust_rss_podcasts = bool(getattr(constants, 'trustRssPodcasts', False))
# Read-only token for GET /api/diag/* (admin API). Unset or shorter than 32
# chars: the endpoints answer 404. Never commit it: constants.py only.
diag_token = getattr(constants, 'diagToken', None) or None
# AI episode summaries (app/service/ai): off until the keys and the model are set in constants.py.
# The summary goes through OpenRouter; the model is its id there, e.g. "provider/model-name".
openrouter_api_key = getattr(constants, 'openrouterApiKey', None) or ''
ai_summary_model = getattr(constants, 'openrouterModel', None) or ''
groq_api_key = getattr(constants, 'groqApiKey', None) or ''
# hours of audio summarized per 30 days by plan level; a summary someone already made is free for everyone
ai_summary_hours_per_month = {1: 5, 2: 15, 3: 30}
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
    # User download taps. Independent of RSS fanout.
    'rec': 4,
    # Automatic circle sends. Raise this if notify lags; does not steal rec.
    'circle': 2,
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
# a new user who came by a friend's link: added to tariff_new_user_period
tariff_ref_invitee_period = 7 * 24
# prepaid months of Relay with Telegram Stars: (months, % off the charge)
prepay_bundles = ((3, 10), (6, 15), (12, 25))
# win-back after Relay stops: messages this many days after, and % off the first month (once per user)
winback_after_days = (7, 30)
winback_offer_discount = 30
# the server's monthly bill, USD: the fixed cost the admin economics page spreads over users by load
server_usd_month = 10

# максимальное число подписок и количества в обновлении
max_subscriptions_without_tariff = 15
# episodes a listener without a plan gets by click in any 7 days (app/service/record/free_limit.py)
free_rec_per_week = 10

# максимальная длина подкаста хэша для идентификации подкаста
maxPodcastDateCallDataHexLen = 15

yandex_disk_mail = constants.yandex_disk_mail
yandex_disk_backup_token = constants.yandex_disk_backup_token

creator_email = constants.yandex_disk_mail

special_paid_emails = constants.special_paid_emails
patreon_creator_access_token = constants.patreon_creator_access_token
patreon_subs_perpage = 100
patreon_api_v2_url = "https://www.patreon.com/api/oauth2/v2"
patreon_request_timeout = 30

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
# use_cache = True if server else False
use_cache = True

# Placeholder cover for podcasts without artwork. Shipped with the repo, so it never depends
# on a third-party host staying alive (the previous external url now answers with html)
no_photo_path = os.path.join(BASE_DIR, 'static/no_podcast_cover.png')
noPhoto = no_photo_path if os.path.isfile(no_photo_path) else getattr(constants, 'noPhoto', '')

available_podcast_hoster_links = [
    'castos.com',
    'vk.com',
    'redcircle.com'
]

try:
    another_projects_texts = constant_texts.anotherProjectsTexts
except Exception:
    another_projects_texts = []
