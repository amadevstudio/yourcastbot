from telebot import types  # type: ignore

from app.controller.general.notify import notify
from app.routes.message_tools import go_back_inline_markup, go_back_inline_button
from lib.telegram.general.message_master import render_messages, InlineButtonData
from app.i18n.messages import get_message
from app.service.payment.paymentSafeModule import \
    prepare_price, get_tariff_info_message, get_tariff_params_by_tg, decode_tariff
from config import creatorId
from config import db_path, tariff_period
from config import botName
from db.sqliteAdapter import SQLighter
from app.routes.ptypes import ControllerParams
from telebot import types  # type: ignore

from app.controller.general.notify import notify
from app.i18n.messages import get_message
from app.routes.message_tools import go_back_inline_markup, go_back_inline_button
from app.routes.ptypes import ControllerParams
from app.service.payment.paymentSafeModule import \
    prepare_price, get_tariff_info_message, get_tariff_params_by_tg, decode_tariff
from config import botName
from config import creatorId
from config import db_path, tariff_period
from db.sqliteAdapter import SQLighter
from lib.telegram.general.message_master import render_messages, InlineButtonData


def open_donate_page(data: ControllerParams):
    donate_msg = get_donate_message(data['language_code'])
    render_messages(data['chat_id'], [{
        'type': 'text', 'text': donate_msg, 'reply_markup': go_back_inline_markup(data['language_code'])}])


def get_donate_message(lang_code):
    message = ""
    message += "<b>" + get_message("donate", lang_code) + "</b>\n\n"
    message += get_message("donateMessage", lang_code) + "\n\n"
    message += get_message("botDescr", lang_code) + "\n\n"

    return message


# def generateDonateLink(bot, message):
#     try:
#         float(message.text)
#     # summa = float(message.text)
#     except Exception:
#         answer = bot.send_message(
#             chat_id=message.chat.id,
#             text=get_message("notANumber", message.from_user.language_code),
#             parse_mode="Markdown")
#         return
#
#     # link = generatePaymentLink(
#     # 	message.chat.id, summa, message.from_user.language_code)
#
#     # goBackKeyboard = types.InlineKeyboardMarkup()
#     # goBackKeyboard.add(types.InlineKeyboardButton(
#     # 	text=get_message("goBack", message.from_user.language_code),
#     # 	callback_data="{\"tp\": \"bck\"}"))
#
#     # answer = bot.send_message(
#     # 	chat_id=message.chat.id,
#     # 	text=get_message(
#     # 		"paymentLinkMessage", message.from_user.language_code) + link,
#     # 	reply_markup=goBackKeyboard)
#     answer = bot.send_message(
#         chat_id=message.chat.id,
#         text=get_message('donate_page_body', message.from_user.language_code),
#         parse_mode='markdown')
#     storage.set_user_last_text(message.chat.id, answer.message_id)
#
#
# def generatePaymentLink(user_id, sum_count, culture):
#     link = 'https://auth.robokassa.ru/Merchant/Index.aspx?'
#
#     invId = '0'  # max 2^31 - 1
#     # invId = str(round(time.time()))# + str(user_id)
#
#     culture = 'Culture=' + culture + '&'
#     encoding = 'Encoding=utf-8' + '&'
#     description = 'Description=' + str(user_id) + '&'
#     outSum = str(sum_count)
#
#     # shp_item = ':Shp_item=1' # not works with that
#
#     res = (
#             payment_login + ':' + outSum + ':' + invId + ':' + payment_p1)  # + shp_item)
#
#     hash_object = hashlib.md5(res.encode())
#     signatureValue = 'SignatureValue=' + hash_object.hexdigest()
#
#     link += (
#             'MerchantLogin=' + payment_login + '&' + 'InvId=' + invId + '&' + culture
#             + encoding + description + 'OutSum=' + outSum + '&' + signatureValue)
#
#     return link


# --------------------
# service subscription functions


# subscription messages and logic

def open_subscription_page(data: ControllerParams):
    tariff, balance, time_left, notify_left = get_tariff_params_by_tg(data['chat_id'])

    sub_msg = get_sub_message(
        data['chat_id'], data['language_code'], tariff['level'],
        tariff['price'], balance, time_left, notify_left)

    render_messages(data['chat_id'], [{
        'type': 'text', 'text': sub_msg['message'], 'reply_markup': sub_msg['markup'],
        'disable_web_page_preview': True}])


