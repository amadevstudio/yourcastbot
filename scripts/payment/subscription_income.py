#!/usr/bin/python3.7

# Robokassa

# ATTENTION!
# visudo
# add to the end:
# nobody ALL = NOPASSWD: /home/yourcast/yourcast/scripts/payment/subscription_income.py
# or www-data ALL =(root) NOPASSWD: *same path*
# sudo chmod u+x /home/yourcast/yourcast/scripts/payment/subscription_income.py


from telethon import TelegramClient  # , events
from telethon.tl.custom import Button

import json
import hashlib

import os
import sys

import base64

# bot_path = os.getcwd().split('/yourcast')[0]
# bot_path = '/home/yourcast/yourcast'
# bot_path = '/home/kinton/Projects/Telegram/yourcast/bot'

bot_path = str(sys.argv[2])

# python scripts/subscription_income.py '{"out_summ":"367.14","OutSum":"367.14","inv_id":"3","InvId":"3","crc":"D0DE7F8580F03B6CD32AE70275527C6F","SignatureValue":"D0DE7F8580F03B6CD32AE70275527C6F","PaymentMethod":"Qiwi","IncSum":"402.57","IncCurrLabel":"Qiwi40QiwiRM","IsTest":"1","EMail":"","Fee":"0.0","Shp_summa":"5.0","Shp_uid":"6070615"}'
sys.path.insert(1, bot_path)

from db.sqliteAdapter import SQLighter
import config
import app.service.user.language
from app.i18n.messages import get_message

from app.service.payment.paymentSafeModule import get_tariff_info_message, decode_tariff, giveAward

getps = base64.b64decode(sys.argv[1]).decode('utf-8')

isOk = False
output = ""

async def send_to_creator(message):
	await bot.send_message(config.creatorId, message)

async def error_to_user(tgid, language_code):
	message = get_message('error', language_code)
	await bot.send_message(int(tgid), message)

payment_log_path = f"{config.BASE_DIR}/log/payment.log"

