# -*- coding: utf-8 -*-
"""Episode captions: feed text is escaped, our tags stay balanced, limits hold.

Run from the repo root: python app/service/record/test_caption.py
"""
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.record.caption import (  # noqa: E402
    CAPTION_LIMITS, prepare_message_text, record_caption)
from lib.markup import telegram_html  # noqa: E402
from lib.markup.cleaner import html_mrkd_cleaner  # noqa: E402
from lib.telegram import limits  # noqa: E402

# Tags Telegram accepts with parse_mode=HTML (the subset captions can hit).
_TELEGRAM_TAGS = {'a', 'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del',
                  'code', 'pre', 'span', 'tg-spoiler', 'blockquote'}
_TAG = re.compile(r'<(/?)([a-z][a-z0-9-]*)((?:\s[^<>]*)?)>')

# Nadie Sabe Nada, 12.09.2026: the feed itself ends mid-tag.
_TRUNCATED_FEED_TAIL = (
    'Ep. 505: Primer ‘Nadie Sabe Nada’, ahora sí, grabado cuando tiene que ser.'
    '&nbsp;Al empezar tenemos problemas con un foco. ' * 12
    + 'damos la bienvenida a Richard Marx (el cantante no, otro).</span></span></p></div>'
    '<div class="OutlineElement Ltr" style="font-family: &quot;Segoe UI&quot;, Arial;">'
    '<p class="Paragraph" paraid="414848442" style="margin: 16px 0px; color: windowtext;">'
    '<span data-')


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


_HREF = re.compile(r'<a href="([^"]*)">')
_ENTITY = re.compile(r'&(lt|gt|amp|quot)(?![A-Za-z]);?')
_ENTITY_CHARS = {'lt': '<', 'gt': '>', 'amp': '&', 'quot': '"'}


def telegram_href(markup):
    """The first link as Telegram reads it: tdlib decodes these whole names in
    attribute values, with or without ';' (MessageEntity.cpp, parse_html)."""
    return _ENTITY.sub(lambda m: _ENTITY_CHARS[m.group(1)], _HREF.search(markup).group(1))


def telegram_rejects(markup):
    """Mimic Telegram's HTML parser closely enough for our captions. None = accepted."""
    stack = []
    pos = 0
    for match in _TAG.finditer(markup):
        if '<' in markup[pos:match.start()]:
            return "raw '<' at %d" % markup.index('<', pos)
        pos = match.end()
        closing, name = match.group(1), match.group(2)
        if name not in _TELEGRAM_TAGS:
            return "unsupported tag %s" % name
        if not closing:
            stack.append(name)
        elif not stack or stack.pop() != name:
            return "unbalanced </%s>" % name
    if '<' in markup[pos:]:
        return "unclosed start tag at %d" % markup.index('<', pos)
    if stack:
        return "unclosed <%s>" % stack[-1]
    return None


def caption(mode='default', **fields):
    params = dict(
        lang_code='en', mode=mode, channel_link='http://cadenaser.com/programa/nadie_sabe_nada',
        ch_name='Nadie Sabe Nada', title='Todos ignoran todo', channel_id=259,
        pub_date='2026-09-12T10:45:00+0000', descr='', service_name='rss', service_id=None)
    params.update(fields)
    return record_caption(**params)


def main():
    _assert(max(CAPTION_LIMITS.values()) <= limits.CAPTION_CHARS, "caption budgets fit Telegram's limit")

    # The production failure: html_mrkd_cleaner left "<span data-".
    _assert('<span' not in html_mrkd_cleaner(_TRUNCATED_FEED_TAIL),
            "cleaner drops a tag the feed cut before '>'")

    for mode in ('default', 'short'):
        text = caption(mode, descr=_TRUNCATED_FEED_TAIL)
        _assert(telegram_rejects(text) is None, "%s: Telegram accepts truncated-feed caption" % mode)
        _assert(telegram_html.visible_length(text) <= CAPTION_LIMITS[mode],
                "%s: visible length within %d" % (mode, CAPTION_LIMITS[mode]))
        _assert('&nbsp;' not in text, "%s: entities decoded, not shown raw" % mode)
        _assert(text.startswith('<a href="http://cadenaser.com/programa/nadie_sabe_nada">Nadie Sabe Nada</a>'),
                "%s: channel link header kept" % mode)
        _assert('start=podcast_259' in text, "%s: open-in-bot link kept" % mode)
        _assert(text.endswith('.'), "%s: description cut after a sentence" % mode)

    # Feed fields are text: markup-looking titles are shown, not parsed.
    # (A '<...>' span in feed HTML is a tag by definition; real text arrives as &lt;.)
    text = caption(ch_name='R&D <3', title='a < b & c', descr='5 &lt; 6 &amp; <b>bold</b> x&lt;y')
    _assert(telegram_rejects(text) is None, "Telegram accepts '<' and '&' from feed fields")
    _assert('R&amp;D &lt;3' in text and 'a &lt; b &amp; c' in text, "name and title escaped")
    _assert(telegram_html.plain_text(text).endswith('5 < 6 & bold x<y'), "description reads as sent")

    # A header longer than the limit is never cut open; description yields.
    text = caption('short', title='T' * 600, descr='Never shown.')
    _assert(telegram_rejects(text) is None, "oversized header stays balanced")
    _assert('Never shown' not in text, "no description when header uses the budget")

    text = caption('short', descr='One endless sentence without a stop ' * 30)
    _assert('endless' not in text and telegram_rejects(text) is None,
            "a first sentence over the budget is dropped, not clipped")

    text = caption('none', descr='Hidden description.')
    _assert('Hidden' not in text and telegram_rejects(text) is None, "mode none: header only")

    text = caption('short', on_error=True, descr='Body.')
    _assert('Uploaded' not in text and 'start=podcast_' not in text, "on_error: no upload label or bot link")
    _assert(not text.endswith('\n'), "no trailing blank lines before appended notices")

    text = caption(channel_link='https://example.com/show?a=1&b="x"<y>', descr='')
    _assert(telegram_rejects(text) is None, "quote and brackets in feed URL cannot break href")
    _assert('href="https://example.com/show?a=1&amp;b=%22x%22%3Cy%3E"' in text, "href percent-encoded")

    for url in ('https://example.com/e.mp3?a=1&ltv=2&gt=3&amp=4&quot;=5&aid=6',
                'https://m.cdn.firstory.me/track/a/b/https%3A%2F%2Ffile.cdn.firstory.me%2Fx.mp3?v=1'):
        _assert(telegram_href(caption(channel_link=url, descr='')) == url,
                "Telegram reads the feed URL back unchanged: " + url[:45])

    _assert(telegram_rejects('<b>open') is not None, "validator catches unclosed tag")
    _assert(telegram_rejects('x <span data-') is not None, "validator catches cut tag")

    # prepare_message_text is plain-text trimming; keep its sentence rules.
    _assert(prepare_message_text('One. Two three four', max_length=12, clear_markup=False) == 'One.',
            "trim after the last full sentence")
    _assert(prepare_message_text('Intro. More\n12. Song title', max_length=16, clear_markup=False) == 'Intro. More',
            "drop a dangling list number")

    print("all caption checks passed")


if __name__ == "__main__":
    main()