def get_sub_message(utgid, language_code, tariff_lvl, tariff_price, balance, time_left, notify_left):
    message_text = "<b>" + get_message("bot_sub_page_header", language_code) + "</b>\n\n"
    message_text += get_message("donate_page_body", language_code) + "\n\n"
    message_text += get_message("donate_page_referral", language_code) + "\n" \
                    + "t.me/" + botName + "?start=" + str(utgid) + "\n\n"

    tariff_str = decode_tariff(tariff_lvl, language_code)
    message_text += get_tariff_info_message(
        tariff_str, balance, tariff_price, time_left, notify_left, language_code)

    menu_keyboard: list[list[InlineButtonData]] = [
        [{'text': get_message("tariffs", language_code), 'callback_data': {'tp': 'bs_trfs'}}],
        [{'text': get_message("payViaPatreon", language_code), 'callback_data': {'tp': 'bs_patr'}}],
        [{'text': get_message("payViaCryptoBot", language_code), 'callback_data': {'tp': 'bs_cryptobot'}}],
        # [{'text': get_message("payViaRobokassa", language_code), 'callback_data': {'tp': 'bs_robokassa'}}],
        [go_back_inline_button(language_code)]]

    if utgid == creatorId:
        menu_keyboard.append(
            [{'text': get_message("payViaRobokassa", language_code), 'callback_data': {'tp': 'bs_robokassa'}}])

    result = {
        "message": message_text,
        "markup": menu_keyboard
    }
    return result


def open_subscription_tariffs_page(data: ControllerParams):
    tariff, balance, time_left, notify_left = get_tariff_params_by_tg(data['chat_id'])

    tariffs_sub_msg = get_tariffs_sub_message(data['language_code'], tariff['id'], balance, time_left, notify_left)

    render_messages(data['chat_id'], [{
        'type': 'text',
        'text': tariffs_sub_msg['message'],
        'reply_markup': tariffs_sub_msg['markup']
    }])


def get_tariffs_sub_message(language_code, tariff_id, balance, time_left, notify_left):
    message_text = get_message("bot_sub_trfs_page", language_code) + "\n\n"

    menu_keyboard: list[list[InlineButtonData]] = []

    db_users = SQLighter(db_path)
    tariffs = db_users.getTariffs()
    db_users.close()
    # yes_msg = get_message("yes", language_code)
    # no_msg = get_message("no", language_code)
    tariff_lvl = 0
    tariff_price = 0
    for tariff in tariffs:
        if tariff['id'] == tariff_id:
            tariff_lvl = tariff['level']
            tariff_price = tariff['price']

        tariff_texts = get_tariff_description_and_button_text(
            tariff, {'id': tariff_id}, language_code)

        message_text += tariff_texts['text'] + "\n\n"

        menu_keyboard.append(
            [{'text': tariff_texts['button_text'], 'callback_data': {"tp": "bs_trf_v", "v": tariff['id']}}])

    tariff_str = decode_tariff(tariff_lvl, language_code)
    message_text += get_tariff_info_message(tariff_str, balance, tariff_price, time_left, notify_left, language_code)

    menu_keyboard.append([{
        'text': ('* ' if tariff_lvl == 0 else '') + get_message('disable', language_code),
        'callback_data': {'tp': 'bs_trf_v', 'v': 0}}])

    menu_keyboard.append([go_back_inline_button(language_code)])

    result = {
        "message": message_text,
        "markup": menu_keyboard
    }
    return result


def get_tariff_description_and_button_text(
        tariff, current_tariff, language_code, show_tariff_level_text=True):
    text = ""

    if show_tariff_level_text:
        text = "<b>" + get_message("tariff_lvl" + str(tariff['level']), language_code) + "</b>\n"

    text += get_message("trf_descr_tmplt", language_code) \
            % (
                str(prepare_price(tariff['price'])),
                (
                    str(tariff['notify_count'])
                    if tariff['notify_count'] != -1
                    else "<b>" + get_message(
                        "unlimited", language_code).lower() + "</b>"),
                (
                    ("<b>" + get_message("yes", language_code) + "</b>")
                    if tariff['channel_control'] else get_message("no", language_code)))
    button_text = (
            ("* " if current_tariff['id'] == tariff['id'] else "")
            + get_message("tariff_lvl" + str(tariff['level']), language_code))

    return {"text": text, "button_text": button_text}


