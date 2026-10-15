from app.controller.general.notify import notify
from app.i18n.messages import get_message, emojiCodes
from app.jobs.nosub_digest import DIGEST_TOGGLE_ACTION, digest_enabled
from app.routes.message_tools import go_back_inline_markup
from app.routes.ptypes import ControllerParams
from app.service.record.text_format import (
    EPISODE_FORMAT_ACTIONS, SEPARATE, user_format)
from config import db_path
from db.sqliteAdapter import SQLighter
from lib.telegram.general.message_master import (
    InlineButtonData, MessageStructuresInterface, message_editor, render_messages)


def reminders_mark(enabled: bool) -> str:
    return emojiCodes['whiteHeavyCheckMark'] if enabled else emojiCodes['crossMark']


def reminders_button_text(language_code, enabled: bool) -> str:
    key = "nosubDigestRemindersOn" if enabled else "nosubDigestRemindersOff"
    return reminders_mark(enabled) + " " + get_message(key, language_code)


def episode_format_label(language_code, episode_format) -> str:
    return get_message(
        next(action for action, fmt in EPISODE_FORMAT_ACTIONS.items() if fmt == episode_format),
        language_code)


def episode_format_buttons(language_code, value) -> list[list[InlineButtonData]]:
    """One button per choice; the current one is marked."""
    current = user_format(value)
    rows: list[list[InlineButtonData]] = []
    for action, episode_format in EPISODE_FORMAT_ACTIONS.items():
        mark = emojiCodes['whiteHeavyCheckMark'] + " " if episode_format == current else ""
        rows.append([{
            'text': mark + episode_format_label(language_code, episode_format),
            'callback_data': {'tp': action},
        }])
    return rows


def _stored_episode_format(user):
    try:
        return user['episode_format']
    except (KeyError, IndexError, TypeError):
        return None


def show_digest_reminder_settings(has_bot_subscription: bool) -> bool:
    # Paid users already get the audio; the weekly text is nosub-only.
    return not bool(has_bot_subscription)


def _read_user(chat_id):
    db_users = SQLighter(db_path)
    try:
        return (db_users.get_user_by_tg(chat_id),
                db_users.is_user_have_bot_subscription(chat_id))
    finally:
        db_users.close()


def _screen(text, keyboard) -> list[MessageStructuresInterface]:
    return [{
        'type': 'text',
        'text': text,
        'reply_markup': keyboard,
        'disable_web_page_preview': True,
    }]


def open_settings(data: ControllerParams):
    render_messages(
        data['chat_id'],
        construct_settings_message(data['language_code'], data['chat_id']))


def open_episode_text_settings(data: ControllerParams):
    render_messages(
        data['chat_id'],
        construct_episode_text_message(data['language_code'], data['chat_id']))


def open_reminder_settings(data: ControllerParams):
    render_messages(
        data['chat_id'],
        construct_reminders_message(data['language_code'], data['chat_id']))


def construct_settings_message(language_code, chat_id) -> list[MessageStructuresInterface]:
    """The sections; each button shows what is set in it."""
    user, has_bot_subscription = _read_user(chat_id)

    episode_text_button: InlineButtonData = {
        'text': get_message("settingsEpisodeTextTitle", language_code) + " · "
                + episode_format_label(language_code, user_format(_stored_episode_format(user))),
        'callback_data': {'tp': 'settsText'},
    }
    keyboard: list[list[InlineButtonData]] = [[episode_text_button]]
    if show_digest_reminder_settings(has_bot_subscription):
        reminders_button: InlineButtonData = {
            'text': get_message("settingsRemindersTitle", language_code) + " · "
                    + reminders_mark(digest_enabled(user)),
            'callback_data': {'tp': 'settsRem'},
        }
        keyboard.append([reminders_button])
    keyboard += go_back_inline_markup(language_code)

    text = ("<b>" + get_message("bot_settings", language_code) + "</b>\n\n"
            + get_message("settingsPickSection", language_code))
    return _screen(text, keyboard)


def construct_episode_text_message(language_code, chat_id) -> list[MessageStructuresInterface]:
    user, _ = _read_user(chat_id)
    text = ("<b>" + get_message("settingsEpisodeTextTitle", language_code) + "</b>\n\n"
            + get_message("episodeFormatHelp", language_code))
    keyboard = episode_format_buttons(language_code, _stored_episode_format(user))
    keyboard += go_back_inline_markup(language_code)
    return _screen(text, keyboard)


def construct_reminders_message(language_code, chat_id) -> list[MessageStructuresInterface]:
    user, _ = _read_user(chat_id)
    text = ("<b>" + get_message("settingsRemindersTitle", language_code) + "</b>\n\n"
            + get_message("nosubDigestRemindersHelp", language_code))
    toggle_button: InlineButtonData = {
        'text': reminders_button_text(language_code, digest_enabled(user)),
        'callback_data': {'tp': DIGEST_TOGGLE_ACTION},
    }
    return _screen(text, [[toggle_button]] + go_back_inline_markup(language_code))


def _redraw(data: ControllerParams, screen: list[MessageStructuresInterface]):
    """Edits the screen the button is on; a new message when it cannot be edited."""
    if data['callback'] is not None and data['callback'].message is not None:
        try:
            message_editor(
                data['chat_id'], screen[0], data['callback'].message.message_id)
            return
        except Exception:
            pass
    render_messages(data['chat_id'], screen)


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
    _redraw(data, construct_reminders_message(data['language_code'], data['chat_id']))


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


def set_episode_format_handler(episode_format):
    def set_episode_format(data: ControllerParams):
        db_users = SQLighter(db_path)
        try:
            db_users.set_episode_format(data['chat_id'], episode_format)
            db_users.mark_rich_hint_sent(data['chat_id'])
        finally:
            db_users.close()

        notify(data['callback'], data['message'],
               episode_format_label(data['language_code'], episode_format))
        _redraw(data, construct_episode_text_message(data['language_code'], data['chat_id']))

    return set_episode_format


def use_separate_episode_format(data: ControllerParams):
    """The button under the one-time note after the first rich message."""
    db_users = SQLighter(db_path)
    try:
        db_users.set_episode_format(data['chat_id'], SEPARATE)
        db_users.mark_rich_hint_sent(data['chat_id'])
    finally:
        db_users.close()

    done = get_message("richHintDone", data['language_code'])
    notify(data['callback'], data['message'], episode_format_label(data['language_code'], SEPARATE))
    if data['callback'] is not None and data['callback'].message is not None:
        try:
            from agent.bot_telebot import bot
            bot.edit_message_text(
                done, data['chat_id'], data['callback'].message.message_id, reply_markup=None)
            return
        except Exception:
            pass
    render_messages(data['chat_id'], [{'type': 'text', 'text': done}])
