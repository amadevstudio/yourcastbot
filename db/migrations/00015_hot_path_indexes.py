# -*- coding: utf-8 -*-
import os
import sys
bot_path = os.getcwd().split('/db/migrations')[0]
sys.path.insert(1, bot_path)

from db.hot_indexes import build_hot_path_indexes
from config import db_path


build_hot_path_indexes(db_path)
print("created")