# выбран тариф
def choose_bot_subscription_tariff(data: ControllerParams):
    db = SQLighter(db_path)
    # tariffs = db.getTariffs()
    current_subscription = db.getUserSubscriptionByTg(data['chat_id'])
    if current_subscription is None or current_subscription['tariff_id'] == 0:
        current_tariff = {'id': 0, 'price': 0, 'level': 0, 'notify_count': 0}
    else:
        current_tariff = db.getTariffById(current_subscription['tariff_id'])
    if data['united_data']['v'] == 0:
        desire_tariff = {'id': 0, 'price': 0, 'level': 0, 'notify_count': 0}
    else:
        desire_tariff = db.getTariffById(data['united_data']['v'])
    db.close()

    if desire_tariff is None or current_tariff is None:
        notify(data['callback'], data['message'], get_message('error', data['language_code']), alert=True)
        return False

    after_action_keyboard: list[list[InlineButtonData]] = [[go_back_inline_button(data['language_code'])]]

    # текущий тариф
    if int(data['united_data']['v']) == int(current_tariff['id']):
        # остались дни или без подписки
        if (
                (current_subscription is not None
                 and current_subscription['time_left'] is not None
                 and int(current_subscription['time_left']) > 0)
                or desire_tariff['id'] == 0):

            notify(
                data['callback'], data['message'],
                get_message('youAlreadySubscribedOnTariff', data['language_code']), alert=True)
            return False
        else:
            if current_subscription is None:
                current_subscription = {'balance': 0}
            render_messages(data['chat_id'], [{
                'type': 'text',
                'text': get_message(
                    'tariffActivatedNotEnoughMoney',
                    data['language_code']) % str(desire_tariff['price'] - current_subscription['balance']),
                'reply_markup': after_action_keyboard
            }])
            return

    else:
        # если сейчас есть подписка
        if current_subscription is not None and current_subscription['time_left'] is not None:

            # и текущий тариф дешевле
            if current_tariff['price'] < desire_tariff['price']:
                price_diff = int((current_subscription['time_left'] / tariff_period)
                                 * (desire_tariff['price'] - current_tariff['price']))
                # если не хватает баланса, чтобы подписаться
                if price_diff > int(current_subscription['balance']):
                    message_str = get_message("notEnoughMoneyToActivate", data['language_code']) \
                                  % str(prepare_price(price_diff - int(current_subscription['balance']), 0.5))
                    render_messages(data['chat_id'], [{
                        'type': 'text', 'text': message_str, 'reply_markup': after_action_keyboard}])
                    return
                else:
                    new_balance = int(current_subscription['balance']) - price_diff

            # но если текущий тариф дороже, то частичный возврат
            else:
                price_diff = int(
                    ((current_subscription['time_left'] - 1) / tariff_period)
                    * (current_tariff['price'] - desire_tariff['price']) / 2)
                new_balance = int(current_subscription['balance'])
                if price_diff > 0:
                    new_balance += price_diff

            # If new tariff notify_count is inf, set inf
            if desire_tariff['notify_count'] == -1:
                new_notify_count = -1
            # If current is inf, set new
            elif current_tariff['notify_count'] == -1:
                new_notify_count = desire_tariff['notify_count']
            # New notify count is distance between them
            else:  # desire_tariff['notify_count'] >= 0 and current_tariff['notify_count'] >= 0
                new_notify_count = int(
                    desire_tariff['notify_count']
                    - current_tariff['notify_count'] + current_subscription['notify_count'])
                if new_notify_count < 0:
                    new_notify_count = 0

            new_time_left = current_subscription['time_left']

        else:
            if current_subscription is not None:
                new_balance = current_subscription['balance']
                new_time_left = current_subscription['time_left']
                new_notify_count = current_subscription['notify_count']
            else:
                new_balance = 0
                new_time_left = 0
                new_notify_count = 0

        if new_time_left == 0:
            if new_balance > desire_tariff['price']:
                new_balance = new_balance - desire_tariff['price']
                new_time_left = tariff_period

        db = SQLighter(db_path)
        db.subscribeUserToTariffByTg(
            data['chat_id'], desire_tariff['id'], new_balance, new_time_left, new_notify_count)

        current_subscription = db.getUserSubscriptionByTg(data['chat_id'])
        current_tariff = db.getTariffById(current_subscription['tariff_id'])
        if current_tariff is None:
            current_tariff = {'id': 0, 'level': 0, 'price': 0}
        db.close()

        if current_subscription is not None \
                and int(data['united_data']['v']) == current_subscription['tariff_id']:

            message_str = get_message(
                "tariffSuccessChanged", data['language_code']) + "\n\n"
            tariff_str = decode_tariff(current_tariff['level'], data['language_code'])
            if current_subscription['time_left'] == 0:
                message_str += get_message("tariffNotActive", data['language_code']) + "\n\n"

            message_str += get_tariff_info_message(
                tariff_str, current_subscription['balance'], current_tariff['price'],
                current_subscription['time_left'], current_subscription['notify_count'],
                data['language_code'])
            render_messages(data['chat_id'], [{
                'type': 'text', 'text': message_str, 'reply_markup': after_action_keyboard}])
            return
        else:
            notify(data['callback'], data['message'], get_message('error', data['language_code']), alert=True)
            return False


# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# hour decreaser daemon


def pretty_float_string(number):
    max_digited = "{0:.16f}".format(number)
    length = len(max_digited)
    last_non_zero = 0
    for d in range(length):
        if max_digited[length - d - 1] != "0":
            break
        last_non_zero += 1
    return max_digited[:length - last_non_zero]
