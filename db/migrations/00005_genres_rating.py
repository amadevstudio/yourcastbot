# -*- coding: utf-8 -*-
import sqlite3

import os
import sys
bot_path = os.getcwd().split('/db/migrations')[0]
sys.path.insert(1, bot_path)

from constants import databaseName
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(bot_path, 'db/' + databaseName)

class SQLighterLocal:

	def __init__(self, database):
		self.connection = sqlite3.connect(database)
		self.cursor = self.connection.cursor()

	def create_genres_table(self):
		with self.connection:
			sql = """
			CREATE TABLE IF NOT EXISTS genres (
				id integer PRIMARY KEY,
				name text
			);
			"""
			self.cursor.execute(sql)

	def create_genre_to_podcast_table(self):
		with self.connection:
			sql = """
			CREATE TABLE IF NOT EXISTS genre_to_podcast (
				podcast_id integer NOT NULL,
				genre_id integer NOT NULL,
				is_main integer,
				PRIMARY KEY (podcast_id, genre_id)
			);
			"""
			self.cursor.execute(sql)

	def add_rating_field_to_podcast_user_connection(self):
		with self.connection:
			sql = """
				ALTER TABLE user_channel_cs ADD COLUMN rate integer;
			"""
			self.cursor.execute(sql)

	def close(self):
		self.connection.close()


db = SQLighterLocal(db_path)
db.create_genres_table()
db.create_genre_to_podcast_table()
db.add_rating_field_to_podcast_user_connection()
db.close()

print('Done')
