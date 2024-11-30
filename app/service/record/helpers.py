def get_record_uniq_id(guid: str, full_pub_date: str, title: str) -> str:
    uid = guid + "_" + full_pub_date + "_" + title
    return uid
