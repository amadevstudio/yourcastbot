# -*- coding: utf-8 -*-
"""How an episode's text reaches a user: one rich message, or the audio and a separate quote.

A caption holds 1024 characters (Telegram Premium of the bot's owner does not
change that). A user picks one of four (Settings):

- 'rich' (the default): one message with the player and the whole description.
- 'separate': the audio with a header caption, then the description in a
  collapsible quote (for a Telegram that cannot show a rich message).
- 'caption': the old way, the description cut to fit the caption.
- 'meta': the header only (show, title, date, link), no description, as in channels.

Channels always get 'meta' semantics through description_mode 'none'.
"""
RICH = 'rich'
SEPARATE = 'separate'
CAPTION = 'caption'
META = 'meta'

FORMATS = (RICH, SEPARATE, CAPTION, META)

# Callback action of each choice in Settings; the note after the first rich
# message has its own action: it also closes the note.
EPISODE_FORMAT_ACTIONS = {
    "episodeFormatRich": RICH,
    "episodeFormatSeparate": SEPARATE,
    "episodeFormatCaption": CAPTION,
    "episodeFormatMeta": META,
}
EPISODE_FORMAT_HINT_ACTION = "episodeFormatHint"


def user_format(value) -> str:
    """A stored value (None, '', junk) is the default: rich."""
    return value if value in FORMATS else RICH
