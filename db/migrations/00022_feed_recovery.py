"""Optional manual migration; jobs also ensure the table at startup."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db.feed_recovery import connect

connect().close()
