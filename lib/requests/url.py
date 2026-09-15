"""URLs taken from feeds and iTunes, made safe to fetch without changing them."""
import re
from urllib.parse import quote

# RFC 3986 reserved characters plus '%': an address that already encodes
# something keeps it. quote(url, safe=":/?=") turned a tracker's embedded
# https%3A%2F%2F... into https%253A%252F%252F... and the tracker hung.
_KEEP = "!#$&'()*+,/:;=?@[]~%"
_STRAY_PERCENT = re.compile(r'%(?![0-9A-Fa-f]{2})')


def normalize_url(url: str) -> str:
    """Percent-encode what a URL may not contain (spaces, non-ASCII). Idempotent."""
    return quote(_STRAY_PERCENT.sub('%25', url.strip()), safe=_KEEP)
