from typing import Literal

from agent.bot_telebot import bot
from app.i18n.messages import get_message
from app.repository.storage import storage
from app.routes.message_tools import go_back_inline_markup
from app.routes.ptypes import Callback, Message
from lib.telegram.general.message_master import render_messages, MessageStructuresInterface


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
