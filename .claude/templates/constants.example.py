# -*- coding: utf-8 -*-
"""Placeholder secrets used by dev sessions (Claude Code on the web).

The real ``constants.py`` is gitignored and lives only on the developer machine
and on the production server; see ``how-to.txt`` for the meaning of every value.
This template only exists so the project stays importable (``import config``
pulls this module in), which is what mypy and any script need. Nothing here is
a real credential and nothing here talks to Telegram: the bot must not be
started with these values.
"""

creatorId = 0
botId = 0
storageChatId = 0

donate_link = 'https://example.invalid/donate'
advertising_contact = '@example'

transmitterBotToken = ''

# Robokassa
payment_login = ''
payment_p1 = ''
payment_p2 = ''
payment_p1_test = ''
payment_p2_test = ''

# Telegram app credentials (Telethon).
# Left empty on purpose: agent/bot_telethon.py calls TelegramClient(...).start() at
# import time, so any module that pulls it in (app.routes.*, app.core.controller,
# app.jobs.podcastsUpdater, ...) would otherwise try to reach Telegram from the
# sandbox. Empty values make Telethon raise a ValueError immediately instead of
# hanging on connection retries; the other ~55 modules import fine.
app_api_id = 0
app_api_hash = ''

isServer = False
isUnderMaintenance = False
isTest = True

serverWorkDir = ''
serverToken = ''
serverBotName = 'yourcast_bot'
serverAgentId = 0
serverTransmitterChatId = ''
payment_log_path = ''

localWorkDir = ''
localToken = ''
localBotName = 'yourcast_local_bot'
localAgentId = 0
localTransmitterChatId = ''

testToken = ''
testBotName = 'yourcast_test_bot'

databaseName = 'yourcast.db'

noPhoto = ''

yandex_disk_mail = 'dev@example.invalid'
yandex_disk_backup_token = ''

special_paid_emails: list[str] = []

patreon_creator_access_token = ''

crypto_bot_api_key = ''
crypto_bot_api_key_test = ''

amplitude_analytics_api_key = ''
