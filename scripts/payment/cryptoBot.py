#!/usr/bin/python3.7
import datetime

# ATTENTION!
# visudo
# add to the end:
# nobody ALL = NOPASSWD: /home/yourcast/yourcast/scripts/cryptoBot.py
# or www-data ALL =(root) NOPASSWD: *same path*
# sudo chmod u+x /home/yourcast/yourcast/scripts/cryptoBot.py

from telethon import TelegramClient  # , events
from telethon.tl.custom import Button

import json
import base64

import os
import sys
# bot_path = os.getcwd().split('/yourcast')[0]
# bot_path = '/home/yourcast/yourcast'
# bot_path = '/home/kinton/Projects/Telegram/yourcast/bot'

bot_path = str(sys.argv[1])

# python scripts/subscription_income.py '{"out_summ":"367.14","OutSum":"367.14","inv_id":"3","InvId":"3","crc":"D0DE7F8580F03B6CD32AE70275527C6F","SignatureValue":"D0DE7F8580F03B6CD32AE70275527C6F","PaymentMethod":"Qiwi","IncSum":"402.57","IncCurrLabel":"Qiwi40QiwiRM","IsTest":"1","EMail":"","Fee":"0.0","Shp_summa":"5.0","Shp_uid":"6070615"}'
sys.path.insert(1, bot_path)
os.chdir(bot_path)

from db.sqliteAdapter import SQLighter
# import storage
import config

# from mainf import formatRssLastDate, user_language as user_language_processor
from app.i18n.messages import get_message

from lib.api.payment.cryptoBotApi import CryptoBotApi
from app.service.payment.paymentSafeModule import get_tariff_info_message, decode_tariff, giveAward

# TODO: refactor the file, make some tests

paramsString = base64.b64decode(sys.argv[2]).decode('utf-8')
headersString = base64.b64decode(sys.argv[3]).decode('utf-8')

payment_log_path = f"{config.BASE_DIR}/log/payment.log"

isOk = False
output = ""

def updateSubscription(db, user, amountCents):

	chat_tg_id = user['telegramId']

	current_subscription = db.getUserSubscriptionByTg(chat_tg_id)
	if current_subscription is None:
		current_tariff = None
	else:
		current_subscription = {
			'id': current_subscription['id'],
			'uid': current_subscription['uid'],
			'tariff_id': current_subscription['tariff_id'],
			'balance': current_subscription['balance'],
			'time_left': current_subscription['time_left'],
			'notify_count': current_subscription['notify_count']
		}
		current_tariff = db.getTariffById(current_subscription['tariff_id'])
	if current_tariff is None:
		current_tariff = {'id': 0, 'level': 0, 'price': 0}

	if current_subscription is None or current_subscription['id'] == 0:
		current_tariff_id = 0
		current_subscription_time_left = 0
		balance = int(amountCents)
		db.subscribeUserToTariffByTg(
			chat_tg_id, current_tariff_id,
			balance, current_subscription_time_left, 0)
		current_subscription = {
			'balance': balance,
			'time_left': current_subscription_time_left,
			'notify_count': 0
		}
		# деньги пришли, подпишитесь
		result_mode = 0

	elif current_subscription['time_left'] > 0:
		new_user_balance = current_subscription['balance'] + int(amountCents)
		db.subscribeUserToTariffByTg(
			chat_tg_id, current_subscription['tariff_id'],
			new_user_balance, current_subscription['time_left'],
			current_subscription['notify_count'])
		current_subscription['balance'] = new_user_balance
		# деньги пришли, осталось до конца х дней, хватает для продления?
		result_mode = 1

	# elif current_subscription['time_left'] == 0:
	else:
		# current_tariff = db.getTariffById(current_subscription['tariff_id'])
		# if current_tariff is None:
		# 	current_tariff = {'id': 0, 'level': 0, 'price': 0}
		new_user_balance = current_subscription['balance'] + int(amountCents)
		if current_tariff['price'] != 0:
			if new_user_balance >= current_tariff['price']:
				new_user_balance -= current_tariff['price']
				db.subscribeUserToTariffByTg(
					chat_tg_id, current_subscription['tariff_id'],
					new_user_balance, config.tariff_period,
					current_tariff['notify_count'])
				current_subscription['balance'] = new_user_balance
				current_subscription['time_left'] = config.tariff_period
				current_subscription['notify_count'] = current_tariff['notify_count']
				# деньги пришли, тариф продлен
				result_mode = 2
			else:
				db.subscribeUserToTariffByTg(
					chat_tg_id, current_subscription['tariff_id'],
					new_user_balance, current_subscription['time_left'], 0)
				current_subscription['balance'] = new_user_balance
				current_subscription['notify_count'] = 0
				# деньги пришли, не хватает на продление
				result_mode = 3
		else:
			db.subscribeUserToTariffByTg(
				chat_tg_id, current_subscription['tariff_id'],
				new_user_balance, current_subscription['time_left'], 0)
			current_subscription['balance'] = new_user_balance
			# деньги пришли, подпишитесь
			result_mode = 0

	return [result_mode, current_tariff, current_subscription]


