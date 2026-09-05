from typing import TypedDict


class UserDBType(TypedDict, total=False):
    id: int
    telegramId: int
    lang: str
    bitrate: str
    ref_id: int
    deleted_at: str
    nosub_digest_enabled: int
    nosub_digest_sent_at: str
