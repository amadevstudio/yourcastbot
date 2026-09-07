# -*- coding: utf-8 -*-
import sqlite3
from typing import Optional

import config
from db.connection import connect_sqlite


def connect(database: Optional[str] = None) -> sqlite3.Connection:
    path = config.db_path if database is None else database
    conn = connect_sqlite(path)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}