# !!!
# Точка входа
def income_processing():
	async def send_to_creator(message):
		await bot.send_message(config.creatorId, message, parse_mode='html')

	async def error_to_user(tgid, language_code):
		message = get_message('error', language_code)
		await bot.send_message(int(tgid), message, parse_mode='html')

	async def send_to_user(
		tgid, result, current_tariff, current_subscription, language_code):

		tariff_str = decode_tariff(current_tariff['level'], language_code)
		tariff_info_message = get_tariff_info_message(
			tariff_str, current_subscription['balance'],
			current_tariff['price'], current_subscription['time_left'],
			current_subscription['notify_count'], language_code)
		buttons = [
			Button.inline(
				get_message('tariffs', language_code), b'{\"tp\": \"bs_trfs\"}'),
			Button.inline(
				get_message('goBackMenu', language_code), b'{\"tp\": \"menu\"}')
		]
		# деньги пришли, подпишитесь
		if result == 0:
			message = get_message('money_came', language_code) \
				+ " " + get_message('subscribe_now', language_code) \
				+ "\n\n" + tariff_info_message
		# деньги пришли, осталось до конца х дней, хватает для продления?
		elif result == 1:
			if current_subscription['balance'] > current_tariff['price']:
				prolongation = get_message('enough_to_prolongation', language_code)
			else:
				prolongation = get_message('not_enough_to_prolongation', language_code)
			message = get_message('money_came', language_code) \
				+ "\n" + prolongation \
				+ "\n\n" + tariff_info_message
		# деньги пришли, тариф продлен
		elif result == 2:
			message = get_message('money_came', language_code) \
				+ " " + get_message('tariff_prolonged', language_code) \
				+ "\n\n" + tariff_info_message
		# деньги пришли, не хватает на продление
		elif result == 3:
			message = get_message('money_came', language_code) \
				+ " " + get_message('not_enough_to_prolongation', language_code) \
				+ "\n\n" + tariff_info_message
		else:
			message = get_message('money_came', language_code)

		message = await bot.send_message(int(tgid), message, buttons=buttons, parse_mode='html')

		# storage.clear_user_storage(tgid)
		# storage.add_user_state(tgid, "menu")
		# storage.add_user_state(tgid, "bot_sub")
		# storage.add_user_state(tgid, "cryptobot_bot_sub")
		#
		# storage.del_user_resend_flag(tgid)
		# storage.set_user_last_text(tgid, message.id)

	async def notify_refer(refer_id, message):
		message = message.replace('*', '**')  # bold in telethon's markdown
		message = await bot.send_message(int(refer_id), message, parse_mode='html')
		# storage.del_user_resend_flag(refer_id)
		# storage.set_user_last_text(refer_id, message.id)

	try:

		app_id = config.app_api_id
		api_hash = config.app_api_hash
		bot_token = config.token

		bot = TelegramClient(
			'www-data', app_id, api_hash).start(bot_token=bot_token)

		# data = json.loads(getps)
		# params = data['body']
		# headers = data['headers']

		params = json.loads(paramsString)
		headers = json.loads(headersString)

		signature = headers.get('Crypto-Pay-Api-Signature', '')

		customPayload = json.loads(params["payload"]["payload"])

		if "net" in customPayload and customPayload["net"] == "testnet":
			test_mode = True
		else:
			test_mode = False

		if test_mode:
			cryptoBotApi = CryptoBotApi(config.crypto_bot_api_key_test, "testnet")
		else:
			cryptoBotApi = CryptoBotApi(config.crypto_bot_api_key)

		queryVerified = cryptoBotApi.isDataSignatureCorrect(paramsString, signature)

		if not queryVerified:
			return

		invoice_id = params["payload"]["invoice_id"]
		invoice_hash = params["payload"]["hash"]
		paid_at = params["payload"]["paid_at"]
		status = params["payload"]["status"]

		chat_tg_id = customPayload["tgid"]
		amountCents = customPayload["amount"]

		db = SQLighter(config.db_path)
		# db.subscribeUserToTariffByTg(
		# 	call.chat.id, desire_tariff['id'], new_balance, new_time_left)
		user = db.get_user_by_tg(chat_tg_id)

		# user_language = user_language_processor(user['lang'])
		user_language = user['lang'] if user['lang'] is not None else 'en'

		invoice = db.findInvoice(
			user['id'], "cryptoBot", invoice_id,
			invoiceHash=invoice_hash)

		if invoice is None:
			invoice_already_paid = False
			[result_mode, current_tariff, current_subscription] \
				= updateSubscription(db, user, amountCents)

			invoice = db.createInvoice(
				user['id'], "cryptoBot", invoice_id, datetime.datetime.now(),  # formatRssLastDate(paid_at),
				invoiceHash=invoice_hash, status=status, amount=amountCents)
		else:
			invoice_already_paid = True

		db.close()

		if not invoice_already_paid:
			try:
				with bot:
					bot.loop.run_until_complete(send_to_user(
						user['telegramId'], result_mode, current_tariff,
						current_subscription, user_language))

					if config.server:
						with open(payment_log_path, 'a+') as psl:
							psl.write(paramsString + '\n\n')

				if user['ref_id'] is not None:
					message = giveAward(user['ref_id'], user['telegramId'], 'replenished')
					if message is not None:
						with bot:
							bot.loop.run_until_complete(notify_refer(user['ref_id'], message))

				with bot:
					bot.loop.run_until_complete(
						send_to_creator("New income by cryptobot",))

			except Exception as e:
				exc_type, exc_obj, exc_tb = sys.exc_info()
				fename = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
				if config.server:
					with open(payment_log_path, 'a+') as pfl:
						pfl.write(
							str(e) + " : "
							+ str(exc_type) + ' ' + str(fename) + ' ' + str(exc_tb.tb_lineno) + ": "
							+ paramsString + '\n\n')
				else:
					print(e, exc_type, fename, exc_tb.tb_lineno, flush=True)

		print("OK")

	except Exception as e:
		exc_type, exc_obj, exc_tb = sys.exc_info()
		fename = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
		if config.server:
			with open(payment_log_path, 'a+') as pfl:
				import sqlite3
				connection = sqlite3.connect(config.db_path, timeout=10)
				pfl.write("Connection open\n")
				connection.row_factory = sqlite3.Row
				cursor = connection.cursor()
				cursor.execute("update user_channel_cs set notify = 0 where id = 1")
				pfl.write("Executed\n")
				connection.commit()
				pfl.write("Commited\n")
				connection.close()
				pfl.write(
					str(e) + " : "
					+ str(exc_type) + ' ' + str(fename) + ' ' + str(exc_tb.tb_lineno) + ": "
					+ paramsString + ' ' + headersString + '\n\n')
		else:
			print(e, exc_type, fename, exc_tb.tb_lineno, flush=True)


income_processing()
