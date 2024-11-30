# -*- coding: utf-8 -*-
import sqlite3
import json

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

	def create_tariffs_table(self):
		with self.connection:
			sql = """
			CREATE TABLE IF NOT EXISTS tariffs (
				id integer PRIMARY KEY,
				level integer NOT NULL,
				price integer NOT NULL,
				notify_count integer NOT NULL,
				compression integer
			);
			"""
			self.cursor.execute(sql)

	def create_user_tariff_connections_table(self):
		with self.connection:
			sql = """
			CREATE TABLE IF NOT EXISTS user_tariff_cs (
				id integer PRIMARY KEY,
				uid integer NOT NULL,
				tariff_id integer NOT NULL,
				balance integer
				notify_count integer,
				time_left integer
			);
			"""
			self.cursor.execute(sql)

	def add_users_refer_column(self):
		with self.connection:
			sql = """
				ALTER TABLE users ADD ref_id integer
			"""
			self.cursor.execute(sql)

	def add_tarif(self, level, price, notify_count, compression):
		with self.connection:
			self.cursor.execute(
				'INSERT INTO tariffs \
					(level, price, notify_count, compression) \
				VALUES (?, ?, ?, ?)',
				(str(level), str(price), str(notify_count), str(compression),))
			self.connection.commit()

	def delete_users_balance_column(self):
		with self.connection:
			sql = """
				CREATE TEMPORARY TABLE "users_backup" (
				"id"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
				"telegramId"	INTEGER NOT NULL UNIQUE,
				"lang"	char(15),
				"bitrate"	char(7),
				"ref_id"	integer);
			"""
			self.cursor.execute(sql)
			self.connection.commit()
			sql = """
				INSERT INTO users_backup
				SELECT id, telegramId, lang, bitrate, ref_id FROM users;
			"""
			self.cursor.execute(sql)
			self.connection.commit()
			sql = """
				DROP TABLE users;
			"""
			self.cursor.execute(sql)
			self.connection.commit()
			sql = """
				CREATE TABLE "users" (
				"id"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
				"telegramId"	INTEGER NOT NULL UNIQUE,
				"lang"	char(15),
				"bitrate"	char(7),
				"ref_id"	integer);
			"""
			self.cursor.execute(sql)
			self.connection.commit()
			sql = """
				INSERT INTO users
				SELECT id, telegramId, lang, bitrate, ref_id FROM users_backup;
			"""
			self.cursor.execute(sql)
			self.connection.commit()
			sql = """
				DROP TABLE users_backup;
			"""
			self.cursor.execute("VACUUM")
			self.connection.commit()

	def close(self):
		self.connection.close()


db = SQLighterLocal(db_path)
db.create_tariffs_table()
db.create_user_tariff_connections_table()
# db.add_users_refer_column()
db.add_tarif(1, 100, 40, 0)
db.add_tarif(2, 200, 100, 1)
db.add_tarif(3, 500, -1, 1)
db.delete_users_balance_column()
db.close()

db_users = SQLighter(db_path)
db_users.close()

print("created")
