"""Untrusted text inside Telegram HTML.

Feed titles, show names and descriptions are data, not markup. Reduce them
to plain text, measure and trim that text, then escape it on the way into
our own tags. Our tags stay balanced by construction, so nothing ever has to
close a foreign tag or slice a string that contains markup.
"""
import html

from lib.markup.cleaner import html_cleaner, markdown_cleaner

# Percent-encoding keeps a feed URL inside href="..." without relying on
# Telegram decoding entities in attribute values.
_HREF_UNSAFE = {'"': '%22', '<': '%3C', '>': '%3E', ' ': '%20'}


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
