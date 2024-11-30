import copy

from app.routes.ptypes import Message, Callback, Inline
from lib.tools.logger import logger


def log_incoming_data(callback: Callback | None, message: Message | None, keep_text: bool = False):
    message_to_log = copy.deepcopy(message)
    callback_to_log = copy.deepcopy(callback)

    if callback_to_log is not None:
        if keep_text is False and callback_to_log.message is not None:
            del callback_to_log.message.text
        logger.log(callback_to_log.deepcopy2dict())

    elif message_to_log is not None:
        if keep_text is False:
            del message_to_log.text
        logger.log(message_to_log.deepcopy2dict())


def log_incoming_inline(inline: Inline):
    inline_to_log = copy.deepcopy(inline)

    if inline_to_log is not None:
        logger.log(inline_to_log)
