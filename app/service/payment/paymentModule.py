from telebot import types  # type: ignore

from app.controller.general.notify import notify
from app.routes.message_tools import go_back_inline_markup, go_back_inline_button
from lib.telegram.general.message_master import render_messages, InlineButtonData
from app.i18n.messages import get_message
from app.service.payment.paymentSafeModule import \
    prepare_price, get_tariff_info_message, get_tariff_params_by_tg, decode_tariff
from config import creatorId
from config import db_path, tariff_period
from db.sqliteAdapter import SQLighter
from app.routes.ptypes import ControllerParams
from telebot import types  # type: ignore

from app.controller.general.notify import notify
from app.i18n.messages import get_message
from app.routes.message_tools import go_back_inline_markup, go_back_inline_button
from app.routes.ptypes import ControllerParams
from app.service.ai import paid_models
from app.service.payment import referral, stars_subscription
from app.service.payment.paymentSafeModule import \
    days_left_text, money_text, get_tariff_info_message, get_tariff_params_by_tg, decode_tariff
from app.service.payment.offers import BUNDLES_CALLBACK, bundle_discount_back, longest_bundle, settle_bundles
from app.service.payment.storefront import (
    once_pay_rows, tariffs_for_change_plan, subscription_pay_rows)
from app.service.plan import channels as channel_plan, features
from config import creatorId
from config import db_path, tariff_period
from db.sqliteAdapter import SQLighter
from db import plan_grants
from db.tariff_rows import paid_for_days
from lib.telegram.general.message_master import render_messages, InlineButtonData
from lib.tools.logger import logger


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
    message_text += get_message("relay_sub_page_body", language_code) + "\n\n"

    tariff_str = decode_tariff(tariff_lvl, language_code)
    grant_line = channel_plan.status_line(utgid, language_code)
    if grant_line:  # free Bronze: while subscribed, not days left; money does not renew it
        message_text += "<b>" + get_message("curr_tariff", language_code) + ": " + tariff_str + "</b>\n<b>" \
            + get_message("curr_balance", language_code) % money_text(balance) + "</b>\n" + grant_line
    else:
        message_text += get_tariff_info_message(
            tariff_str, balance, tariff_price, time_left, notify_left, language_code)
    message_text += "\n\n" + get_message("relay_sub_page_footnote", language_code)

    # how to pay (a subscription, one payment), then change plan; the methods are one level down
    menu_keyboard: list[list[InlineButtonData]] = subscription_pay_rows(language_code)
    menu_keyboard += channel_plan.entry_row(utgid, language_code)
    menu_keyboard.append([{'text': get_message('referralMenuButton', language_code), 'callback_data': {'tp': 'bs_ref'}}])
    menu_keyboard.append([go_back_inline_button(language_code)])

    result = {
        "message": message_text,
        "markup": menu_keyboard
    }
    return result


def open_referral_page(data: ControllerParams):
    """Invite friends: what the inviter gets (giveAward), the link and the share button."""
    language_code = data['language_code']
    render_messages(data['chat_id'], [{
        'type': 'text', 'disable_web_page_preview': True,
        'text': get_message('donate_page_referral', language_code) + '\n\n' + referral.invite_link(data['chat_id']),
        'reply_markup': [referral.invite_row(data['chat_id'], language_code), [go_back_inline_button(language_code)]]}])


def open_once_page(data: ControllerParams):
    """One-time payments: Stars, CryptoBot (Robokassa for the creator) and the page of
    every plan's prepaid months (a running plan sees its own there)."""
    language_code = data['language_code']
    menu_keyboard: list[list[InlineButtonData]] = once_pay_rows(
        language_code, include_robokassa=(data['chat_id'] == creatorId))
    menu_keyboard.append([{
        'text': get_message('bundlesButton', language_code).format(discount=longest_bundle()[1]),
        'callback_data': {'tp': BUNDLES_CALLBACK}}])
    menu_keyboard.append([go_back_inline_button(language_code)])
    render_messages(data['chat_id'], [{
        'type': 'text', 'text': get_message('payOnceBody', language_code), 'reply_markup': menu_keyboard}])


