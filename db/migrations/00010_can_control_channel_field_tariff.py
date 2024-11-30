# -*- coding: utf-8 -*-
import sqlite3

import os
import sys
bot_path = os.getcwd().split('/db/migrations')[0]
sys.path.insert(1, bot_path)

from db.sqliteAdapter import SQLighter
from config import db_path

class SQLighterLocal:

	def __init__(self, database):
		self.connection = sqlite3.connect(database)
		self.cursor = self.connection.cursor()

	def close(self):
		self.connection.close()

	def add_can_control_channel(self):
		with self.connection:
			sql = """
				ALTER TABLE tariffs ADD COLUMN channel_control integer;
			"""
			self.cursor.execute(sql)


db = SQLighterLocal(db_path)
db.add_can_control_channel()
db.close()

# db_users = SQLighter(db_path)
# db_users.close()

print("created")
