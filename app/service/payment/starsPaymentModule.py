import asyncio
import datetime
import json
import math
import time
import uuid
from typing import TypedDict

from telebot import types
from telethon import TelegramClient
from telethon.sessions import MemorySession
from telethon.tl.functions.help import GetAppConfigRequest
from telethon.tl.types import JsonArray, JsonBool, JsonNull, JsonNumber, JsonObject, JsonString

import config
from agent.bot_telebot import bot
from app.controller.general.notify import notify
from app.i18n.messages import get_message
from app.routes.message_tools import go_back_inline_button
from app.routes.ptypes import ControllerParams
from app.service.payment.paymentModule import (
    decode_tariff, get_tariff_description_and_button_text)
from app.service.payment.paymentSafeModule import (
    get_tariff_info_message, get_tariff_params_by_tg, giveAward, prepare_price)
from config import db_path
from db.sqliteAdapter import SQLighter
from lib.telegram.general.message_master import InlineButtonData, outer_sender, render_messages
from lib.tools.logger import Logger

STARS_CURRENCY = "XTR"
STARS_SERVICE_TYPE = "telegramStars"
STARS_WITHDRAW_RATE_KEY = "stars_usd_withdraw_rate_x1000"
STARS_DEFAULT_WITHDRAW_RATE_X1000 = 1300
STARS_RATE_CACHE_TTL_SECONDS = 24 * 60 * 60

_stars_rate_x1000: int | None = None
_stars_rate_updated_at: float | None = None

logger = Logger(file="payment_stars")


class StarsRateUnavailable(Exception):
    pass


class StarsPayload(TypedDict):
    t: int
    b: int
    s: int
    r: int
    p: str


def _json_value_to_py(value):
    if isinstance(value, JsonObject):
        return {item.key: _json_value_to_py(item.value) for item in value.value}
    if isinstance(value, JsonArray):
        return [_json_value_to_py(item) for item in value.value]
    if isinstance(value, JsonString):
        return value.value
    if isinstance(value, JsonNumber):
        if value.value == int(value.value):
            return int(value.value)
        return value.value
    if isinstance(value, JsonBool):
        return value.value
    if isinstance(value, JsonNull):
        return None
    return None


async def _fetch_stars_withdraw_rate_x1000() -> int:
    client = TelegramClient(MemorySession(), config.app_api_id, config.app_api_hash)
    await client.connect()
    try:
        app_config = await client(GetAppConfigRequest(hash=0))
        config_data = _json_value_to_py(app_config.config)
        rate = int(config_data.get(STARS_WITHDRAW_RATE_KEY))
        if rate <= 0:
            raise ValueError("Telegram Stars withdraw rate is not positive")
        return rate
    finally:
        await client.disconnect()


def get_stars_withdraw_rate_x1000(force: bool = False, allow_fallback: bool = True) -> int:
    global _stars_rate_x1000, _stars_rate_updated_at

    now = time.time()
    if (
            not force
            and _stars_rate_x1000 is not None
            and _stars_rate_updated_at is not None
            and now - _stars_rate_updated_at < STARS_RATE_CACHE_TTL_SECONDS):
        return _stars_rate_x1000

    try:
        rate = asyncio.run(_fetch_stars_withdraw_rate_x1000())
        _stars_rate_x1000 = rate
        _stars_rate_updated_at = now
        return rate
    except Exception as e:
        logger.err(e)
        if allow_fallback:
            return _stars_rate_x1000 or STARS_DEFAULT_WITHDRAW_RATE_X1000
        raise StarsRateUnavailable("Telegram Stars withdraw rate is unavailable") from e

    return _stars_rate_x1000


def get_invoice_stars_withdraw_rate_x1000() -> int:
    return get_stars_withdraw_rate_x1000(allow_fallback=False)


def stars_for_balance(balance_amount: int, rate_x1000: int) -> int:
    return max(1, math.ceil(int(balance_amount) * 1000 / int(rate_x1000)))


def balance_for_stars(stars_amount: int, rate_x1000: int) -> int:
    return max(1, round(int(stars_amount) * int(rate_x1000) / 1000))


def pretty_stars_usd_rate(rate_x1000: int) -> str:
    return str(prepare_price(rate_x1000))


