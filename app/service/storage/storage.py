from app.i18n.messages import get_message
from app.repository.storage import storage
from lib.telegram.general.message_master import message_master


def renew_user_shelve(bot, call, menu_module):
    menu_message = menu_module.construct_menu_message(
        call.from_user.language_code, call.chat.id)

    message_master(
        bot, call.chat.id,
        get_message("gettingStateError", call.from_user.language_code),
        resending=True)
    message_master(
        bot, call.chat.id, menu_message["message"], menu_message["markup"],
        resending=True, disable_web_page_preview=True)

    storage.clear_user_storage(call.chat.id)
    storage.add_user_state(call.chat.id, "menu")
