# -*- coding: utf-8 -*-
"""Feed text in podcast cards: decoded once, escaped, never pasted raw.

The podcast page showed "educational:&nbsp; explaining" (The HiFi Five,
03.10.2026): the old cleaner stripped tags but kept entities, and Telegram
HTML knows only &lt; &gt; &amp; &quot;. Locks the cards and the rule that
feed text reaches Telegram only through lib.markup.telegram_html.
Run from the repo root: python app/service/podcast/test_card.py
"""
import ast
import html
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.podcast import card  # noqa: E402
from app.service.record.test_caption import telegram_rejects  # noqa: E402

NBSP = " "
HIFI_DESCR = (
    "Welcome to The HiFi Five, a live roundtable discussion show about all things "
    "high-end audio.<br>This show is educational:&nbsp; explaining how to select "
    "components.&nbsp; This show also is a candid look at the hobby.")


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _visible(markup):
    """What the reader sees: our tags gone, the four Telegram entities decoded."""
    return html.unescape(re.sub(r"<[^>]+>", "", markup))


def _channel(**fields):
    data = {
        "id": 2546, "title": "The HiFi Five Podcast",
        "channelLink": "https://www.buzzsprout.com/2546169",
        "lastDate": "2026-09-24T10:00:00+0000",
        "genres": [{"name": "hobbies", "isMain": True}, {"name": "leisure", "isMain": False}],
        "descr": HIFI_DESCR,
    }
    data.update(fields)
    return data


def test_entities_are_decoded():
    text = card.channel_card_text(_channel(), "en", "yourcastbot")
    _assert("&nbsp;" not in text and "&amp;nbsp;" not in text, "no entity shown as text")
    _assert("educational:" + NBSP + " explaining" in _visible(text),
            "&nbsp; is a no-break space for the reader")
    _assert("high-end audio.\nThis show" in _visible(text), "<br> is a line break")
    _assert(telegram_rejects(text) is None, "Telegram accepts the card")


def test_raw_markup_is_escaped():
    text = card.channel_card_text(_channel(
        title="Q&A <live>", descr="Tags: <b>bold</b> & a < b, 5 &gt; 3"), "en", "yourcastbot")
    _assert(telegram_rejects(text) is None, "a stray '<' or '&' does not break the message")
    _assert(_visible(text).startswith("Q&A \n"), "a tag in the title is dropped, '&' shown")
    _assert("Tags: bold & a" in _visible(text), "description tags dropped, '&' kept as text")
    _assert("5 > 3" in _visible(text), "an entity in the feed is decoded once")


def test_site_link_is_not_markdown_escaped():
    text = card.channel_card_text(
        _channel(channelLink="https://example.com/my_show?a=1&b=2"), "en", "yourcastbot")
    _assert("my_show" in text and "\\_" not in text, "no visible backslash before '_'")
    _assert("?a=1&amp;b=2" in text, "'&' in the link is escaped for HTML")


def test_card_layout_is_kept():
    text = card.channel_card_text(_channel(rating={"value": "4.5", "count": 12}),
                                  "en", "yourcastbot")
    lines = text.split("\n")
    _assert(lines[0] == "<b>The HiFi Five Podcast</b>", "name in bold")
    _assert(lines[1] == "https://www.buzzsprout.com/2546169", "site on its own line")
    _assert(lines[2] == "Latest release 2026-09-24", "latest release date")
    _assert('start=podcast_2546"' in lines[4] and "@yourcastbot" in lines[4],
            "open in the bot by the channel id")
    _assert(lines[6] == "<b>Hobbies</b>, Leisure" or lines[6].startswith("<b>"),
            "main genre in bold first")
    _assert("4.5/5 (12)" in lines[7], "rating line")
    no_id = card.channel_card_text(_channel(id=None, service_name="itunes", service_id=77),
                                   "en", "yourcastbot")
    _assert('start=podcastItunes_77"' in no_id, "no channel id: open by the iTunes id")
    bare = card.channel_card_text(_channel(id=0, service_name="rss"), "en", "yourcastbot")
    _assert("\n@yourcastbot\n" in bare, "neither: just the bot")


def test_genre_names_are_escaped():
    genres = card.genres_html([("society & culture", True), ("comedy", False)], "en")
    _assert(genres == "<b>Society &amp; culture</b>, Comedy", "i18n '&' escaped, main in bold")


def test_records_header():
    text = card.records_header_text(
        {"title": "News &amp; Views", "lastDate": "2026-10-01T09:47:00+0000",
         "descr": "<p>First&nbsp;sentence. Second one.</p>"},
        42, "1/3", "en")
    _assert(telegram_rejects(text) is None, "Telegram accepts the list header")
    _assert(_visible(text).startswith("News & Views\n"), "show name decoded once")
    _assert("First" + NBSP + "sentence.\n" in _visible(text), "first sentence, entity decoded")
    _assert("Second" not in text, "only the first sentence")
    _assert(text.endswith("42 " + card.emojiCodes.get("disk") + "\n1/3"), "count and pages")


def test_search_card_is_html():
    text = card.search_card_text(
        "Tom & Jerry <Live>", None, "https://podcasts.apple.com/us/podcast/id1?a=1&b=2",
        "2026-09-24T10:00:00Z", "podcastItunes", 1, [("comedy", True)], "en", "yourcastbot")
    _assert(telegram_rejects(text) is None, "Telegram accepts the inline result message")
    _assert(text.startswith("<b>Tom &amp; Jerry </b>\n"), "name escaped, in bold")
    _assert('<a href="https://podcasts.apple.com/us/podcast/id1?a=1&amp;b=2">Apple Podcasts</a>'
            in text, "Apple Podcasts link through href()")
    _assert(text.endswith("<b>Comedy</b>"), "main genre bold (Markdown cleaning used to drop it)")


def _python_files():
    for base, dirs, files in os.walk(_ROOT):
        dirs[:] = [d for d in dirs if d not in ("venv", ".git", "node_modules", "__pycache__")]
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(base, name)


def test_one_way_in():
    """Only telegram_html uses the low-level cleaner; no Markdown messages."""
    importers, markdown = [], []
    for path in _python_files():
        rel = os.path.relpath(path, _ROOT)
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "lib.markup.cleaner" \
                    or isinstance(node, ast.Import) \
                    and any(a.name == "lib.markup.cleaner" for a in node.names):
                importers.append(rel)
            # Our own messages; an admin mailing picks its mode itself (mailer.py).
            if isinstance(node, ast.keyword) and node.arg == "parse_mode" \
                    and isinstance(node.value, ast.Constant) and node.value.value == "Markdown":
                markdown.append(rel)
    _assert(sorted(set(importers)) == [os.path.join("lib", "markup", "telegram_html.py")],
            "lib.markup.cleaner is used only by lib.markup.telegram_html")
    _assert(markdown == [], "no parse_mode='Markdown' in our messages: one escaping policy")
    _assert(not hasattr(__import__("lib.markup.cleaner", fromlist=["x"]), "html_mrkd_cleaner"),
            "the half-way cleaner (tags out, entities kept) is gone")


def main():
    for case in (test_entities_are_decoded, test_raw_markup_is_escaped,
                 test_site_link_is_not_markdown_escaped, test_card_layout_is_kept,
                 test_genre_names_are_escaped, test_records_header, test_search_card_is_html,
                 test_one_way_in):
        print("-- %s" % case.__name__)
        case()
    print("all card checks passed")


if __name__ == "__main__":
    main()
