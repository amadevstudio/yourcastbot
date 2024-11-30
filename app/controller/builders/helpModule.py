from app.routes.message_tools import go_back_inline_markup
from app.routes.ptypes import ControllerParams
from lib.telegram.general.message_master import render_messages
from app.i18n.messages import get_message
from config import another_projects_texts


def privacy(data: ControllerParams):
    render_messages(data['chat_id'], [{
        'type': 'text',
        'text': get_message('privacy', data['language_code']),
        'reply_markup': go_back_inline_markup(
            data['language_code'])
    }])

def open_help(data: ControllerParams):
    help_msg = get_help_message(data['language_code'])
    render_messages(data['chat_id'], [{
        'type': 'text', 'text': help_msg, 'reply_markup': go_back_inline_markup(data['language_code']),
        'disable_web_page_preview': True}])


def get_help_message(lang_code, full=True):
    message = ""
    if full:
        message += "<b>" + get_message("help", lang_code) + "</b>\n\n"
        message += get_message("botDescr", lang_code) + "\n\n"
        message += get_message("whatPodcastIs", lang_code) + "\n\n"
    message += get_message("functsDescr", lang_code)

    return message


def show_another_projects(data: ControllerParams):
    ad_message = "<b>" + get_message("another_projects", data['language_code']) + "</b>\n\n"
    ad_message += get_message("another_projects_text", data['language_code']) + "\n\n"
    ad_message += get_promo_messages(data['language_code'])

    render_messages(data['chat_id'], [{
        'type': 'text',
        'text': ad_message,
        'reply_markup': go_back_inline_markup(data['language_code']),
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }])


def get_promo_messages(language_code: str, take_projects: list[str] | None = None) -> str:
    ad_messages = []
    text: str | None
    for text_set in another_projects_texts:
        if take_projects is not None and text_set.get('name', None) not in take_projects:
            continue

        if language_code in text_set['description']:
            text = text_set.get('description', {}).get(language_code, None)
        else:
            text = text_set.get('description', {}).get('en', None)
        if text is not None:
            ad_messages.append("\U00002022 " + text)  # точка bullet

    return "\n\n".join(ad_messages)
