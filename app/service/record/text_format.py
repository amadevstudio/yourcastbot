# -*- coding: utf-8 -*-
"""How an episode's text reaches a user: the title and buttons, one rich message, or the audio and a quote.

A caption holds 1024 characters (Telegram Premium of the bot's owner does not
change that). A user picks one of five (Settings):

- 'brief' (the default since 2026-10-22): the header only, with "Summary" and
  "Show notes" buttons under the audio; the feed's description comes on a tap
  (DESCRIPTION_ACTION), as a collapsible quote replying to the audio.
- 'rich': one message with the player and the whole description.
- 'separate': the audio with a header caption, then the description in a
  collapsible quote (for a Telegram that cannot show a rich message).
- 'caption': the old way, the description cut to fit the caption.
- 'meta': the header only (show, title, date, link), no description, as in channels.

Channels always get 'meta' semantics through description_mode 'none'.
"""
BRIEF = 'brief'
RICH = 'rich'
SEPARATE = 'separate'
CAPTION = 'caption'
META = 'meta'

FORMATS = (BRIEF, RICH, SEPARATE, CAPTION, META)
DESCRIPTION_ACTION = 'desc'  # "Show notes" under a brief episode

# Callback action of each choice in Settings; the note after the first rich
# message has its own action: it also closes the note.
EPISODE_FORMAT_ACTIONS = {
    "episodeFormatBrief": BRIEF,
    "episodeFormatRich": RICH,
    "episodeFormatSeparate": SEPARATE,
    "episodeFormatCaption": CAPTION,
    "episodeFormatMeta": META,
}
EPISODE_FORMAT_HINT_ACTION = "episodeFormatHint"


def user_format(value) -> str:
    """A stored value (None, '', junk) is the default: brief. A choice made in Settings stays."""
    return value if value in FORMATS else BRIEF
