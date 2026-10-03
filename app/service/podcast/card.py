# -*- coding: utf-8 -*-
"""Podcast cards: our HTML around feed text that is escaped, never parsed.

Feed fields (show name, description, site link) are data. They reach
Telegram only through lib.markup.telegram_html: decoded once to plain text
(&nbsp; is a character, not five letters), trimmed as plain text, escaped
on the way into our tags. Pasting them raw showed entities as text and let a
stray '<' break the whole message. Episode captions do the same
(app/service/record/caption.py). Lock: app/service/podcast/test_card.py.
"""
import re

from app.i18n.messages import emojiCodes, get_message, get_message_rtd
from app.service.record.caption import prepare_message_text
from app.service.record.helpers import prepare_podcast_update_time
from lib.markup import telegram_html


def genres_html(genres, language_code) -> str:
    """'<b>Main</b>, Other' from (genre key, is main) pairs; names from i18n."""
    names = []
    for key, is_main in genres:
        name = telegram_html.escape(str(get_message_rtd(["genres", key], language_code)))
        names.append("<b>" + name + "</b>" if is_main else name)
    return ", ".join(names)


def _site_line(url) -> str:
    # A bare URL: Telegram links it. Escaped for HTML, never markdown-escaped
    # (un_markdown_link put a visible "\_" into every underscore).
    return telegram_html.escape(str(url).strip()) + "\n"


def _date(value) -> str:
    """A feed date as the card shows it (the day part), escaped like any feed field."""
    return telegram_html.text(prepare_podcast_update_time(str(value)))


def _open_in_bot(language_code, bot_name, mode, podcast_id) -> str:
    return get_message("linkInTheBotByPodcastId_HTML", language_code).format(
        botName=bot_name, id=podcast_id, mode=mode)


def channel_card_text(channel_data, language_code, bot_name) -> str:
    """The podcast page: name, site, latest release, link in the bot, genres,
    rating and the description."""
    message = "<b>" + telegram_html.text(channel_data.get("title")) + "</b>\n"
    if channel_data.get("channelLink"):
        message += _site_line(channel_data["channelLink"])
    last_date = channel_data.get("lastDate")
    if last_date:
        message += get_message("lastUpdate", language_code) + " " + \
            _date(last_date) + "\n\n"

    channel_id = channel_data.get("id")
    channel_id = int(channel_id) if channel_id is not None else None
    if channel_id is not None and channel_id < 1:
        channel_id = None
    if channel_id is not None:
        message += _open_in_bot(language_code, bot_name, "podcast", channel_id)
        message += " " + get_message("in_the_bot", language_code).format(botName=bot_name)
    elif channel_data.get("service_name") == "itunes" and channel_data.get("service_id"):
        message += _open_in_bot(
            language_code, bot_name, "podcastItunes", channel_data["service_id"])
        message += " " + get_message("in_the_bot", language_code).format(botName=bot_name)
    else:
        message += "@" + bot_name
    message += "\n\n"

    genres = genres_html(
        [(genre["name"], genre["isMain"]) for genre in channel_data.get("genres") or []],
        language_code)
    if genres or "rating" in channel_data:
        if genres:
            message += genres + "\n"
        rating = channel_data.get("rating")
        if rating and rating["value"]:
            value = round(float(rating["value"]), 1)
            value = value if int(value) != value else int(value)
            message += emojiCodes["trophy"] + " " + f"{value}/5 ({rating['count']})\n"
        message += "\n"

    return message + telegram_html.text(channel_data.get("descr"))


def records_header_text(podcast_data, count, routing_helper_message, language_code) -> str:
    """Above the episode list: name, latest release, the first sentence of the
    description, how many episodes."""
    descr = telegram_html.plain_text(podcast_data.get("descr"))
    first = re.search(r'[.?!]\s', descr)
    if first and first.start() > 0:
        descr = descr[:first.start() + 1]
    descr = prepare_message_text(descr, clear_markup=False)
    return (
        "<b>" + telegram_html.text(podcast_data.get("title")) + "</b>\n"
        + get_message("lastUpdate", language_code) + " "
        + _date(podcast_data.get("lastDate") or "") + "\n\n"
        + telegram_html.escape(descr) + "\n"
        + get_message("thereis", language_code) + " " + str(count) + " "
        + emojiCodes.get("disk") + "\n"
        + routing_helper_message)


def search_card_text(
        name, site_link, apple_link, release_date, open_mode, open_id, genres,
        language_code, bot_name) -> str:
    """The message an inline search result sends: name, site (or Apple
    Podcasts), latest release, link in the bot, genres."""
    message = "<b>" + telegram_html.text(name) + "</b>\n"
    if site_link:
        message += _site_line(site_link)
    else:
        message += '<a href="' + telegram_html.href(apple_link) + '">Apple Podcasts</a>\n'
    message += get_message("lastUpdate", language_code) + " " + _date(release_date) + "\n\n"
    message += _open_in_bot(language_code, bot_name, open_mode, open_id) + "\n\n"
    return message + genres_html(genres, language_code)
