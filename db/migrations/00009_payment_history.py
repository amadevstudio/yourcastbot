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

	def create_payment_history_table(self):
		with self.connection:
			sql = """
			CREATE TABLE IF NOT EXISTS payment_history (
				user_id integer NOT NULL,
				service_type text NOT NULL,
				invoice_id text,
				invoice_hash text,
				status text,
				amount integer,
				datetime text,
				PRIMARY KEY (user_id, service_type, invoice_id)
			);
			"""
			self.cursor.execute(sql)


db = SQLighterLocal(db_path)
db.create_payment_history_table()
db.close()

# db_users = SQLighter(db_path)
# db_users.close()

print("created")
