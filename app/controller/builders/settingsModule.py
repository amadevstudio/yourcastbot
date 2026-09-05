from app.controller.general.notify import notify
from app.i18n.messages import get_message, emojiCodes
from app.jobs.nosub_digest import DIGEST_TOGGLE_ACTION, digest_enabled
from app.routes.message_tools import go_back_inline_markup
from app.routes.ptypes import ControllerParams
from config import db_path
from db.sqliteAdapter import SQLighter
from lib.telegram.general.message_master import (
    InlineButtonData, MessageStructuresInterface, message_editor, render_messages)


def reminders_button_text(language_code, enabled: bool) -> str:
    mark = (
        emojiCodes['whiteHeavyCheckMark'] if enabled
        else emojiCodes['crossMark'])
    key = "nosubDigestRemindersOn" if enabled else "nosubDigestRemindersOff"
    return mark + " " + get_message(key, language_code)


def show_digest_reminder_settings(has_bot_subscription: bool) -> bool:
    # Paid users already get the audio; the weekly text is nosub-only.
    return not bool(has_bot_subscription)


def open_settings(data: ControllerParams):
    render_messages(
        data['chat_id'],
        construct_settings_message(data['language_code'], data['chat_id']))


def construct_settings_message(language_code, chat_id) -> list[MessageStructuresInterface]:
    db_users = SQLighter(db_path)
    try:
        user = db_users.get_user_by_tg(chat_id)
        has_bot_subscription = db_users.is_user_have_bot_subscription(chat_id)
    finally:
        db_users.close()

    text = "<b>" + get_message("bot_settings", language_code) + "</b>"
    keyboard: list[list[InlineButtonData]] = []
    if show_digest_reminder_settings(has_bot_subscription):
        text += "\n\n" + get_message("nosubDigestRemindersHelp", language_code)
        toggle_button: InlineButtonData = {
            'text': reminders_button_text(language_code, digest_enabled(user)),
            'callback_data': {'tp': DIGEST_TOGGLE_ACTION},
        }
        keyboard.append([toggle_button])
    keyboard += go_back_inline_markup(language_code)
    return [{
        'type': 'text',
        'text': text,
        'reply_markup': keyboard,
        'disable_web_page_preview': True,
    }]


def toggle_digest_reminders(data: ControllerParams):
    db_users = SQLighter(db_path)
    try:
        user = db_users.get_user_by_tg(data['chat_id'])
        enabled = not digest_enabled(user)
        db_users.set_nosub_digest_enabled(data['chat_id'], enabled)
    finally:
        db_users.close()

    notify(
        data['callback'], data['message'],
        get_message(
            "nosubDigestRemindersOnToast" if enabled
            else "nosubDigestRemindersOffToast",
            data['language_code']))

    settings_message = construct_settings_message(
        data['language_code'], data['chat_id'])[0]
    if data['callback'] is not None and data['callback'].message is not None:
        try:
            message_editor(
                data['chat_id'], settings_message,
                data['callback'].message.message_id)
        except Exception:
            render_messages(data['chat_id'], [settings_message])
    else:
        render_messages(data['chat_id'], [settings_message])


def mute_digest_reminders(data: ControllerParams):
    db_users = SQLighter(db_path)
    try:
        db_users.set_nosub_digest_enabled(data['chat_id'], False)
    finally:
        db_users.close()

    notify(
        data['callback'], data['message'],
        get_message("nosubDigestMutedToast", data['language_code']))

    if data['callback'] is not None and data['callback'].message is not None:
        try:
            from agent.bot_telebot import bot
            bot.edit_message_reply_markup(
                data['chat_id'],
                data['callback'].message.message_id,
                reply_markup=None)
        except Exception:
            pass