def create_payload(chat_id: int, balance_amount: int, stars_amount: int, rate_x1000: int) -> str:
    payload: StarsPayload = {
        "t": int(chat_id),
        "b": int(balance_amount),
        "s": int(stars_amount),
        "r": int(rate_x1000),
        "p": uuid.uuid4().hex[:16]
    }
    return json.dumps(payload, separators=(",", ":"))


def parse_payload(payload: bytes | str) -> StarsPayload | None:
    try:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        data = json.loads(payload)
        if not isinstance(data, dict):
            return None
        if not all(key in data for key in ["t", "b", "s", "r", "p"]):
            return None
        return {
            "t": int(data["t"]),
            "b": int(data["b"]),
            "s": int(data["s"]),
            "r": int(data["r"]),
            "p": str(data["p"])
        }
    except Exception:
        return None


def validate_precheckout_payload(
        payload: bytes | str, user_id: int, currency: str, total_amount: int
) -> tuple[bool, str | None]:
    data = parse_payload(payload)
    if data is None:
        return False, "Invalid payment payload"
    if currency != STARS_CURRENCY:
        return False, "Invalid payment currency"
    if int(user_id) != data["t"]:
        return False, "Invalid payment user"
    if int(total_amount) != data["s"]:
        return False, "Invalid payment amount"
    if data["s"] != stars_for_balance(data["b"], data["r"]):
        return False, "Invalid balance amount"
    return True, None


def open_subscription_page(data: ControllerParams):
    tariff, balance, time_left, notify_left = get_tariff_params_by_tg(data['chat_id'])
    rate_x1000 = get_stars_withdraw_rate_x1000()

    sub_msg = get_sub_message(
        data['language_code'], tariff['id'], tariff['level'],
        tariff['price'], balance, time_left, notify_left, rate_x1000)

    render_messages(data['chat_id'], [{
        'type': 'text', 'text': sub_msg['message'], 'reply_markup': sub_msg['markup'],
        'disable_web_page_preview': True}])


def get_sub_message(
        language_code, tariff_id, tariff_lvl, tariff_price,
        balance, time_left, notify_left, rate_x1000):
    message_text = "<b>" + get_message("bot_sub_page_header", language_code) + "</b>\n\n"
    message_text += get_message("bot_sub_stars_page_body", language_code).format(
        rate=pretty_stars_usd_rate(rate_x1000)) + "\n\n"

    menu_keyboard: list[list[InlineButtonData]] = []

    db_users = SQLighter(db_path)
    tariffs = db_users.getTariffs()
    db_users.close()

    for tariff in tariffs:
        tariff_texts = get_tariff_description_and_button_text(
            tariff, {'id': tariff_id}, language_code)
        message_text += tariff_texts["text"] + "\n\n"

        stars_amount = stars_for_balance(tariff['price'], rate_x1000)
        button_text = f"{tariff_texts['button_text']} — {stars_amount} ⭐"
        if tariff_id == tariff['id']:
            button_text += " (" + get_message("curr_tariff", language_code).lower() + ")"
        menu_keyboard.append([{
            'text': button_text,
            'callback_data': {'tp': 'bs_stars_pay', 'v': tariff['id']}
        }])

    tariff_str = decode_tariff(tariff_lvl, language_code)
    message_text += get_tariff_info_message(
        tariff_str, balance, tariff_price, time_left, notify_left, language_code)

    menu_keyboard.append([go_back_inline_button(language_code)])

    return {
        "message": message_text,
        "markup": menu_keyboard
    }


