import re
from typing import Literal

from app.i18n.messages import get_message
from app.service.record.helpers import prepare_podcast_update_time
from config import botName
from lib.markup import telegram_html
from lib.markup.cleaner import html_mrkd_cleaner

DescriptionModeOptions = Literal['default', 'short', 'none']

# Visible characters for the whole caption; test_caption keeps them under limits.CAPTION_CHARS.
CAPTION_LIMITS: dict[str, int] = {'default': 1000, 'short': 500}


def prepare_message_text(text, max_length=1024, clear_markup=True, whole_sentences=False):
    """Trim plain text to max_length, cutting after the last sentence or line.

    Plain text only: never pass markup here. Build HTML from already
    trimmed text instead (see record_caption). With whole_sentences, text
    that has no sentence or line end inside max_length becomes '' rather
    than a clipped fragment.
    """
    if clear_markup:
        text = html_mrkd_cleaner(text)

    # убрать тройные+ переносы
    text = re.sub(r'\n\n\n+', '\n\n', text)
    # убрать пробелы в начале строк
    text = re.sub(r'\n +', '\n', text)

    if len(text) > max_length:
        text = text[0:max_length]

        # ищем знаки препинания и переносы, убираем текст после них
        ends_of_entities = [x.start() for x in re.finditer(r'([.?!] )|(\n)', text)]
        if len(ends_of_entities) > 0:
            # сохраняем сам знак препинания или перенос
            text = text[:ends_of_entities.pop() + 1]
        elif whole_sentences:
            return ''

        # особые случаи
        regulars = [
            r'\n\s*[0-9]+[\.:)]\s*\Z',  # если оканчивается на пункт списка, например, 23
            r'\s([^\s])*:\Z|\s([^\s])*:\n\Z'  # заканчивается на ' abc:'
        ]
        for regular in regulars:
            ends_of_entities = [x for x in re.finditer(regular, text)]
            if len(ends_of_entities) > 0:
                last_match = ends_of_entities.pop().start()
                text = text[:last_match]

    return text


def record_caption(
        lang_code, mode: DescriptionModeOptions,
        channel_link, ch_name, title, channel_id, pub_date, descr, service_name, service_id,
        on_error=False, show_updated_text=True, bot_reference=True, bot_reference_botname=True) -> str:
    """Episode caption: our HTML around feed text that is escaped, never parsed.

    The header is never cut. The description gets what is left of the limit,
    trimmed as plain text before it is escaped.
    """
    header = _record_header(
        lang_code, channel_link, ch_name, title, channel_id, pub_date, service_name, service_id,
        on_error=on_error, show_updated_text=show_updated_text,
        bot_reference=bot_reference, bot_reference_botname=bot_reference_botname)
    if mode == 'none':
        return header.rstrip()

    budget = CAPTION_LIMITS.get(mode, CAPTION_LIMITS['default']) - telegram_html.visible_length(header)
    description = ''
    if budget > 0:
        # A first sentence longer than the budget is dropped, not clipped.
        description = prepare_message_text(
            telegram_html.plain_text(descr).strip(), max_length=budget, clear_markup=False,
            whole_sentences=True)
    return (header + telegram_html.escape(description)).rstrip()


def _record_header(
        lang_code, channel_link, ch_name, title, channel_id, pub_date, service_name, service_id,
        on_error, show_updated_text, bot_reference, bot_reference_botname) -> str:
    name = telegram_html.text(ch_name)
    if channel_link:
        message = '<a href="' + telegram_html.href(channel_link) + '">' + name + '</a>'
    else:
        message = "<b>" + name + "</b>"

    message += "\n<b>" + telegram_html.text(title)

    if channel_id is not None:
        message += " #id" + str(channel_id) + "\n"
    else:
        message += "\n"

    if not on_error and show_updated_text:
        message += get_message("uploaded", lang_code) + " "
    message += telegram_html.text(prepare_podcast_update_time(pub_date)) + "</b>\n\n"

    # ссылка на бота + ссылка на подкаст в боте
    if not on_error and bot_reference:
        try:
            channel_id = int(channel_id)
            if channel_id < 1 and channel_id is not None:
                channel_id = None
        except Exception:
            channel_id = None
        if channel_id is not None or (service_name == "itunes" and service_id):
            if channel_id is not None:
                message += get_message(
                    "linkInTheBotByPodcastId_HTML", lang_code).format(
                    botName=botName, id=channel_id, mode="podcast")
            elif service_name == "itunes" and service_id:
                message += get_message(
                    "linkInTheBotByPodcastId_HTML", lang_code).format(
                    botName=botName, id=service_id, mode="podcastItunes")
            if bot_reference_botname:
                message += " " + get_message("in_the_bot", lang_code).format(botName=botName)
            message += "\n\n"
        elif bot_reference_botname:
            message += f"@{botName}" + "\n\n"

    return message
