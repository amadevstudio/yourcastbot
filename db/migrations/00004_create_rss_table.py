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

	# def create_rss_table(self):
	# 	with self.connection:
	# 		sql = """
	# 		CREATE TABLE IF NOT EXISTS channel_rss (
	# 			id integer PRIMARY KEY,
	# 			channel_id integer NOT NULL,
	# 			rss_link text
	# 		);
	# 		"""
	# 		self.cursor.execute(sql)

	def makingItunesIdUnnessesary(self):
		with self.connection:
			sql = """
				CREATE TEMPORARY TABLE channels_backup (
					id integer PRIMARY KEY AUTOINCREMENT UNIQUE,
					itunes_id integer,
					name text
				)
			"""
			self.cursor.execute(sql)
			self.connection.commit()
			sql = """
				INSERT INTO channels_backup
				SELECT id, itunes_id, name FROM channels;
			"""
			self.cursor.execute(sql)
			self.connection.commit()
			sql = """
				DROP TABLE channels;
			"""
			self.cursor.execute(sql)
			self.connection.commit()
			sql = """
				CREATE TABLE "channels" (
					id integer PRIMARY KEY AUTOINCREMENT UNIQUE,
					itunes_id integer,
					name text,
					rss_link text
				);
			"""
			self.cursor.execute(sql)
			self.connection.commit()
			sql = """
				INSERT INTO channels
				SELECT id, itunes_id, name, NULL FROM channels_backup;
			"""
			self.cursor.execute(sql)
			self.connection.commit()
			sql = """
				DROP TABLE channels_backup;
			"""
			self.cursor.execute("VACUUM")
			self.connection.commit()

	def close(self):
		self.connection.close()


db = SQLighterLocal(db_path)
# db.create_rss_table()
db.makingItunesIdUnnessesary()
db.close()

print('Done')
