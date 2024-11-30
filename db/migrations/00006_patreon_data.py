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

	def create_tariffs_table(self):
		with self.connection:
			sql = """
			CREATE TABLE IF NOT EXISTS payment_service_user_data (
				user_id integer NOT NULL,
				service_type text NOT NULL,
				email text NOT NULL,
				last_replenishment text,
				active integer NOT NULL,
				PRIMARY KEY (user_id, service_type)
			);
			"""
			self.cursor.execute(sql)


db = SQLighterLocal(db_path)
db.create_tariffs_table()
db.close()

# db_users = SQLighter(db_path)
# db_users.close()

print("created")
