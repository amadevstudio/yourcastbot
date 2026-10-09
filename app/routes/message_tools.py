from typing import Literal

from app.i18n.messages import get_message_rtd
from lib.telegram.general.message_master import InlineButtonData


def go_back_inline_markup(language_code: str, button_text: Literal['back', 'cancel'] = 'back') \
        -> list[list[InlineButtonData]]:
    return [[go_back_inline_button(language_code, button_text)]]


def go_back_inline_button(language_code: str, button_text: Literal['back', 'cancel'] = 'back') -> InlineButtonData:
    return {'text': get_message_rtd(["buttons", button_text], language_code),
            'callback_data': {'tp': 'bck'}}
