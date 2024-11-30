from typing import TypedDict


class UserDBType(TypedDict, total=False):
    id: int
    telegramId: int
    lang: str
    bitrate: str
    ref_id: int
