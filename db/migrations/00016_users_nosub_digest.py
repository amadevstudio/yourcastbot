# -*- coding: utf-8 -*-
import os
import sys
bot_path = os.getcwd().split('/db/migrations')[0]
sys.path.insert(1, bot_path)

from db.connection import connect_sqlite
from db.sqliteAdapter import ensure_users_nosub_digest_columns
from config import db_path


connection = connect_sqlite(db_path)
try:
    ensure_users_nosub_digest_columns(connection, db_path)
finally:
    connection.close()

print("created")
