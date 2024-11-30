from typing import TypedDict, Literal, Required


class RecResult(TypedDict):
    is_new_episode: bool
    file_size: str
    title: str
    dh: str
    num: int


class RecsStateData(TypedDict, total=False):
    p: int
    last_user_guid: str
    last_user_date: str
    search: str
    show_file_sizes: bool
    recCount: int


class RecordsDataType(TypedDict):
    effective_page: int
    perPageLimiter: int
    itemCounter: int
    noSearchItemCounter: int
    channelLink: str
    chName: str
    title: list
    descrs: list
    guids: list
    pubDates: list
    pubDatesFormatted: list
    isNewEpisode: list
    recordUniqIds: list
    links: list
    durations: list
    rssNumbers: list
    lastDate: str
    globalLastPubDate: str
    lastGuid: str
    lastPubDate: str
    lastRecordTitle: str


class RecDataType(TypedDict, total=False):
    tp: Required[Literal['rec', 'nrec']]
    id: int | None
    iid: str
    dh_n: Required[str]


def rec_callback_data_identifier(
        podcast_id: int | None, service_id: str | None, service_name: str | None,
        dh: str, rec_num: int, next_record: bool = False
) -> RecDataType:
    dh_n = f'{dh}_{rec_num}'

    if podcast_id is None and service_id is not None and service_name == 'itunes':
        return {
            'tp': 'rec' if next_record is False else 'nrec',
            'iid': service_id,
            'dh_n': dh_n
        }

    return {
        'tp': 'rec' if next_record is False else 'nrec',
        'id': podcast_id,
        'dh_n': dh_n
    }

