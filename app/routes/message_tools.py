from typing import Literal

from app.i18n.messages import get_message, get_message_rtd
from lib.telegram.general.message_master import InlineButtonData, MessageStructuresInterface


def go_back_inline_markup(language_code: str, button_text: Literal['back', 'cancel'] = 'back') \
        -> list[list[InlineButtonData]]:
    return [[go_back_inline_button(language_code, button_text)]]


def outdated_screen_message(language_code: str) -> list[MessageStructuresInterface]:
    """A screen whose saved state is gone (an old message, a restarted state
    store): say so, with a way back. Without it the chat stays on "Loading..."."""
    return [{
        'type': 'text',
        'text': get_message('screenOutdated', language_code),
        'reply_markup': go_back_inline_markup(language_code),
    }]


def go_back_inline_button(language_code: str, button_text: Literal['back', 'cancel'] = 'back') -> InlineButtonData:
    return {'text': get_message_rtd(["buttons", button_text], language_code),
            'callback_data': {'tp': 'bck'}}
