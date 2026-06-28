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

bot_path = str(sys.argv[2])

sys.path.insert(1, bot_path)
os.chdir(bot_path)

from db.dbTypes import UserDBType
from db.sqliteAdapter import SQLighter
# from app.repository.storage import storage
import config

app_id = config.app_api_id
api_hash = config.app_api_hash
bot_token = config.token

getps = sys.argv[1]
SEND_BATCH_SIZE = 50
SEND_BATCH_SLEEP_SECONDS = 1


def log_line(log_path, *args):
	now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	line = f"[{now}] " + " ".join(str(arg) for arg in args)
	print(line, flush=True)
	with open(log_path, "a", encoding="utf-8") as f:
		f.write(line + "\n")


def is_channel_identifier(tgid):
	try:
		return str(int(tgid)).startswith("-100")
	except Exception:
		return False


async def send_to_user(
	tgid, message, parse_mode, attachments, attachment_type, retries=1):

	try:
		if attachment_type == "":
			await bot.send_message(int(tgid), message, parse_mode=parse_mode)
			# storage.set_user_last_text(tgid, msg.id)
		elif attachment_type == "image" or attachment_type == "audio":
			await bot.send_message(
				int(tgid), message, parse_mode=parse_mode, file=attachments)
		return True, None
	except Exception as e:
		wait_seconds = getattr(e, "seconds", None)
		if wait_seconds is not None and retries > 0:
			time.sleep(int(wait_seconds) + 1)
			return await send_to_user(
				tgid, message, parse_mode, attachments, attachment_type,
				retries=retries - 1)
		return False, e

async def upload_file(link, filename):
	file = await bot.upload_file(link, file_name=filename)
	return file

try:
	log_dir = os.path.join(bot_path, "log")
	os.makedirs(log_dir, exist_ok=True)
	log_file_name = "admin_mailing_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".log"
	log_path = os.path.join(log_dir, log_file_name)

	params = json.loads(base64.b64decode(getps).decode('utf-8'))
	log_line(log_path, "params:", params)

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
		log_line(log_path, "start:", "recipients=", recievers_len, "language=", language,
			"to_creator_only=", to_creator_only)
		sent_count = 0
		failed_count = 0
		skipped_channel_count = 0
		for reciever in send_to:
			i += 1
			if i % SEND_BATCH_SIZE == 0:
				time.sleep(SEND_BATCH_SLEEP_SECONDS)
			if i % 100 == 0:
				log_line(log_path, "progress:", i, "/", recievers_len,
					"sent=", sent_count, "failed=", failed_count,
					"skipped_channels=", skipped_channel_count)
			if is_channel_identifier(reciever['telegramId']):
				skipped_channel_count += 1
				log_line(log_path, "skipped_channel:", reciever['telegramId'])
				continue
			ok, error = bot.loop.run_until_complete(
				send_to_user(
					reciever['telegramId'], message, parse_mode,
					attachments, attachment_type))
			if ok:
				sent_count += 1
			else:
				failed_count += 1
				log_line(log_path, "failed:", reciever['telegramId'],
					type(error).__name__, error)
		bot.loop.run_until_complete(
			send_to_user(
				config.creatorId,
				f"All messages sent. Sent: {sent_count}. Failed: {failed_count}. "
				f"Skipped channels: {skipped_channel_count}. Log: {log_path}",
				"markdown", [], ""))
	log_line(log_path, "done:", "sent=", sent_count, "failed=", failed_count,
		"skipped_channels=", skipped_channel_count)
	print("All done", flush=True)
	print("Log:", log_path, flush=True)

except Exception as e:

	print(e, flush=True)
