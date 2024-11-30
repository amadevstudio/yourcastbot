import hashlib

from app.i18n.messages import get_message, emojiCodes
from app.routes.message_tools import go_back_inline_button, go_back_inline_markup
from app.routes.ptypes import ControllerParams
from app.service.payment.cryptoBotPaymentModule import is_test_payment
from app.service.payment.paymentSafeModule import get_tariff_params_by_tg, prepare_price, decode_tariff, \
    get_tariff_info_message
from config import db_path, server, creatorId, payment_p1_test, payment_p1, payment_login
from db.sqliteAdapter import SQLighter
from lib.telegram.general.message_master import render_messages, InlineButtonData
from lib.tools.logger import logger


def open_subscription_payment_page(data: ControllerParams):
    tariff, balance, time_left, notify_left = get_tariff_params_by_tg(data['chat_id'])

    tariff_payment_message = get_tariff_payment_message(data['language_code'], tariff['id'], balance, time_left,
                                                        notify_left)

    render_messages(data['chat_id'], [{
        'type': 'text', 'text': tariff_payment_message['message'], 'reply_markup': tariff_payment_message['markup'],
        'disable_web_page_preview': True}])


def get_tariff_payment_message(
        language_code, tariff_id, balance, time_left, notify_left):
    message_text = get_message('bot_sub_pmnt_page', language_code) + "\n\n"

    db_users = SQLighter(db_path)
    tariffs = db_users.getTariffs()
    db_users.close()

    menu_key_board: list[list[InlineButtonData]] = []

    tariff_lvl = 0
    tariff_price = 0
    for tariff in tariffs:
        if tariff['id'] == tariff_id:
            tariff_lvl = tariff['level']
            tariff_price = tariff['price']

        cbd = {'tp': 'bs_robokassa_input', 'v': prepare_price(tariff['price'])}
        button_text = str(prepare_price(tariff['price'])) + emojiCodes.get('dollar', '')
        if tariff_id == tariff['id']:
            button_text += \
                " (" + get_message("curr_tariff", language_code).lower() + ")"

        menu_key_board.append([{'text': button_text, 'callback_data': cbd}])

    tariff_str = decode_tariff(tariff_lvl, language_code)
    message_text += get_tariff_info_message(tariff_str, balance, tariff_price, time_left, notify_left, language_code)

    menu_key_board.append([go_back_inline_button(language_code)])

    result = {
        "message": message_text,
        "markup": menu_key_board
    }
    return result


# ссылка на оплату (отключено)
def generate_subscription_payment_message(data: ControllerParams):
    logger.debug("!!!!!!!!")
    if data['callback'] is not None:
        summa = data['united_data'].get('v', None)
        test_mode = False

    elif data['message'] is not None:
        summa = data['message'].text

        # 100 — реальный режим, t100 — тестовый
        if len(summa) > 1 and summa[0] == 't':
            summa = summa[1:]
            if is_test_payment(data['chat_id']):
                test_mode = True
            else:
                test_mode = False
        else:
            test_mode = False

    else:
        return False

    link = generate_subscription_link(
        data['chat_id'], summa,
        "ru" if data['language_code'] == "ru" else "en",
        test_mode)

    render_messages(data['chat_id'],[{
        'type': 'text', 'text': link, 'reply_markup': go_back_inline_markup(data['language_code']),
        'disable_web_page_preview': True}])


def generate_subscription_link(user_id, sum_count, culture, test_mode=False):
    link = 'https://auth.robokassa.ru/Merchant/Index.aspx?'

    inv_id = '0'  # max 2^31 - 1
    # invId = str(round(time.time()))# + str(user_id)

    if not server or (user_id == creatorId and test_mode):
        payment_h1 = payment_p1_test
        is_test = '&IsTest=1'
    else:
        payment_h1 = payment_p1
        is_test = ''

    culture = 'Culture=' + culture + '&'
    encoding = 'Encoding=utf-8' + '&'
    description = 'Description=' + str(user_id) + '&'

    out_sum = 'OutSum=' + str(sum_count) + '&'
    out_sum_cr = str(sum_count)

    out_sum_currency_cr = "USD"
    out_sum_currency = "OutSumCurrency=" + out_sum_currency_cr

    # параметры в алфавитном порядке!
    shp_summ_cr = 'Shp_summa=' + str(sum_count)
    shp_summ = '&' + shp_summ_cr
    shp_uid_cr = 'Shp_uid=' + str(user_id)
    shp_uid = '&' + shp_uid_cr

    res = (
            payment_login + ':' + out_sum_cr + ':' + inv_id + ":"
            + out_sum_currency_cr + ':' + payment_h1 + ":" + shp_summ_cr + ":" + shp_uid_cr)

    hash_object = hashlib.md5(res.encode())
    signatureValue = '&SignatureValue=' + hash_object.hexdigest()

    link += (
            'MerchantLogin=' + payment_login + '&' + 'InvId=' + inv_id + '&'
            + culture + encoding + description + out_sum + out_sum_currency + shp_summ
            + shp_uid + signatureValue + is_test)

    return link
