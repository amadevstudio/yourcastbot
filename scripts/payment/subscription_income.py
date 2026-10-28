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

import hashlib
import hmac
import os
import sys
import base64

# bot_path = os.getcwd().split('/yourcast')[0]
# bot_path = '/home/yourcast/yourcast'
# bot_path = '/home/kinton/Projects/Telegram/yourcast/bot'

bot_path = str(sys.argv[2])

# python scripts/subscription_income.py '{"out_summ":"367.14","OutSum":"367.14","inv_id":"3","InvId":"3","crc":"D0DE7F8580F03B6CD32AE70275527C6F","SignatureValue":"D0DE7F8580F03B6CD32AE70275527C6F","PaymentMethod":"Qiwi","IncSum":"402.57","IncCurrLabel":"Qiwi40QiwiRM","IsTest":"1","EMail":"","Fee":"0.0","Shp_summa":"5.0","Shp_uid":"6070615"}'
sys.path.insert(1, bot_path)

import config
import app.service.user.language
from app.i18n.messages import get_message

from app.service.payment.paymentSafeModule import get_tariff_info_message, decode_tariff, award_referrer_for_payment
from scripts.payment.webhook_input import robokassa_result
from scripts.payment.credit import credit_once, notify

getps = base64.b64decode(sys.argv[1]).decode('utf-8')

isOk = False
output = ""

async def send_to_creator(message):
	await bot.send_message(config.creatorId, message)

payment_log_path = f"{config.BASE_DIR}/log/payment.log"

params = robokassa_result(getps)
if params is None:
	print("bad sign\n", flush=True)
	sys.exit(0)

try:

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
	signature = hash_object.hexdigest().upper()
	crc_norm = str(crc).upper()
	app_id = config.app_api_id
	api_hash = config.app_api_hash
	bot_token = config.token

	if len(signature) != len(crc_norm) or not hmac.compare_digest(signature, crc_norm):
		output = "bad sign\n"
		bot = TelegramClient(
			'yourcastbot', app_id, api_hash).start(bot_token=bot_token)

		# an unsigned request names any uid: it reaches the creator only, never that
		# chat (anyone could make the bot write to anyone) and makes no users row
		with bot:
			message = "Bad robokassa crc uid=%s inv=%s is_test=%s" % (
				params['Shp_uid'], inv_id, is_test)
			bot.loop.run_until_complete(send_to_creator(message,))

	else:
		isOk = True
		output = "OK" + inv_id + "\n"

		# the signature is the same for every delivery of an invoice, so a notice sent
		# again (by Robokassa or by anyone holding the URL) must credit nothing: the
		# invoice is checked and written with the credit, a repeat is answered OK
		user, credited = credit_once(
			params['Shp_uid'], "robokassa", inv_id, int(round(float(params['Shp_summa']) * 100)))
		user_language = app.service.user.language.user_language(user['lang'])
		if credited['already_processed']:
			isOk = False
		else:
			result_mode = credited['result_mode']
			current_tariff = credited['current_tariff']
			current_subscription = credited['current_subscription']

except Exception as e:
	exc_type, exc_obj, exc_tb = sys.exc_info()
	fename = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
	if config.server:
		with open(payment_log_path, 'a+') as pfl:
			pfl.write(
				"%s : %s %s %s : robokassa webhook error\n\n"
				% (e, exc_type, fename, exc_tb.tb_lineno))
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

		message = "New robokassa income uid=%s inv=%s" % (
			params.get("Shp_uid"), inv_id)

		with bot:
			try:
				bot.loop.run_until_complete(send_to_creator(message))
			except Exception:
				pass
			notify(bot, send_to_user(
				params['Shp_uid'], result_mode, current_tariff,
				current_subscription, user_language), "payer")

			if config.server:
				with open(payment_log_path, 'a+') as psl:
					psl.write(
						"robokassa paid uid=%s inv=%s\n" % (
							params.get("Shp_uid"), inv_id))
		refer_id, message = award_referrer_for_payment(user['telegramId'])
		if message is not None:
			with bot:
				notify(bot, notify_refer(refer_id, message), "inviter")

	except Exception as e:
		exc_type, exc_obj, exc_tb = sys.exc_info()
		fename = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
		if config.server:
			with open(payment_log_path, 'a+') as pfl:
				pfl.write(
					"%s : %s %s %s : robokassa notify error\n\n"
					% (e, exc_type, fename, exc_tb.tb_lineno))
		else:
			print(e, exc_type, fename, exc_tb.tb_lineno, flush=True)

if output == "":
	print("bad sign\n", flush=True)
else:
	print(output, flush=True)
