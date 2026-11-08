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
# Episodes of podcasts added by a bare RSS link are downloaded like listed ones: every fetch
# reaches public addresses only (lib/net/public_only.py). trustRssPodcasts = False turns it off.
trust_rss_podcasts = bool(getattr(constants, 'trustRssPodcasts', True))
# Read-only token for GET /api/diag/* (admin API). Unset or shorter than 32
# chars: the endpoints answer 404. Never commit it: constants.py only.
diag_token = getattr(constants, 'diagToken', None) or None
# A dead man's switch URL (e.g. a healthchecks.io check): pinged every minute while the
# Bot API answers (app/core/telegram_link.py). Unset: no ping. constants.py only.
heartbeat_url = getattr(constants, 'heartbeatUrl', None) or ''
# AI episode summaries (app/service/ai): off until the key and the model are set in constants.py.
# The summary goes through OpenRouter; the model is its id there, e.g. "provider/model-name".
openrouter_api_key = getattr(constants, 'openrouterApiKey', None) or ''
ai_summary_model = getattr(constants, 'openrouterModel', None) or ''
# the speech-to-text model (its OpenRouter id) for episodes whose feed has no transcript, same key
ai_transcribe_model = getattr(constants, 'openrouterTranscribeModel', None) or ''
# better models for chats that paid (app/service/ai/paid_models.py), each optional, unset: everyone gets the above.
# The speech-to-text one must label speakers (e.g. x-ai/grok-stt-1.0); the other answers summaries and questions.
ai_paid_transcribe_model = getattr(constants, 'openrouterPaidTranscribeModel', None) or ''
ai_paid_summary_model = getattr(constants, 'openrouterPaidModel', None) or ''
# hours of audio summarized per 30 days by plan level; a summary someone already made is free for everyone
ai_summary_hours_per_month = {1: 5, 2: 15, 3: 30}
# a plan nobody paid for yet (the welcome Relay, referral days): its hours, whatever its level
ai_summary_trial_hours = 5
# of those hours, what the paid model (openrouterPaidTranscribeModel) may transcribe in 30 days, by plan
# level; past it, Whisper. With questions a day by level, a plan's worst month fits its budget (below)
ai_paid_transcribe_hours_per_month = {1: 2, 2: 4, 3: 15}
# questions a day about an episode or a show, by plan level (a trial: ai_trial_questions_per_day)
ai_questions_per_day = {1: 5, 2: 10, 3: 20}
# and in any 30 days, ten days of them (a trial: ai_trial_questions_per_month): the worst month is a third
# of every question of every day
ai_questions_per_month = {1: 50, 2: 100, 3: 200}
# a plan nobody paid for yet (the welcome Relay, referral days): its questions, whatever its level
ai_trial_questions_per_day = 5
ai_trial_questions_per_month = 50
# the most a paid plan's AI may cost in any 30 days, as a share of what its price brings (the price at
# payout_share's Stars share): new summaries, transcripts, questions and the paid model stop there
# (quota.budget). The owner's rule (2026-11-02): no plan may cost more in AI than it brings.
ai_budget_share = 0.7
# what is reckoned before a call is made, USD (made on 2026-11-02: Whisper turbo 0.015 and Grok 0.106 per
# hour of audio, a summary's model call 0.002, a question 0.002, up to 0.009 on a long transcript):
# one starts only if it fits what the budget has left
ai_transcribe_usd_hour = 0.02
ai_paid_transcribe_usd_hour = 0.12
ai_call_usd = 0.01
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
# "what stops you from taking a plan?" goes to the chats due until this day, UTC (app/jobs/why_survey.py)
why_survey_until = '2026-11-21'
# the old accounts asked in all, 300 an hour: the pilot's 1000 (2026-11-07: 3% of those reached answered,
# 3 in 4 had blocked the bot long ago), then all of them (the owner's call, 2026-11-08)
why_old_limit = 11000
# the bot's channel (news), which takes messages from anyone: a longer answer can go there too
channel_url = 'https://t.me/yourcast_channel'
channel_direct_url = 'https://t.me/yourcast_channel?direct'
# the server's monthly bill, USD: the fixed cost the admin economics page spreads over users by load
server_usd_month = 10
# the share of a payment that reaches us, by payment_history.service_type (others: all of it), for the
# admin economics page. Stars are sold at Telegram's withdraw rate, but the rewards come through Fragment
# in TON: an estimate of what conversion and fees take (2-5% by unofficial accounts, no official figure)
payout_share = {'telegramStars': 0.95}

# максимальное число подписок и количества в обновлении
max_subscriptions_without_tariff = 15
# episodes a listener without a plan gets by click in any 7 days (app/service/record/free_limit.py)
free_rec_per_week = 10
# episodes by click a plan nobody paid for (the welcome trial, referral days) gets in any 24 hours:
# one trial took ~1000 episodes of one show in 4 days and held a rec worker of 4 (2026-10)
trial_rec_per_day = 100

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

try:
    another_projects_texts = constant_texts.anotherProjectsTexts
except Exception:
    another_projects_texts = []
