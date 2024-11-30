#!/usr/bin/python3.7
import datetime
import time

# ATTENTION!
# visudo
# add to the end:
# nobody ALL = NOPASSWD: /home/yourcast/yourcast/scripts/subscription_income.py
# or www-data ALL =(root) NOPASSWD: *same path*
# sudo chmod u+x /home/yourcast/yourcast/scripts/subscription_income.py

from telethon import TelegramClient  # , events

import json
import os
import sys
import base64

from db.dbTypes import UserDBType

bot_path = str(sys.argv[2])

sys.path.insert(1, bot_path)
os.chdir(bot_path)

from db.sqliteAdapter import SQLighter
# from app.repository.storage import storage
import config

app_id = config.app_api_id
api_hash = config.app_api_hash
bot_token = config.token

getps = sys.argv[1]


async def send_to_user(
	tgid, message, parse_mode, attachments, attachment_type):

	try:
		if attachment_type == "":
			msg = await bot.send_message(int(tgid), message, parse_mode=parse_mode)
			# storage.set_user_last_text(tgid, msg.id)
		elif attachment_type == "image" or attachment_type == "audio":
			msg = await bot.send_message(
				int(tgid), message, parse_mode=parse_mode, file=attachments)
	except Exception:
		pass

async def upload_file(link, filename):
	file = await bot.upload_file(link, file_name=filename)
	return file

try:

	params = json.loads(base64.b64decode(getps).decode('utf-8'))
	print(params, flush=True)

	if 'to_creator_only' in params and params['to_creator_only'] == 'true':
		to_creator_only = True
	else:
		to_creator_only = False

	if 'recipients_identifiers' in params \
		and params['recipients_identifiers'] != '':

		recipients_identifiers = params['recipients_identifiers'].split(',')
	else:
		recipients_identifiers = []

	if 'parse_mode' not in params or params['parse_mode'] == 'mrkd':
		parse_mode = 'markdown'
	elif params['parse_mode'] == 'html':
		parse_mode = 'html'
	else:
		parse_mode = ''

	language = params.get('language', None)
	if language == '':
		language = None

	# -----

	send_to: list[UserDBType]

	if to_creator_only:
		send_to = [{'telegramId': config.creatorId}]
	else:
		if len(recipients_identifiers) > 0:
			send_to = []
			for id in recipients_identifiers:
				send_to.append({'telegramId': id})
		else:
			db = SQLighter(config.db_path)
			send_to = db.get_all_users(language=language)
			db.close()

	message = params['message']

	if len(params['attachments']) > 0:
		attachment_type = params['attachment_type']
		attachment_files = params['attachments']
	else:
		attachment_type = ""
		attachment_files = []

	bot = TelegramClient('www-data', app_id, api_hash).start(bot_token=bot_token)
	recievers_len = len(send_to)

	attachments = []
	for a in attachment_files:
		file = bot.loop.run_until_complete(upload_file(a['link'], a['filename']))
		attachments.append(file)

	i = 0
	with bot:
		bot.loop.run_until_complete(
			send_to_user(
				config.creatorId, f"Start sending messages to {recievers_len}",
				"markdown", [], ""))
		for reciever in send_to:
			i += 1
			if i % 10 == 0:
				time.sleep(1)
			if i % 100 == 0:
				print('%d / %d' % (i, recievers_len), flush=True)
				print(datetime.datetime.now())
			bot.loop.run_until_complete(
				send_to_user(
					reciever['telegramId'], message, parse_mode,
					attachments, attachment_type))
		bot.loop.run_until_complete(
			send_to_user(
				config.creatorId, "All messages sent", "markdown", [], ""))
	print("All done", flush=True)

except Exception as e:

	print(e, flush=True)
