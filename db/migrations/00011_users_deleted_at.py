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

	def add_users_deleted_at(self):
		with self.connection:
			columns = [
				row[1] for row in
				self.cursor.execute("PRAGMA table_info(users)").fetchall()]
			if 'deleted_at' in columns:
				print("already exists")
				return

			sql = """
				ALTER TABLE users ADD COLUMN deleted_at text;
			"""
			self.cursor.execute(sql)


db = SQLighterLocal(db_path)
db.add_users_deleted_at()
db.close()

# db_users = SQLighter(db_path)
# db_users.close()

print("created")
