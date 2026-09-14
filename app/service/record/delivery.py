"""How an episode reaches Telegram, decided from its size alone. No I/O.

Sender executes these decisions; this module only names them, so the
limits and their order live in one place and can be tested directly.
"""
import enum

from lib.telegram import limits


class Upload(enum.Enum):
    BOT_API = 'bot_api'  # multipart upload, or a file_id we already have
    AGENT = 'agent'  # Telethon upload


def fetch_by_url_first(size_mb: float) -> bool:
    """Small enough for Telegram to download the enclosure URL itself."""
    return size_mb <= limits.URL_FETCH_MB


def upload_order(size_mb: float) -> tuple[Upload, ...]:
    """What to try after downloading, by the size on disk. Empty: too big.

    The second entry serves chats the first one missed: a Bot API refusal
    goes to the agent; chats the agent missed get its file_id via the Bot API.
    """
    if size_mb > limits.MTPROTO_UPLOAD_MB:
        return ()
    if size_mb <= limits.BOT_UPLOAD_MB:
        return Upload.BOT_API, Upload.AGENT
    return Upload.AGENT, Upload.BOT_API
