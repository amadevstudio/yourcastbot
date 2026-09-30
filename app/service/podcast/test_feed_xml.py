# -*- coding: utf-8 -*-
"""The feed's <channel> is found whatever the host puts before it. Stdlib only.

Run from the repo root: python app/service/podcast/test_feed_xml.py
"""
import os
import sys
import xml.etree.ElementTree as ET

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.podcast.feed_xml import channel_element  # noqa: E402


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _root(xml):
    # keep comments and processing instructions, as lxml does
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
    return ET.fromstring(xml, parser=parser)


def _channel_title(xml):
    channel = channel_element(_root(xml))
    return None if channel is None else channel.findtext("title")


def main():
    _assert_eq(_channel_title(
        "<rss><channel><title>Plain</title><item/></channel></rss>"),
        "Plain", "channel first, as before")
    # feeds.acast.com, TED Talks Daily, September 2026
    _assert_eq(_channel_title(
        "<rss><script xmlns='http://www.w3.org/1999/xhtml'>x</script>"
        "<channel><title>TED Talks Daily</title><item/></channel></rss>"),
        "TED Talks Daily", "a script element before the channel")
    _assert_eq(_channel_title(
        "<rss><!-- generated --><?stats x?><channel><title>C</title></channel></rss>"),
        "C", "a comment and a processing instruction before the channel")
    _assert_eq(channel_element(_root(
        "<feed><title>Atom</title><entry/></feed>")).tag,
        "title", "no channel: the first element, as before")
    _assert_eq(channel_element(_root("<rss><!-- only --></rss>")), None,
               "nothing to parse: None, the caller reports it")
    print("all feed_xml checks passed")


if __name__ == "__main__":
    main()