def open_subscription_tariffs_page(data: ControllerParams):
    tariff, balance, time_left, notify_left = get_tariff_params_by_tg(data['chat_id'], purchase=True)

    tariffs_sub_msg = get_tariffs_sub_message(data['language_code'], tariff['id'], balance, time_left, notify_left)

    render_messages(data['chat_id'], [{
        'type': 'text',
        'text': tariffs_sub_msg['message'] + channel_plan.pay_note(data['chat_id'], data['language_code']),
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

    for tariff in tariffs_for_change_plan(tariffs):
        tariff_texts = get_tariff_description_and_button_text(
            tariff, {'id': tariff_id}, language_code)

        message_text += tariff_texts['text'] + "\n\n"

        menu_keyboard.append(
            [{'text': tariff_texts['button_text'], 'callback_data': {"tp": "bs_trf_v", "v": tariff['id']}}])

    if paid_models.available():  # any paid plan has the better AI models
        message_text += get_message('paidModelsPlans', language_code).format(
            what=paid_models.what(language_code)) + "\n\n"

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


def ai_plan_text(level, language_code) -> str:
    """What the plan gives in AI, a line of its description ('' with AI off): hours of audio for summaries
    and transcripts, questions a day and per 30 days, the paid model's hours among them (the level's profile)."""
    from app.service.ai import summary
    rights = features.profile(features.level_key(level)) if int(level or 0) > 0 else features.profile(features.NONE)
    hours = rights['ai_hours'] if rights['ai'] else 0
    if not hours or not summary.enabled():
        return ''
    text = "\n" + get_message('trf_descr_ai', language_code).format(
        hours=hours, questions=rights['ai_questions_day'], month=rights['ai_questions_month'])
    paid = min(rights['ai_paid_hours'] or 0, hours)
    if paid and paid_models.transcribe_model(True) != paid_models.transcribe_model(False):
        text += ' ' + get_message('trf_descr_ai_paid', language_code).format(paid=paid)
    return text


def get_tariff_description_and_button_text(
        tariff, current_tariff, language_code, show_tariff_level_text=True):
    text = ""

    if show_tariff_level_text:
        text = "<b>" + get_message("tariff_lvl" + str(tariff['level']), language_code) + "</b>\n"

    text += get_message("trf_descr_tmplt", language_code) \
            % (
                money_text(tariff['price']),
                (
                    str(tariff['notify_count'])
                    if tariff['notify_count'] != -1
                    else "<b>" + get_message(
                        "unlimited", language_code).lower() + "</b>"),
                (
                    ("<b>" + get_message("yes", language_code) + "</b>")
                    if tariff['channel_control'] else get_message("no", language_code)))
    text += ai_plan_text(tariff['level'], language_code)
    button_text = (
            ("* " if current_tariff['id'] == tariff['id'] else "")
            + get_message("tariff_lvl" + str(tariff['level']), language_code))

    return {"text": text, "button_text": button_text}


# выбран тариф
CONFIRM_TARIFF_ACTION = 'bs_trf_ok'


def _stars_top_up_row(language_code) -> list[InlineButtonData]:
    """To the Stars page from a "not enough on the balance" answer: it used to have Back only."""
    return [{'text': get_message('topUpStarsButton', language_code), 'callback_data': {'tp': 'bs_stars'}}]


def downgrade_text(chat_id, current_tariff, desire_tariff, time_left, language_code, bundle_back=0) -> str:
    """The question before a move to a cheaper plan or off: the days, what comes back to the balance
    (the chat ever paid: the same half as the move gives), the prepaid months' discount that leaves
    it, what going back costs, a Stars subscription that the move cancels."""
    current = decode_tariff(current_tariff['level'], language_code)
    difference = int(current_tariff['price']) - int(desire_tariff['price'])
    if int(desire_tariff['id']) == 0:
        lines = [get_message('planOffAsk', language_code).format(current=current),
                 get_message('planOffWhat', language_code)]
    else:
        plan = decode_tariff(desire_tariff['level'], language_code)
        lines = [get_message('planDowngradeAsk', language_code).format(current=current, plan=plan),
                 get_message('planDowngradeDays', language_code).format(days=days_left_text(time_left), plan=plan)]
    refund = int(((time_left - 1) / tariff_period) * difference / 2)
    if refund > 0 and paid_for_days(chat_id):
        lines.append(get_message('planDowngradeRefund', language_code).format(refund=money_text(refund)))
    if bundle_back:
        lines.append(get_message('bundleDiscountBack', language_code).format(amount=money_text(bundle_back)))
    back = int((time_left / tariff_period) * difference)
    if back > 0:
        lines.append(get_message('planDowngradeBack', language_code).format(
            current=current, back=money_text(back, 0.5)))
    try:
        if stars_subscription.active(chat_id):
            lines.append(get_message('planDowngradeStarsSub', language_code).format(current=current))
    except Exception as e:  # the question goes without the line, never fails
        logger.warn("downgrade question: stars subscription:", chat_id, type(e).__name__, e)
    return "\n\n".join(lines)


def confirm_bot_subscription_tariff(data: ControllerParams):
    """"Yes" under downgrade_text: the move, if the plan it was asked from still runs."""
    return choose_bot_subscription_tariff(data, confirmed=True)


def choose_bot_subscription_tariff(data: ControllerParams, confirmed=False):
    db = SQLighter(db_path)
    # tariffs = db.getTariffs()
    current_subscription = db.getUserSubscriptionByTg(data['chat_id'])
    if current_subscription is None or current_subscription['tariff_id'] == 0:
        current_tariff = {'id': 0, 'price': 0, 'level': 0, 'notify_count': 0}
        if current_subscription is not None:  # days on no plan are no days: no price difference for them
            current_subscription = dict(current_subscription, time_left=0, notify_count=0)
    else:
        current_tariff = db.getTariffById(current_subscription['tariff_id'])
    if data['united_data']['v'] == 0:
        desire_tariff = {'id': 0, 'price': 0, 'level': 0, 'notify_count': 0}
    else:
        desire_tariff = db.getTariffById(data['united_data']['v'])
    db.close()
    # a grant's plan (db/plan_grants.py) is no plan here: the chosen plan turns on in its place from the
    # balance at its full price, its days are never a price difference or a refund
    grant = current_subscription is not None and plan_grants.active_kind(data['chat_id'])
    if grant:
        current_subscription = {'tariff_id': 0, 'balance': current_subscription['balance'],
                                'time_left': 0, 'notify_count': 0}
        current_tariff = {'id': 0, 'price': 0, 'level': 0, 'notify_count': 0}

    if desire_tariff is None or current_tariff is None:
        notify(data['callback'], data['message'], get_message('error', data['language_code']), alert=True)
        return False

    after_action_keyboard: list[list[InlineButtonData]] = [[go_back_inline_button(data['language_code'])]]

    if grant and int(desire_tariff['id']) == 0:
        # "Disable": the grant's plan ends and no plan is left, as for anyone (the plan it replaced would
        # come back with no days, and the tick would renew it from the balance)
        plan_grants.end_for_chat(data['chat_id'], 'disabled', restore=False)
        db = SQLighter(db_path)
        try:
            db.subscribeUserToTariffByTg(data['chat_id'], 0, current_subscription['balance'], 0, 0)
        finally:
            db.close()
        notify(data['callback'], data['message'], get_message('tariffSuccessChanged', data['language_code']))
        return open_subscription_tariffs_page(data)

    current_balance, hours_left = ((int(current_subscription['balance'] or 0), int(current_subscription['time_left'] or 0))
                                   if current_subscription is not None else (0, 0))
    # текущий тариф; the same plan with no days and the money for it is turned on below, as any plan
    if int(data['united_data']['v']) == int(current_tariff['id']) and not (
            int(desire_tariff['id']) > 0 and current_balance >= int(desire_tariff['price']) and hours_left <= 0):
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
                'text': get_message('tariffActivatedNotEnoughMoney', data['language_code']).format(
                    missing=money_text(desire_tariff['price'] - current_subscription['balance'], 0.5)),
                'reply_markup': [_stars_top_up_row(data['language_code'])] + after_action_keyboard
            }])
            return

    else:
        # A tap on a cheaper plan or off was a switch at once: a trial's curious tap on Bronze cost
        # $1.86 to undo. Asked first, with what it changes; the yes names the plan it was asked from.
        running = (int(current_tariff['id']) > 0 and current_subscription is not None
                   and int(current_subscription['time_left'] or 0) > 0)
        # leaving a plan its prepaid months renew: the discount on the months left comes off the
        # balance (offers.bundle_discount_back); what stays is what was paid for them
        bundle_back, bundle_settle = (bundle_discount_back(
            data['chat_id'], current_tariff['price'], current_subscription['balance'])
            if running else (0, []))
        if running and int(desire_tariff['price']) < int(current_tariff['price']) and not (
                confirmed and int(data['united_data'].get('c', -1)) == int(current_tariff['id'])):
            yes = (get_message('planOffYes', data['language_code']) if int(desire_tariff['id']) == 0
                   else get_message('planDowngradeYes', data['language_code']).format(
                       plan=decode_tariff(desire_tariff['level'], data['language_code'])))
            render_messages(data['chat_id'], [{
                'type': 'text',
                'text': downgrade_text(data['chat_id'], current_tariff, desire_tariff,
                                       int(current_subscription['time_left']), data['language_code'],
                                       bundle_back),
                'reply_markup': [[{'text': yes, 'callback_data': {
                    'tp': CONFIRM_TARIFF_ACTION, 'v': desire_tariff['id'], 'c': current_tariff['id']}}]]
                + after_action_keyboard}])
            return
        if bundle_back:
            current_subscription = dict(current_subscription, balance=int(current_subscription['balance']) - bundle_back)

        # если сейчас есть подписка
        if current_subscription is not None and current_subscription['time_left'] is not None:

            # и текущий тариф дешевле
            if current_tariff['price'] < desire_tariff['price']:
                price_diff = int((current_subscription['time_left'] / tariff_period)
                                 * (desire_tariff['price'] - current_tariff['price']))
                # если не хватает баланса, чтобы подписаться
                if price_diff > int(current_subscription['balance']):
                    message_str = get_message("notEnoughMoneyToActivate", data['language_code']).format(
                        missing=money_text(price_diff - int(current_subscription['balance']), 0.5))
                    render_messages(data['chat_id'], [{
                        'type': 'text', 'text': message_str,
                        'reply_markup': [_stars_top_up_row(data['language_code'])] + after_action_keyboard}])
                    return
                else:
                    new_balance = int(current_subscription['balance']) - price_diff

            # но если текущий тариф дороже, то частичный возврат
            else:
                price_diff = int(
                    ((current_subscription['time_left'] - 1) / tariff_period)
                    * (current_tariff['price'] - desire_tariff['price']) / 2)
                new_balance = int(current_subscription['balance'])
                # half of the days left goes back to the balance, if anything was ever
                # paid: the welcome trial's days were not, they must not become money
                if price_diff > 0 and paid_for_days(data['chat_id']):
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

        if not new_time_left:
            # as the tick renews (balance >= price): the period starts now, with the plan's own deliveries
            # (a count carried from a plan with no days was what was left of an old period)
            if new_balance >= desire_tariff['price'] and int(desire_tariff['id']) > 0:
                new_balance = new_balance - desire_tariff['price']
                new_time_left = tariff_period
                new_notify_count = desire_tariff['notify_count']

        if grant:
            if new_time_left == 0:  # short of the chosen plan: the grant's plan keeps running
                render_messages(data['chat_id'], [{
                    'type': 'text',
                    'text': get_message("notEnoughMoneyToActivate", data['language_code']).format(
                        missing=money_text(max(int(desire_tariff['price']) - int(new_balance), 0), 0.5)),
                    'reply_markup': [_stars_top_up_row(data['language_code'])] + after_action_keyboard}])
                return
            plan_grants.end_for_chat(data['chat_id'], 'purchase')

        settle_bundles(bundle_settle)
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
            if bundle_back:
                message_str += "\n\n" + get_message('bundleDiscountBack', data['language_code']).format(
                    amount=money_text(bundle_back))
            # a Stars subscription paid for the old plan: canceled, one for the new plan offered
            from app.service.payment.starsPaymentModule import plan_change_notice
            notice, rows = plan_change_notice(data['chat_id'], desire_tariff, data['language_code'])
            if notice:
                message_str += "\n\n" + notice
            render_messages(data['chat_id'], [{
                'type': 'text', 'text': message_str, 'reply_markup': rows + after_action_keyboard}])
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
