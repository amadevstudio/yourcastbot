"""Optional manual migration; the listening repository also ensures its tables."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db.listening import connect

connect().close()
