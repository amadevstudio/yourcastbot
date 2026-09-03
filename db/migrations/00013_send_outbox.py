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

	def create_send_outbox_table(self):
		with self.connection:
			sql = """
			CREATE TABLE IF NOT EXISTS send_outbox (
				id INTEGER PRIMARY KEY,
				created_at TEXT,
				action TEXT NOT NULL,
				user_id TEXT NOT NULL,
				payload_json TEXT NOT NULL,
				status TEXT NOT NULL,
				attempts INTEGER NOT NULL DEFAULT 0,
				leased_until TEXT NULL,
				available_at TEXT NOT NULL
			);
			"""
			self.cursor.execute(sql)
			self.cursor.execute("""
			CREATE INDEX IF NOT EXISTS send_outbox_claim_idx
				ON send_outbox (status, available_at, id);
			""")


db = SQLighterLocal(db_path)
db.create_send_outbox_table()
db.close()

# db_users = SQLighter(db_path)
# db_users.close()

print("created")
