# -*- coding: utf-8 -*-
"""How an episode's text reaches a user: one rich message, or the audio and a separate quote.

A caption holds 1024 characters (Telegram Premium of the bot's owner does not
change that). 'rich' is the default for everyone: one message with the player
and the whole description. A user whose Telegram cannot show it switches to
'separate': the audio with a short caption, then the description in a
collapsible quote. 'caption' is the old way and stays for channels and for
every case where a rich message could not be sent.
"""
RICH = 'rich'
SEPARATE = 'separate'
CAPTION = 'caption'

EPISODE_FORMAT_TOGGLE_ACTION = "episodeFormatToggle"
EPISODE_FORMAT_SEPARATE_ACTION = "episodeFormatSeparate"


def user_format(value) -> str:
    """A stored value (None, '', junk) is the default: rich."""
    return SEPARATE if value == SEPARATE else RICH


def other_format(value) -> str:
    return RICH if user_format(value) == SEPARATE else SEPARATE
