# -*- coding: utf-8 -*-
import os
import sys
bot_path = os.getcwd().split('/db/migrations')[0]
sys.path.insert(1, bot_path)

from db.connection import connect_sqlite

from db.sqliteAdapter import SQLighter
from config import db_path

class SQLighterLocal:

	def __init__(self, database):
		self.connection = connect_sqlite(database)
		self.cursor = self.connection.cursor()

	def close(self):
		self.connection.close()

	def add_channel_http_validators(self):
		with self.connection:
			columns = [
				row[1] for row in
				self.cursor.execute("PRAGMA table_info(channels)").fetchall()]
			if 'http_etag' not in columns:
				self.cursor.execute(
					"ALTER TABLE channels ADD COLUMN http_etag TEXT;")
			else:
				print("http_etag already exists")
			if 'http_last_modified' not in columns:
				self.cursor.execute(
					"ALTER TABLE channels ADD COLUMN http_last_modified TEXT;")
			else:
				print("http_last_modified already exists")


db = SQLighterLocal(db_path)
db.add_channel_http_validators()
db.close()

# db_users = SQLighter(db_path)
# db_users.close()

print("created")
