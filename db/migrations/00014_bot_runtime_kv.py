# -*- coding: utf-8 -*-
import os
import sys
bot_path = os.getcwd().split('/db/migrations')[0]
sys.path.insert(1, bot_path)

from db.connection import connect_sqlite
from config import db_path


class SQLighterLocal:

	def __init__(self, database):
		self.connection = connect_sqlite(database)
		self.cursor = self.connection.cursor()

	def close(self):
		self.connection.close()

	def create_bot_runtime_kv(self):
		with self.connection:
			self.cursor.execute("""
			CREATE TABLE IF NOT EXISTS bot_runtime_kv (
				key TEXT PRIMARY KEY,
				value TEXT NOT NULL
			);
			""")


db = SQLighterLocal(db_path)
db.create_bot_runtime_kv()
db.close()

print("created")
