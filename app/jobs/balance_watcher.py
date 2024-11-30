import datetime
import time

from app.i18n.messages import get_message
from app.service.payment.paymentModule import get_tariff_description_and_button_text
from app.service.payment.paymentSafeModule import decode_tariff, get_tariff_info_message
from config import db_path, tariff_period
from db.sqliteAdapter import SQLighter
from lib.telegram.general.message_master import outer_sender
from lib.tools.logger import logger


def balance_watcher(update_time):
    while True:
        if update_time == 'per_hour':
            delta = datetime.timedelta(hours=1)
            now = datetime.datetime.now()
            next_hour = (now + delta).replace(microsecond=0, second=0, minute=0)
            wait_seconds = (next_hour - now).seconds
        else:
            wait_seconds = 3600
        time.sleep(wait_seconds)
        time.sleep(1)  # bcs of repeats in 1 second

        db = SQLighter(db_path)
        prolonged_users = db.get_users_who_can_be_prolonged()
        not_prolonged_users = db.get_users_who_cannot_be_prolonged()
        # # INFO: Debug string
        # not_prolonged_users = [{
        # 	'balance': 0, 'telegramId': creatorId, 'lang': 'ru',
        # 	'tid': 3, 'tprice': 10, 'tlevel': 3, 'tnc': 100}]

        # отлючено, так как если пользователя нет, то число не совпадёт
        # how_many_prolonged = db.prolongUsers(tariff_period)
        db.prolong_users(tariff_period)
        # if len(prolonged_users) != how_many_prolonged:
        # 	sendErrorMessageToCreator(bot, "Не все пользователи продлены")
        # 	eprint("Users to prolong:", flush=True)
        # 	for pu in prolonged_users:
        # 		eprint(pu['telegramId'], flush=True)

        db.decrease_all_time_left()
        #  если не отключить, то можно накручивать рефералов, надо хранить
        # db.delete_payment_records_without_user()
        tariffs = db.getTariffs()
        db.close()

        tariffs_by_id = {}
        for tariff in tariffs:
            tariffs_by_id[tariff['id']] = tariff

        lang = 'no_lang'
        for pu in prolonged_users:
            if pu['telegramId']:
                if lang != pu['lang']:
                    lang = pu['lang']

                message_base = get_message("tariff_prolonged_by_daemon", lang) + "\n\n"

                balance = int(pu['balance']) - int(pu['tprice'])

                tariff_str = decode_tariff(pu['tlevel'], lang)
                message = message_base + get_tariff_info_message(
                    tariff_str, balance, pu['tprice'], tariff_period, pu['tnc'], lang)
                outer_sender(pu['telegramId'], [{'type': 'text', 'text': message}])

        lang = 'no_lang'
        for npu in not_prolonged_users:
            if lang != npu['lang']:
                lang = npu['lang']
                message_base = get_message(
                    "tariff_cannot_be_prolonged_by_daemon", lang) + "\n\n"

            balance = int(npu['balance'])

            tariff_str = decode_tariff(npu['tlevel'], lang)
            # срок действия вышел + описание текущих условий
            message = message_base + get_tariff_info_message(
                tariff_str, balance, npu['tprice'], 0, 0, lang)

            # описание тарифа
            message += "\n\n" + get_message("your_tariff_description", lang) + ":\n" \
                       + get_tariff_description_and_button_text(
                tariffs_by_id[npu['tid']], {'id': npu['tid']}, lang,
                show_tariff_level_text=False)['text']
            try:
                outer_sender(npu['telegramId'], [{'type': 'text', 'text': message}])
            except Exception as e:
                logger.err(e)
