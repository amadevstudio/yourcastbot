import re

html_break_regular = re.compile(r'<\/?br[\s\/]*>?', re.IGNORECASE)
line_break_regular = re.compile(r'\n')
html_regular = re.compile(r'<\/?(?:(?!br))[^>]*\/?>', re.IGNORECASE)  # Not b
markdown_regular = re.compile(r'[\*[_`]')


def html_cleaner(msg):
    # from lib.tools.logger import logger
    # logger.debug("Before", msg)
    line_break_saved = line_break_regular.sub('<br/', msg)  # Not filter br
    # logger.debug("After line break regular", line_break_saved)
    html_cleared = html_regular.sub('', line_break_saved)
    # logger.debug("After html regular", html_cleared)
    html_breaks_replaced = html_break_regular.sub('\n', html_cleared)
    # logger.debug("After html breaks replaced", html_breaks_replaced)
    return html_breaks_replaced


def markdown_cleaner(msg):
    return markdown_regular.sub(' ', msg)


def html_mrkd_cleaner(msg: str | None):
    if msg is None:
        return ''

    return markdown_cleaner(html_cleaner(msg))


def un_markdown_link(str):
    return str.replace("_", "\\_")