def send_invoice(data: ControllerParams):
    try:
        tariff_id = int(data['united_data'].get('v', 0))
    except Exception:
        notify(data['callback'], data['message'], get_message('parsingError', data['language_code']), alert=True)
        return False

    db_users = SQLighter(db_path)
    try:
        tariffs = db_users.getTariffs()
    finally:
        db_users.close()

    selected_tariff = next((tariff for tariff in tariffs if tariff['id'] == tariff_id), None)
    if selected_tariff is None or selected_tariff['price'] <= 0:
        notify(data['callback'], data['message'], get_message('parsingError', data['language_code']), alert=True)
        return False

    amount_balance = int(selected_tariff['price'])
    try:
        rate_x1000 = get_invoice_stars_withdraw_rate_x1000()
    except StarsRateUnavailable as e:
        logger.err(e)
        notify(data['callback'], data['message'], get_message('telegram_stars_invoice_error', data['language_code']), alert=True)
        return False
    amount_stars = stars_for_balance(amount_balance, rate_x1000)

    payload = create_payload(data['chat_id'], amount_balance, amount_stars, rate_x1000)
    title = get_message("telegram_stars_invoice_title", data['language_code'])
    description = get_message("telegram_stars_invoice_description", data['language_code']).format(
        balance=str(prepare_price(amount_balance)),
        stars=str(amount_stars),
        rate=pretty_stars_usd_rate(rate_x1000))

    try:
        bot.send_invoice(
            data['chat_id'],
            title,
            description,
            payload,
            "",
            STARS_CURRENCY,
            [types.LabeledPrice(label=title, amount=amount_stars)])
    except Exception as e:
        logger.err(e)
        notify(data['callback'], data['message'], get_message('telegram_stars_invoice_error', data['language_code']), alert=True)
        return False


def _payment_result_message(result, current_tariff, current_subscription, language_code):
    tariff_str = decode_tariff(current_tariff['level'], language_code)
    tariff_info_message = get_tariff_info_message(
        tariff_str, current_subscription['balance'],
        current_tariff['price'], current_subscription['time_left'],
        current_subscription['notify_count'], language_code)

    if result == 0:
        message = get_message('money_came', language_code) \
            + " " + get_message('subscribe_now', language_code) \
            + "\n\n" + tariff_info_message
    elif result == 1:
        if current_subscription['balance'] > current_tariff['price']:
            prolongation = get_message('enough_to_prolongation', language_code)
        else:
            prolongation = get_message('not_enough_to_prolongation', language_code)
        message = get_message('money_came', language_code) \
            + "\n" + prolongation \
            + "\n\n" + tariff_info_message
    elif result == 2:
        message = get_message('money_came', language_code) \
            + " " + get_message('tariff_prolonged', language_code) \
            + "\n\n" + tariff_info_message
    elif result == 3:
        message = get_message('money_came', language_code) \
            + " " + get_message('not_enough_to_prolongation', language_code) \
            + "\n\n" + tariff_info_message
    else:
        message = get_message('money_came', language_code)

    return message


def process_successful_payment(
        chat_id: int, currency: str, total_amount: int, payload: bytes | str,
        charge_id: str, provider_charge_id: str | None = None):
    ok, error = validate_precheckout_payload(payload, chat_id, currency, total_amount)
    if not ok:
        logger.err(error)
        return False

    payload_data = parse_payload(payload)
    if payload_data is None:
        return False

    db = SQLighter(config.db_path)
    try:
        user = db.get_user_by_tg(chat_id)
        if user is None:
            logger.err("Telegram Stars payment user not found", chat_id)
            return False

        result_data = db.applyPaymentReplenishmentOnce(
            user, STARS_SERVICE_TYPE, charge_id, datetime.datetime.now(),
            payload_data["b"], config.tariff_period,
            invoiceHash=f"{payload_data['p']}:{payload_data['r']}:{provider_charge_id or ''}",
            status="paid")
        if result_data['already_processed']:
            return False
    finally:
        db.close()

    language_code = user['lang'] if user['lang'] is not None else 'en'
    message = _payment_result_message(
        result_data['result_mode'], result_data['current_tariff'],
        result_data['current_subscription'], language_code)
    buttons = [[
        {'text': get_message('tariffs', language_code), 'callback_data': {'tp': 'bs_trfs'}},
        {'text': get_message('goBackMenu', language_code), 'callback_data': {'tp': 'menu'}}
    ]]
    outer_sender(chat_id, [{'type': 'text', 'text': message, 'reply_markup': buttons}])

    if user['ref_id'] is not None:
        award_message = giveAward(user['ref_id'], user['telegramId'], 'replenished')
        if award_message is not None:
            outer_sender(user['ref_id'], [{'type': 'text', 'text': award_message}])

    if config.server:
        outer_sender(config.creatorId, [{'type': 'text', 'text': "New income by Telegram Stars"}])

    return True
