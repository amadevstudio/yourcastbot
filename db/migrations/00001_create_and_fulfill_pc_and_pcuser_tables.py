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

	def create_channels_table(self):
		with self.connection:
			sql = """
			CREATE TABLE IF NOT EXISTS channels (
				id integer PRIMARY KEY,
				itunes_id integer NOT NULL,
				name text
			);
			"""
			self.cursor.execute(sql)

	def create_user_channel_connections_tables(self):
		with self.connection:
			sql = """
			CREATE TABLE IF NOT EXISTS user_channel_cs (
				id integer PRIMARY KEY,
				user_telegram_id integer NOT NULL,
				channel_id integer NOT NULL,
				last_guid text,
				last_date text,
				notify integer
			);
			"""
			self.cursor.execute(sql)

	def delete_users_subs_column(self):
		with self.connection:
			sql = """
				CREATE TEMPORARY TABLE "users_backup" (
				"id"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
				"telegramId"	INTEGER NOT NULL UNIQUE,
				"balance"	INTEGER,
				lang char(15));
			"""
			self.cursor.execute(sql)
			self.connection.commit()
			sql = """
				INSERT INTO users_backup SELECT id, telegramId, balance, lang FROM users;
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
				"balance"	INTEGER,
				lang char(15));
			"""
			self.cursor.execute(sql)
			self.connection.commit()
			sql = """
				INSERT INTO users SELECT id, telegramId, balance, lang FROM users_backup;
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
db.create_channels_table()
db.create_user_channel_connections_tables()
db.close()

db_users = SQLighter(db_path)
users = db_users.get_all_users()

created_connections = 0
for user in users:
	if user['subs'] != '' and user['subs'] != '{}':
		try:
			user_subs = json.loads(user['subs'])
		except Exception as e:
			print(user['id'], " ", e, flush=True)
			continue

		for sub in user_subs:
			try:
				notify = user_subs[sub]["notify"]
			except Exception:
				notify = True
			db_users.add_sub(
				user['telegramId'], 0, sub, user_subs[sub]["pcName"],
				user_subs[sub]["lastGuid"], user_subs[sub]["lastDate"],
				notify)
			print("Sub ported", flush=True)
			created_connections += 1

print(created_connections)
print(db_users.created_channels)
db_users.close()

db = SQLighterLocal(db_path)
db.delete_users_subs_column()
db.close()
