# -*- coding: utf-8 -*-
"""Every text in `messages` exists in all six languages, with the same slots.

A translation with another number of %s, or a {name} English does not have,
crashes the format call; an unclosed tag makes Telegram reject the message.

Run: python app/i18n/test_translations_complete.py
"""
import collections
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.i18n.messages import messages  # noqa: E402

LANGUAGES = ("en", "ru", "pt-BR", "es", "de", "he")
PERCENT = re.compile(r"%[sd]")
NAME = re.compile(r"\{(\w+)\}")
TAG = re.compile(r"<(/?)(b|i|u|s|a|code|pre)\b")


def _unbalanced(text):
    depth = collections.Counter()
    for closing, tag in TAG.findall(text):
        depth[tag] += -1 if closing else 1
    return {tag: n for tag, n in depth.items() if n}


def _problems(en, text):
    found = []
    if len(PERCENT.findall(text)) != len(PERCENT.findall(en)):
        found.append("%s count")
    if not set(NAME.findall(text)) <= set(NAME.findall(en)):
        found.append("unknown {name}")
    if _unbalanced(text) and not _unbalanced(en):
        found.append("unclosed tag %r" % _unbalanced(text))
    return found


def main():
    missing, broken = [], []
    for key, by_lang in messages.items():
        en = (by_lang.get("en") or {}).get("ro_msg")
        for lang in LANGUAGES:
            text = (by_lang.get(lang) or {}).get("ro_msg")
            if not text:
                missing.append("%s/%s" % (key, lang))
            elif en and _problems(en, text):
                broken.append("%s/%s: %s" % (key, lang, ", ".join(_problems(en, text))))
    if missing:
        raise AssertionError("untranslated: %r" % missing[:10])
    print("ok  %d texts in %d languages" % (len(messages), len(LANGUAGES)))
    if broken:
        raise AssertionError("format slots or tags broken:\n" + "\n".join(broken[:20]))
    print("ok  no translation breaks the format slots or tags")


if __name__ == "__main__":
    main()
