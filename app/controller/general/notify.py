from typing import Literal

from agent.bot_telebot import bot
from app.i18n.messages import get_message
from app.repository.storage import storage
from app.routes.message_tools import go_back_inline_markup
from app.routes.ptypes import Callback, Message
from lib.telegram.general.message_master import render_messages, MessageStructuresInterface
from lib.tools.logger import logger


# A button of an old screen: its saved state is gone (app/routes/screen_state.py).
# The handler returns one of these, so it ends with False like its other failure
# paths. A page (a list) replaces the screen; an action (a toggle) shows a toast.
def render_outdated_screen(data) -> Literal[False]:
    render_messages(data['chat_id'], [{
        'type': 'text',
        'text': get_message('screenOutdated', data['language_code']),
        'reply_markup': go_back_inline_markup(data['language_code']),
    }], resending=data['callback'] is None)
    return False


def notify_outdated_screen(data) -> Literal[False]:
    notify(data['callback'], data['message'], get_message('screenOutdated', data['language_code']), alert=True)
    return False


def notify(
        call: Callback | None,
        message: Message | None,
        text: str,
        alert: bool = False,
        resending: bool = False,
        save_state: bool = False,
        button_text: Literal['back', 'cancel'] = 'back',
        disable_web_page_preview: bool = True
):
    if call is not None:
        call.answered = True
        bot.answer_callback_query(
            callback_query_id=call.id, show_alert=alert, text=text)
        return

    if message is not None:
        message_structures: list[MessageStructuresInterface] = [{
            'type': 'text',
            'text': text,
            'reply_markup': go_back_inline_markup(message.from_user.language_code, button_text=button_text),
            'disable_web_page_preview': disable_web_page_preview
        }]
        render_messages(message.chat.id, resending=resending, message_structures=message_structures)

        if not save_state:
            storage.add_user_state(message.chat.id, 'empty')


# A tap the handler did not answer: the button kept its spinner until Telegram gave up
# (32 of 49 taps in botsim, 2026-11-08). The incoming worker answers it with nothing
# once the handler is done, so a toast the handler sends is never refused as answered.
def answer_tap(call: Callback | None):
    if call is None or getattr(call, 'answered', True):
        return
    call.answered = True
    try:
        bot.answer_callback_query(callback_query_id=call.id)
    except Exception as e:  # a query older than Telegram keeps (a restart, a slow handler)
        logger.warn("tap answer:", e)
