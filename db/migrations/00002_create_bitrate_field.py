# -*- coding: utf-8 -*-
import sqlite3

import os
import sys
bot_path = os.getcwd().split('/db/migrations')[0]
sys.path.insert(1, bot_path)

from config import db_path

class SQLighterLocal:

	def __init__(self, database):
		self.connection = sqlite3.connect(database)
		self.cursor = self.connection.cursor()

	def add_bitrate_to_users(self):
		with self.connection:
			sql = """
				ALTER TABLE users ADD COLUMN bitrate char(7);
			"""
			self.cursor.execute(sql)

	def close(self):
		self.connection.close()


db = SQLighterLocal(db_path)
db.add_bitrate_to_users()
db.close()
