from app.controller.builders.helpModule import get_promo_messages
from config import db_path
from db.sqliteAdapter import SQLighter
from lib.telegram.general.message_master import outer_sender


def send_advertising(chat_id, language_code):
    ad_message = get_advertising_text(chat_id, language_code)
    if ad_message is None:
        return

    try:
        outer_sender(chat_id, [{'type': 'text', 'text': ad_message}])
    except Exception:
        pass


def get_advertising_text(chat_id, language_code) -> str | None:
    ad_message = get_promo_messages(language_code, ['Smartpods'])
    if ad_message == '':
        return None

    db_users = SQLighter(db_path)
    is_user_have_bot_subscription = db_users.is_user_have_bot_subscription(chat_id)
    db_users.close()
    if is_user_have_bot_subscription:
        return None

    return ad_message
