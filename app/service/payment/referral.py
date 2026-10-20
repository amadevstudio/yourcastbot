# -*- coding: utf-8 -*-
"""Invite a friend: the share button and its copy. The rewards are giveAward's.

The link is the one /start already reads (`?start=<inviter chat id>`).
The button opens Telegram's share sheet with the link and a ready text.
"""
from urllib.parse import quote

from app.i18n.messages import get_message
from config import botName, tariff_new_user_period, tariff_ref_invitee_period, tariff_ref_period


def invite_link(chat_id) -> str:
    return "https://t.me/%s?start=%d" % (botName, int(chat_id))


def share_url(chat_id, language_code) -> str:
    text = get_message("referralShareText", language_code).format(
        days=(tariff_new_user_period + tariff_ref_invitee_period) // 24)
    return "https://t.me/share/url?url=%s&text=%s" % (
        quote(invite_link(chat_id), safe=""), quote(text, safe=""))


def invite_row(chat_id, language_code) -> list:
    """One keyboard row; a URL button, so it works from any message and state."""
    return [{
        "text": get_message("referralInviteButton", language_code).format(
            days=tariff_ref_period // 24),
        "url": share_url(chat_id, language_code),
    }]
