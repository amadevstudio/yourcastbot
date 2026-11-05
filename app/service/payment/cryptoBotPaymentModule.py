import json

from app.controller.general.notify import notify
import config
from app.routes.message_tools import go_back_inline_button
from lib.telegram.general.message_master import render_messages, InlineButtonData
from app.i18n.messages import get_message
from app.repository.storage import storage
from app.service.payment.paymentModule import (
    decode_tariff, get_tariff_info_message, get_tariff_description_and_button_text,
    get_tariff_params_by_tg, prepare_price)
from app.service.payment.paymentSafeModule import money_text
from config import crypto_bot_api_key, crypto_bot_api_key_test
from config import db_path
from db.sqliteAdapter import SQLighter
from lib.api.payment.cryptoBotApi import CryptoBotApi
from app.routes.ptypes import ControllerParams
from lib.tools.logger import logger

if config.server:
    cryptoBotApi = CryptoBotApi(crypto_bot_api_key)
else:
    cryptoBotApi = CryptoBotApi(crypto_bot_api_key_test, "testnet")


# A CryptoBot invoice is in dollars: the payer picks the coin in CryptoBot
# (any it accepts), so the bot keeps no rates. Converting by getExchangeRates
# failed for a coin without a USD rate (USDC, 2026-11-04: every amount was
# "parsing error"). A plan's button carries the plan (`pl`): with no plan
# running the payment turns it on, as a Stars invoice does
# (applyPaymentReplenishmentOnce planId); a typed amount tops the balance up.
FIAT = 'USD'


# страница оплаты через криптобот: планы и своя сумма
def open_subscription_page(data: ControllerParams):
    tariff, balance, time_left, notify_left = get_tariff_params_by_tg(data['chat_id'])
    page = get_amount_input_message(
        data['language_code'], tariff['id'], balance, time_left, notify_left)
    render_messages(data['chat_id'], [{
        'type': 'text', 'text': page['message'], 'reply_markup': page['markup'],
        'disable_web_page_preview': True}])


def is_test_payment(payer_chat_id: int):
    return payer_chat_id == config.creatorId


# страница пополнения баланса: своя сумма текстом или кнопка плана
def open_amount_input_page(data: ControllerParams):
    storage.set_user_state_data(data['chat_id'], 'bs_crbot_input', data['united_data'])

    plan_id = None
    if data['callback'] is not None:
        summa = data['united_data'].get('v', None)
        plan_id = data['united_data'].get('pl', None)
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

    # "Another amount" (or a coin button of an old page): the amount is typed here
    if summa is None:
        render_messages(data['chat_id'], [{
            'type': 'text', 'text': get_message("bot_sub_cryptobot_amount_input", data['language_code']),
            'reply_markup': [[go_back_inline_button(data['language_code'])]]}])

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
        data['chat_id'], data['language_code'], summa_cents, test_mode, plan_id=plan_id)

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
        'reply_markup': generated_data['markup'], 'disable_web_page_preview': True}])


def get_amount_input_message(language_code, tariff_id, balance, time_left, notify_left):
    """The plans with their prices as buttons (each its plan's invoice) and "Another amount" (typed, a top-up)."""
    message_text = get_message("cryptobotPlans", language_code) + "\n\n"

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
        cbd = {"tp": "bs_crbot_input", "v": prepare_price(tariff['price']), "pl": tariff['id']}
        button_text = get_message("tariff_lvl" + str(tariff['level']), language_code) \
            + " – $" + money_text(tariff['price'])
        if tariff_id == tariff['id']:
            button_text += " (" + get_message("curr_tariff", language_code).lower() + ")"
        menu_keyboard.append([{'text': button_text, 'callback_data': cbd}])

    tariff_str = decode_tariff(tariff_lvl, language_code)
    message_text += get_tariff_info_message(tariff_str, balance, tariff_price, time_left, notify_left, language_code)

    menu_keyboard.append([{'text': get_message('cryptobotOtherAmount', language_code),
                           'callback_data': {'tp': 'bs_crbot_input'}}])
    menu_keyboard.append([go_back_inline_button(language_code)])

    result = {
        "message": message_text,
        "markup": menu_keyboard
    }
    return result


def invoice_params(chat_id, summa_cents, plan_id=None, test_mode=False) -> dict:
    """createInvoice's arguments: dollars, any coin, what the webhook credits in the payload."""
    payload = {"tgid": chat_id, "amount": summa_cents}
    if plan_id:
        payload["v"] = int(plan_id)
    if test_mode:
        payload["net"] = "testnet"
    return {"asset": None, "amount": "%.2f" % (summa_cents / 100), "currency_type": "fiat", "fiat": FIAT,
            "payload": json.dumps(payload)}


def generate_subscription_link(
        chat_id, language_code, summa_cents, test_mode=False, plan_id=None):
    test_mode = test_mode or not config.server
    local_crypto_bot_api = CryptoBotApi(crypto_bot_api_key_test, "testnet") if test_mode else cryptoBotApi

    try:
        invoice_data = local_crypto_bot_api.createInvoice(
            **invoice_params(chat_id, summa_cents, plan_id, test_mode))
    except LookupError as e:
        try:
            error = json.loads(str(e))
            return {"error": error["api_error"]["name"]}
        except Exception:
            return {"error": ""}
    except Exception as e:  # no network, a timeout, an answer that is not JSON
        logger.warn("cryptobot invoice:", type(e).__name__, e)
        return {"error": ""}

    message = get_message("cryptobotInvoice", language_code).format(summa=money_text(summa_cents))
    # pay_url is the old name of bot_invoice_url (Crypto Pay API)
    link = invoice_data.get('bot_invoice_url') or invoice_data['pay_url']
    markup = [[{'text': get_message('pay', language_code), 'url': link}],
              [go_back_inline_button(language_code)]]
    return {"message": message, "markup": markup}