try:

	params = json.loads(getps)
	out_sum = params['OutSum']
	inv_id = params['InvId']
	crc = params['SignatureValue']

	user_id = int(params['Shp_uid'])

	try:
		if 'IsTest' in params:
			is_test = (int(params['IsTest']) == 1)
		else:
			is_test = False
	except Exception:
		is_test = False
	if not config.server or (user_id == config.creatorId and is_test):
		payment_p2 = config.payment_p2_test
	else:
		payment_p2 = config.payment_p2

	shp_summ_cr = 'Shp_summa=' + str(params['Shp_summa'])
	shp_uid_cr = 'Shp_uid=' + str(params['Shp_uid'])

	res = (
		out_sum + ':' + inv_id + ':' + payment_p2 + ":"
		+ shp_summ_cr + ':' + shp_uid_cr)
	hash_object = hashlib.md5(res.encode())
	signature = hash_object.hexdigest()
	signature = signature.upper()

	app_id = config.app_api_id
	api_hash = config.app_api_hash
	bot_token = config.token

	if signature == crc:
		isOk = True
		output = "OK" + inv_id + "\n"

		db = SQLighter(config.db_path)
		# db.subscribeUserToTariffByTg(
		# 	call.chat.id, desire_tariff['id'], new_balance, new_time_left)
		user = db.get_user_by_tg(params['Shp_uid'])
		user_language = app.service.user.language.user_language(user['lang'])
		current_subscription = db.getUserSubscriptionByTg(params['Shp_uid'])
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
			balance = int(float(params['Shp_summa']) * 100)
			db.subscribeUserToTariffByTg(
				params['Shp_uid'], current_tariff_id,
				balance, current_subscription_time_left, 0)
			current_subscription = {
				'balance': balance,
				'time_left': current_subscription_time_left,
				'notify_count': 0
			}
			# деньги пришли, подпишитесь
			result_mode = 0

		elif current_subscription['time_left'] > 0:
			new_user_balance = current_subscription['balance'] \
				+ int(float(params['Shp_summa']) * 100)
			db.subscribeUserToTariffByTg(
				params['Shp_uid'], current_subscription['tariff_id'],
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
			new_user_balance = current_subscription['balance'] \
				+ int(float(params['Shp_summa']) * 100)
			if current_tariff['price'] != 0:
				if new_user_balance >= current_tariff['price']:
					new_user_balance -= current_tariff['price']
					db.subscribeUserToTariffByTg(
						params['Shp_uid'], current_subscription['tariff_id'],
						new_user_balance, config.tariff_period,
						current_tariff['notify_count'])
					current_subscription['balance'] = new_user_balance
					current_subscription['time_left'] = config.tariff_period
					current_subscription['notify_count'] = current_tariff['notify_count']
					# деньги пришли, тариф продлен
					result_mode = 2
				else:
					db.subscribeUserToTariffByTg(
						params['Shp_uid'], current_subscription['tariff_id'],
						new_user_balance, current_subscription['time_left'], 0)
					current_subscription['balance'] = new_user_balance
					current_subscription['notify_count'] = 0
					# деньги пришли, не хватает на продление
					result_mode = 3
			else:
				db.subscribeUserToTariffByTg(
					params['Shp_uid'], current_subscription['tariff_id'],
					new_user_balance, current_subscription['time_left'], 0)
				current_subscription['balance'] = new_user_balance
				# деньги пришли, подпишитесь
				result_mode = 0
		db.close()

	else:

		output = "bad sign\n"
		bot = TelegramClient(
			'yourcastbot', app_id, api_hash).start(bot_token=bot_token)

		db = SQLighter(config.db_path)
		user = db.get_user_by_tg(params['Shp_uid'])
		db.close()
		user_language = app.service.user.language.user_language(user['lang'])

		with bot:
			bot.loop.run_until_complete(error_to_user(
				params['Shp_uid'], user_language))
			message = "Bad crc: " + signature + " != " + crc + "; " \
				+ "uid: " + params['Shp_uid'] + ' sum: ' + params['OutSum'] \
				+ ' Payload:\n' + getps + '\n\n' \
				+ 'Key: ' + payment_p2 + '; is_test: ' + str(is_test)
			bot.loop.run_until_complete(send_to_creator(message,))
		# что-то пошло не так. если деньги ушли,
		# а в боте их нет — свяжитесь с администрацией

except Exception as e:
	exc_type, exc_obj, exc_tb = sys.exc_info()
	fename = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
	if config.server:
		with open(payment_log_path, 'a+') as pfl:
			pfl.write(
				str(e) + " : "
				+ exc_type + ' ' + fename + ' ' + exc_tb.tb_lineno + " : "
				+ getps + '\n\n')
	else:
		print(e, exc_type, fename, exc_tb.tb_lineno, flush=True)


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

	message = await bot.send_message(int(tgid), message, buttons=buttons, parse_mode="HTML")

async def notify_refer(refer_id, message):
	message = await bot.send_message(int(refer_id), message, parse_mode="HTML")

if isOk:
	try:
		bot = TelegramClient(
			'yourcastbot', app_id, api_hash).start(bot_token=bot_token)

		message = crc + '\n'
		message += signature + '\n\n'
		message += getps

		with bot:
			try:
				bot.loop.run_until_complete(send_to_creator(message))
			except Exception:
				pass
			bot.loop.run_until_complete(send_to_user(
				params['Shp_uid'], result_mode, current_tariff,
				current_subscription, user_language))

			if config.server:
				with open(payment_log_path, 'a+') as psl:
					psl.write(getps + '\n\n')
		if user['ref_id'] is not None:
			message = giveAward(user['ref_id'], user['telegramId'], 'replenished')
			if message is not None:
				with bot:
					bot.loop.run_until_complete(notify_refer(user['ref_id'], message))

	except Exception as e:
		exc_type, exc_obj, exc_tb = sys.exc_info()
		fename = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
		if config.server:
			with open(payment_log_path, 'a+') as pfl:
				pfl.write(
					str(e) + " : "
					+ exc_type + ' ' + fename + ' ' + exc_tb.tb_lineno + " : "
					+ getps + '\n\n')
		else:
			print(e, exc_type, fename, exc_tb.tb_lineno, flush=True)

if output == "":
	print("bad sign\n", flush=True)
else:
	print(output, flush=True)
