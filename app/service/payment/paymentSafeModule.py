import math
from typing import TypedDict, Tuple

from app.i18n.messages import get_message
from config import db_path
from config import (
    tariff_ref_period, tariff_ref_no_subscription_period,
    tariff_ref_notifies, tariff_ref_sub_period, tariff_ref_invitee_period,
    tariff_new_user_period, tariff_secret_start_cmd_period,
    tariff_period)
from db.sqliteAdapter import SQLighter


def prepare_price(price, ensurement: float = 0) -> float:
    prepared_price: float = round((int(price) + int(ensurement)) / 100, 2)
    return prepared_price


def money_text(cents, ensurement: float = 0) -> str:
    """Dollars for a message: 5, 4.50, 0 (prepare_price printed 5.0 and 0.0)."""
    value = prepare_price(cents, ensurement)
    return "%d" % value if value == int(value) else "%.2f" % value


def days_left_text(time_left) -> str:
    """Whole days left on a plan, for our HTML messages.

    Under a day is "&lt;1": a bare "<1" is a tag to Telegram, which refused the
    whole menu on a trial's last day (2026-10-27) and the payment notices with it.
    """
    if 0 < time_left < 24:
        return "&lt;1"
    return str(math.floor(time_left / 24))


def is_subscription_active(subscription):
    return subscription is not None and (subscription['tariff_id'] > 0 and subscription['time_left'] > 0)


def get_tariff_info_message(
        tariff_str, balance, price, time_left, notify_left, language_code):
    tariff_info_message = "<b>" + \
                          get_message("curr_tariff", language_code) + ": " + tariff_str + \
                          "</b>" + "\n"
    tariff_info_message += "<b>" + \
                           (get_message(
                               "curr_balance", language_code) % money_text(balance)) + "</b>"
    if balance < price:
        tariff_info_message += " " + \
            get_message("not_enough_for_renewal", language_code) \
            % money_text(price - balance, 0.5)
    tariff_info_message += "\n"
    if time_left is not None:
        tariff_info_message += get_message("days_left", language_code) % days_left_text(time_left)
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


class PaymentApplyResult(TypedDict):
    result_mode: int
    current_tariff: TariffParams
    current_subscription: dict


def apply_balance_replenishment(db: SQLighter, user, amount_cents: int) -> PaymentApplyResult:
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
        current_tariff = {'id': 0, 'level': 0, 'price': 0, 'notify_count': 0, 'compression': 0}

    if current_subscription is None or current_subscription['id'] == 0:
        balance = int(amount_cents)
        db.subscribeUserToTariffByTg(chat_tg_id, 0, balance, 0, 0)
        current_subscription = {
            'balance': balance,
            'time_left': 0,
            'notify_count': 0
        }
        result_mode = 0

    elif current_subscription['time_left'] > 0:
        new_user_balance = current_subscription['balance'] + int(amount_cents)
        db.subscribeUserToTariffByTg(
            chat_tg_id, current_subscription['tariff_id'],
            new_user_balance, current_subscription['time_left'],
            current_subscription['notify_count'])
        current_subscription['balance'] = new_user_balance
        result_mode = 1

    else:
        new_user_balance = current_subscription['balance'] + int(amount_cents)
        if current_tariff['price'] != 0:
            if new_user_balance >= current_tariff['price']:
                new_user_balance -= current_tariff['price']
                db.subscribeUserToTariffByTg(
                    chat_tg_id, current_subscription['tariff_id'],
                    new_user_balance, tariff_period,
                    current_tariff['notify_count'])
                current_subscription['balance'] = new_user_balance
                current_subscription['time_left'] = tariff_period
                current_subscription['notify_count'] = current_tariff['notify_count']
                result_mode = 2
            else:
                db.subscribeUserToTariffByTg(
                    chat_tg_id, current_subscription['tariff_id'],
                    new_user_balance, current_subscription['time_left'], 0)
                current_subscription['balance'] = new_user_balance
                current_subscription['notify_count'] = 0
                result_mode = 3
        else:
            db.subscribeUserToTariffByTg(
                chat_tg_id, current_subscription['tariff_id'],
                new_user_balance, current_subscription['time_left'], 0)
            current_subscription['balance'] = new_user_balance
            result_mode = 0

    if result_mode == 2:
        from app.jobs.relay_remind import clear_relay_d3_sent
        clear_relay_d3_sent(chat_tg_id)

    return {
        'result_mode': result_mode,
        'current_tariff': current_tariff,
        'current_subscription': current_subscription
    }


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


def notify_count_after_referral(notify_count, bonus) -> int:
    """Referral bonus on top of the current notify_count; -1 is unlimited and stays so."""
    if int(notify_count) == -1:
        return -1
    return int(notify_count) + int(bonus)


def award_referrer_for_payment(invitee_tg_id):
    """(referrer chat id, message) for an invitee's payment, or (None, None).

    Once per invitee, whatever the pay method: the referrer is taken off the
    invitee (claim_referrer) before the award, so a webhook retry or a second
    payment awards nothing. A crash in between loses one bonus, never doubles it.
    """
    db = SQLighter(db_path)
    try:
        refer_tg_id = db.claim_referrer(invitee_tg_id)
    finally:
        db.close()
    if refer_tg_id is None:
        return None, None
    return refer_tg_id, giveAward(refer_tg_id, invitee_tg_id, 'replenished')


# Дать подарок за приглашение или начало использование
# A first command other than /start (/search, /menu from the bot's menu) creates
# the user with no plan; podcasts they subscribe to before /start used to make a
# newcomer "returning" (tariff_secret_start_cmd_period, 2 days instead of 14).
NEWCOMER_HOURS = 24


def _joined_recently(db, telegram_id) -> bool:
    """The user row is younger than NEWCOMER_HOURS (users.created_at; NULL for old users)."""
    row = db.cursor.execute(
        "SELECT created_at >= datetime('now', ?) FROM users WHERE telegramId = ?",
        ('-%d hours' % NEWCOMER_HOURS, str(telegram_id))).fetchone()
    return bool(row and row[0])


def giveAward(refer_tg_id, refered_tg_id, mode, invited=False):
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
                notify_count_after_referral(
                    current_subscription['notify_count'], tariff_ref_notifies))
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

    # новым пользователям — подписка
    elif mode == 'new':
        pc_count = db.select_users_subs_count(refer_tg_id)

        if pc_count == 0 or _joined_recently(db, refer_tg_id):
            on_period = tariff_new_user_period
            if invited:
                # a friend's link: the welcome plan is longer
                on_period += tariff_ref_invitee_period
                message += get_message("award_welcome_invited", language_code).format(
                    days=tariff_ref_invitee_period // 24) + "\n\n"
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
