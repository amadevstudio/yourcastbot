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

	def create_channels_table(self):
		with self.connection:
			sql = """
			CREATE TABLE IF NOT EXISTS tg_channels (
				id integer PRIMARY KEY AUTOINCREMENT UNIQUE,
				user_id integer NOT NULL,
				tg_id integer NOT NULL,
				active integer NOT NULL
			);
			"""
			self.cursor.execute(sql)

	def create_subscription_to_channel_connection(self):
		with self.connection:
			sql = """
			CREATE TABLE IF NOT EXISTS subscription_to_tg_channel_cs (
				user_channel_cs_id integer NOT NULL,
				tg_channel_id integer NOT NULL,
				PRIMARY KEY (user_channel_cs_id, tg_channel_id)
			);
			"""
			self.cursor.execute(sql)


db = SQLighterLocal(db_path)
db.create_channels_table()
db.create_subscription_to_channel_connection()
db.close()

# db_users = SQLighter(db_path)
# db_users.close()

print("created")
