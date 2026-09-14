"""Telegram size limits. One place, so the numbers do not drift apart."""

URL_FETCH_MB = 20  # Bot API downloads a file from a URL itself
BOT_UPLOAD_MB = 50  # Bot API multipart upload
MTPROTO_UPLOAD_MB = 2000  # Telethon / user-level upload
CAPTION_CHARS = 1024  # visible characters, after entity parsing
