"""Untrusted text inside Telegram messages: the one way in.

Feed titles, show names and descriptions are data, not markup. Reduce them
to plain text, measure and trim that text, then escape it on the way into
our own tags. Our tags stay balanced by construction, so nothing ever has to
close a foreign tag or slice a string that contains markup.

Every message, button and inline result takes feed text through here:
plain_text() for plain fields (buttons, audio title and performer, inline
result titles), text() between our tags, escape() for text that is already
plain (a Telegram channel title, a URL shown as text), href() for links.
Stored data (job payloads) keeps the raw feed text and is decoded once, when
shown. Only this module uses lib.markup.cleaner.
Lock: app/service/podcast/test_card.py.
"""
import html
import re

from lib.markup.cleaner import html_cleaner, markdown_cleaner

# Percent-encoding keeps a feed URL inside href="...". Telegram decodes
# &lt &gt &amp &quot in attribute values even without ';', so a query like
# ?a=1&gt=2 would turn into ?a=1>=2: '&' goes in as &amp;.
_HREF_UNSAFE = {'"': '%22', '<': '%3C', '>': '%3E', ' ': '%20', '&': '&amp;'}


def plain_text(raw: str | None) -> str:
    """What the reader sees: tags and broken tag tails gone, entities decoded."""
    if raw is None:
        return ''
    return markdown_cleaner(html.unescape(html_cleaner(str(raw))))


def escape(text: str) -> str:
    return html.escape(text, quote=False)


def text(raw: str | None) -> str:
    """A feed field ready to sit between our tags."""
    return escape(plain_text(raw))


def href(url: str | None) -> str:
    return ''.join(_HREF_UNSAFE.get(ch, ch) for ch in str(url or '').strip())


def visible_length(markup: str) -> int:
    """Characters Telegram counts against the caption limit."""
    return len(plain_text(markup))


_ANCHOR = re.compile(r'<a\s[^>]*?href\s*=\s*(["\'])(.*?)\1[^>]*>(.*?)</a\s*>', re.IGNORECASE | re.DOTALL)
_LINK_OPEN, _LINK_CLOSE = '\ue000', '\ue001'
_LINK_TOKEN = re.compile(_LINK_OPEN + r'(\d+)' + _LINK_CLOSE)


def protect_links(raw: str) -> tuple[str, list[str]]:
    """For text that keeps its links (a rich message): every http(s) anchor of the feed becomes
    a token holding its visible text, so plain_text() and trimming cannot touch it.
    Returns the text and the finished '<a href>' tags; restore_links() puts them back
    into the escaped text. Other schemes and empty anchors stay plain text."""
    links: list[str] = []

    def take(match):
        url = html.unescape(match.group(2)).strip()
        label = escape(plain_text(match.group(3)).strip())
        if not re.match(r'https?://', url, re.IGNORECASE) or not label:
            return match.group(3)
        links.append('<a href="' + href(url) + '">' + label + '</a>')
        return _LINK_OPEN + str(len(links) - 1) + _LINK_CLOSE

    return _ANCHOR.sub(take, str(raw)), links


def restore_links(escaped: str, links: list[str]) -> str:
    """Tokens back to their anchors; a token cut by trimming is dropped."""
    escaped = _LINK_TOKEN.sub(lambda m: links[int(m.group(1))] if int(m.group(1)) < len(links) else '', escaped)
    return escaped.replace(_LINK_OPEN, '').replace(_LINK_CLOSE, '')
