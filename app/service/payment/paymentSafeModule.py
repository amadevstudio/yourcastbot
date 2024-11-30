import math
from typing import TypedDict, Tuple

from app.i18n.messages import get_message
from config import db_path
from config import (
    tariff_ref_period, tariff_ref_no_subscription_period,
    tariff_ref_notifies, tariff_ref_sub_period,
    tariff_new_user_period, tariff_secret_start_cmd_period)
from db.sqliteAdapter import SQLighter


def prepare_price(price, ensurement: float = 0) -> float:
    prepared_price: float = round((int(price) + int(ensurement)) / 100, 2)
    return prepared_price


def is_subscription_active(subscription):
    return subscription is not None and (subscription['tariff_id'] > 0 and subscription['time_left'] > 0)


def get_tariff_info_message(
        tariff_str, balance, price, time_left, notify_left, language_code):
    tariff_info_message = "<b>" + \
                          get_message("curr_tariff", language_code) + ": " + tariff_str + \
                          "</b>" + "\n"
    tariff_info_message += "<b>" + \
                           (get_message(
                               "curr_balance", language_code) % str(prepare_price(balance))) + "</b>"
    if balance < price:
        tariff_info_message += \
            get_message("not_enough_for_renewal", language_code) \
            % str(prepare_price(price - balance, 0.5))
    tariff_info_message += "\n"
    if time_left is not None:
        if 0 < time_left < 24:
            days_left_str = "<1"
        else:
            days_left_str = str(math.floor(time_left / 24))
        tariff_info_message += get_message("days_left", language_code) % days_left_str
    tariff_info_message += "\n"
    if notify_left is not None:
        if notify_left == -1:
            notify_left = get_message("unlimited", language_code)
        tariff_info_message += get_message("notify_left", language_code) % str(notify_left)

    return tariff_info_message


class TariffParams(TypedDict):
    id: int
    level: int
    price: int
    notify_count: int
    compression: int


def get_tariff_params_by_tg(telegram_id: int) -> Tuple[TariffParams, int, int, int]:
    db = SQLighter(db_path)
    subscription = db.getUserSubscriptionByTg(telegram_id)
    if subscription is None:
        subscription = {
            "tariff_id": 0, 'balance': 0, 'time_left': 0, 'notify_count': 0}
    tariff = db.getTariffById(subscription['tariff_id'])
    db.close()

    if tariff is None:
        tariff = {
            "id": 0, "level": 0, "price": 0, "notify_count": 0, "compression": 0}
    balance = subscription['balance']
    time_left = subscription['time_left']
    notify_left = subscription['notify_count']

    return tariff, balance, time_left, notify_left


def decode_tariff(tariff_lvl, language_code):
    if tariff_lvl == 0:
        tariff_str = get_message("not_selected", language_code)
    elif tariff_lvl == 1 or tariff_lvl == 2 or tariff_lvl == 3:
        tariff_str = get_message("tariff_lvl" + str(tariff_lvl), language_code)
    else:
        tariff_str = get_message("not_selected", language_code)

    return tariff_str


# Дать подарок за приглашение или начало использование
def giveAward(refer_tg_id, refered_tg_id, mode):
    if not mode:
        mode = 'reged'

    db = SQLighter(db_path)
    user = db.get_user_by_tg(refer_tg_id)

    if user is None:
        return None

    message = ""
    language_code = user['lang'] if user['lang'] is not None else 'en'

    # приглашённый начал пользоваться
    if mode == 'reged':
        current_subscription = db.getUserSubscriptionByTg(refer_tg_id)
        if current_subscription is None:
            extreme = db.getExtremeTariff('min')
            db.subscribeUserToTariffByTg(
                refer_tg_id, extreme['id'], 0,
                tariff_ref_no_subscription_period, extreme['notify_count'])
            # по вашей ссылке зарегался реферал, теперь у вас бронза
            message += get_message("award_without_s_new_user", language_code)
        else:
            db.subscribeUserToTariffByTg(
                refer_tg_id, current_subscription['tariff_id'],
                current_subscription['balance'],
                int(current_subscription['time_left']) + int(tariff_ref_period),
                int(current_subscription['notify_count'] + int(tariff_ref_notifies)))
            # по вышей ссылке зарегался, текущие условия улучшены
            message += get_message("award_with_s_new_user", language_code)

    # приглашённый купил подписку, refer_tg_id здесь — нового пользователя
    elif mode == 'replenished':
        current_subscription = db.getUserSubscriptionByTg(refer_tg_id)
        extreme = db.getExtremeTariff('max')
        if current_subscription is None:
            db.subscribeUserToTariffByTg(
                refer_tg_id, extreme['id'], 0,
                tariff_ref_sub_period, extreme['notify_count'])
            # реферал купил подписку, теперь у вас максимальный тариф на х дней
            message += get_message("award_without_s_subscribed", language_code)
        else:
            db.subscribeUserToTariffByTg(
                refer_tg_id, extreme['id'],
                current_subscription['balance'],
                int(current_subscription['time_left']) + int(tariff_ref_sub_period),
                extreme['notify_count'])
            # реферал купил подписку, тариф улучшен до максимального и продлён на х
            message += get_message("award_with_s_subscribed", language_code)
        db.user_clear_refer(refered_tg_id)

    # новым пользователям — подписка
    elif mode == 'new':
        pc_count = db.select_users_subs_count(refer_tg_id)

        if pc_count == 0:
            on_period = tariff_new_user_period
            message += get_message("award_welcome", language_code)
        else:
            on_period = tariff_secret_start_cmd_period
            message += get_message("secret_award_welcome", language_code)

        current_subscription = db.getUserSubscriptionByTg(refer_tg_id)

        if current_subscription is None:
            extreme = db.getExtremeTariff('max')

            db.subscribeUserToTariffByTg(
                refer_tg_id, extreme['id'], 0,
                on_period, extreme['notify_count'])

        else:
            db.close()
            return None
        # db.subscribeUserToTariffByTg(
        # 	refer_tg_id, extreme['id'],
        # 	current_subscription['balance'],
        # 	int(current_subscription['time_left']) + int(tariff_new_user_period),
        # 	extreme['notify_count'])
        # # реферал купил подписку, тариф улучшен до максимального и продлён на х
        # message += get_message("award_welcome", language_code)

    db.close()
    tariff, balance, time_left, notify_left = get_tariff_params_by_tg(refer_tg_id)
    tariff_str = decode_tariff(tariff['level'], language_code)
    message += "\n\n" + get_tariff_info_message(
        tariff_str, balance, tariff['price'], time_left, notify_left, language_code)

    return message
