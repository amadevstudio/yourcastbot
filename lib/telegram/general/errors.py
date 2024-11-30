import re

from config import db_path
from db.sqliteAdapter import SQLighter


def get_timeout_from_error_client(error):
	result = re.search(r'A wait of ([0-9]+) seconds is required', str(error))
	if result is not None:
		try:
			return int(result[1]) + 1
		except Exception:
			pass
	return False


def get_timeout_from_error_bot(error: Exception) -> int | bool:
	result = re.search(r'Too Many Requests: retry after ([0-9]+)', str(error))
	if result is not None:
		try:
			return int(result[1]) + 1
		except Exception:
			pass
	return False


def user_unavailable_error(e):
	return "Forbidden: bot was blocked by the user" in str(e) \
			or "Bad Request: chat not found" in str(e) \
			or "Forbidden: user is deactivated" in str(e) \
			or "Forbidden: bot was kicked from the group chat" in str(e)


def bot_blocked_reaction(e, user_id):
	if user_unavailable_error(e):
		db_users = SQLighter(db_path)
		db_users.delete_user_tg(int(user_id), False)
		db_users.close()
		return True
	else:
		return False

def message_to_edit_not_found(e):
	return "message to edit not found" in str(e)
