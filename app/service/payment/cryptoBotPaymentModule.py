import json

from app.controller.general.notify import notify
import config
from app.routes.message_tools import go_back_inline_button, go_back_inline_markup
from lib.telegram.general.message_master import render_messages, InlineButtonData
from app.i18n.messages import get_message, emojiCodes
from app.repository.storage import storage
from app.service.payment.paymentModule import (
    decode_tariff, get_tariff_info_message, get_tariff_description_and_button_text,
    get_tariff_params_by_tg, prepare_price, pretty_float_string)
from config import crypto_bot_api_key, crypto_bot_api_key_test
from config import db_path
from db.sqliteAdapter import SQLighter
from lib.api.payment.cryptoBotApi import CryptoBotApi
from app.routes.ptypes import ControllerParams

if config.server:
    cryptoBotApi = CryptoBotApi(crypto_bot_api_key)
else:
    cryptoBotApi = CryptoBotApi(crypto_bot_api_key_test, "testnet")


# страница оплаты через криптобот с выбором валюты
def open_subscription_page(data: ControllerParams):
    tariff, balance, time_left, notify_left = get_tariff_params_by_tg(data['chat_id'])

    sub_msg = get_sub_message(data['language_code'], tariff['level'], tariff['price'], balance, time_left, notify_left)

    render_messages(data['chat_id'], [{
        'type': 'text', 'text': sub_msg['message'], 'reply_markup': sub_msg['markup'],
        'disable_web_page_preview': True}])


def get_sub_message(language_code, tariff_lvl, tariff_price, balance, time_left, notify_left):
    message_text = "<b>" + get_message("bot_sub_page_header", language_code) + "</b>\n\n"
    message_text += get_message("bot_sub_cryptobot_page_body", language_code) + "\n\n"

    tariff_str = decode_tariff(tariff_lvl, language_code)
    message_text += get_tariff_info_message(
        tariff_str, balance, tariff_price, time_left, notify_left, language_code)

    menu_key_board: list[list[InlineButtonData]] = []

    asset_row: list[InlineButtonData] = []
    for asset in cryptoBotApi.AVAILABLE_ASSETS:
        asset_row.append({'text': cryptoBotApi.ASSETS[asset],
                          'callback_data': {'tp': 'bs_crbot_input', 'asset': asset}})
        if len(asset_row) == 2:  # 2 coins per row
            menu_key_board.append(asset_row)
            asset_row = []
    if len(asset_row) != 0:
        menu_key_board.append(asset_row)

    menu_key_board.append([go_back_inline_button(language_code)])

    result = {
        "message": message_text,
        "markup": menu_key_board
    }
    return result


def is_test_payment(payer_chat_id: int):
    return payer_chat_id == config.creatorId


# страница пополнения баланса
def open_amount_input_page(data: ControllerParams):
    tariff, balance, time_left, notify_left = get_tariff_params_by_tg(data['chat_id'])

    storage.set_user_state_data(data['chat_id'], 'bs_crbot_input', data['united_data'])

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

    # First page open, show amounts
    if summa is None:
        tariff_payment_message = get_amount_input_message(
            data['language_code'], tariff['id'], balance, time_left, notify_left)

        render_messages(data['chat_id'], [{
            'type': 'text', 'text': tariff_payment_message['message'],
            'reply_markup': tariff_payment_message['markup']}])

        return

    try:
        summa_cents = round(float(summa) * 100)
    except ValueError:
        notify(data['callback'], data['message'],
               get_message('notANumber', data['language_code']), alert=True)
        return False

    if summa_cents < 1:
        notify(data['callback'], data['message'],
               get_message('amountTooSmall', data['language_code']), alert=True)
        return False

    generated_data = generate_subscription_link(
        data['chat_id'], data['language_code'], summa_cents, data['united_data']['asset'], test_mode)

    if "error" in generated_data:
        if generated_data["error"] == "AMOUNT_TOO_SMALL":
            notify(data['callback'], data['message'],
                   get_message('amountTooSmall', data['language_code']), alert=True)
        else:
            notify(data['callback'], data['message'],
                   get_message('parsingError', data['language_code']), alert=True)
        return False

    render_messages(data['chat_id'], [{
        'type': 'text', 'text': generated_data['message'],
        'reply_markup': go_back_inline_markup(data['language_code']), 'disable_web_page_preview': True}])


def get_amount_input_message(language_code, tariff_id, balance, time_left, notify_left):
    message_text = get_message("bot_sub_cryptobot_amount_input", language_code) + "\n\n"

    menu_keyboard: list[list[InlineButtonData]] = []

    db_users = SQLighter(db_path)
    tariffs = db_users.getTariffs()
    db_users.close()

    tariff_lvl = 0
    tariff_price = 0
    for tariff in tariffs:
        if tariff['id'] == tariff_id:
            tariff_lvl = tariff['level']
            tariff_price = tariff['price']

        tariff_texts = get_tariff_description_and_button_text(
            tariff, {'id': tariff_id}, language_code)

        # сообщение
        message_text += tariff_texts["text"] + "\n\n"

        # кнопки
        cbd = {"tp": "bs_crbot_input", "v": prepare_price(tariff['price'])}
        button_text = str(prepare_price(tariff['price'])) + emojiCodes.get('dollar', '')
        if tariff_id == tariff['id']:
            button_text += " (" + get_message("curr_tariff", language_code).lower() + ")"
        menu_keyboard.append([{'text': button_text, 'callback_data': cbd}])

    tariff_str = decode_tariff(tariff_lvl, language_code)
    message_text += get_tariff_info_message(tariff_str, balance, tariff_price, time_left, notify_left, language_code)

    menu_keyboard.append([go_back_inline_button(language_code)])

    result = {
        "message": message_text,
        "markup": menu_keyboard
    }
    return result


def generate_subscription_link(
        chat_id, language_code, summa_cents, asset, test_mode=False):
    exchange_rate = cryptoBotApi.getExchangeRate(asset)

    if exchange_rate is None:
        return {"error": ""}

    summa = prepare_price(summa_cents)

    exchange_rate_usd = float(exchange_rate['USD'])
    asset_amount = summa / exchange_rate_usd

    payload = {"tgid": chat_id, "amount": summa_cents}
    if not config.server or test_mode:
        payload["net"] = "testnet"
        local_crypto_bot_api = CryptoBotApi(crypto_bot_api_key_test, "testnet")
    else:
        local_crypto_bot_api = cryptoBotApi

    try:
        invoice_data = local_crypto_bot_api.createInvoice(
            asset, asset_amount,
            payload=json.dumps(payload))
    except LookupError as e:
        try:
            error = json.loads(str(e))
            return {"error": error["api_error"]["name"]}
        except Exception:
            return {"error": ""}

    payment_link = invoice_data['pay_url']

    asset_amount = pretty_float_string(asset_amount)

    message = get_message(
        "cryptobot_generated_link_page", language_code).format(
        summa=summa, asset=asset, assetAmount=asset_amount,
        exchangeRateUSD=exchange_rate_usd, paymentLink=payment_link)

    return {"message": message}
