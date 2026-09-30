# -*- coding: utf-8 -*-
"""Pick the RSS <channel> out of a parsed feed root. No lxml import.

rss.__parse_rss_root took the root's first child as the channel. Acast
feeds put <script xmlns="http://www.w3.org/1999/xhtml"> before <channel>,
so TED Talks Daily (10k listeners) and ~1.4k other channels parsed to no
items: nothing was delivered, the episode list was empty and every
cursor was "__". Hosts may also put comments or processing instructions
there. Works on lxml and xml.etree elements alike.

Lock: python app/service/podcast/test_feed_xml.py
"""


def channel_element(root):
    """The <channel> child of an RSS root; else its first element child."""
    first = None
    for child in root:
        tag = child.tag
        if not isinstance(tag, str):  # comment, processing instruction, entity
            continue
        if tag == "channel" or tag.endswith("}channel"):
            return child
        if first is None:
            first = child
    return first
