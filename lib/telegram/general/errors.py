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
		# Пометить, а не удалять: подписки должны пережить блокировку, чтобы всё
		# восстановилось, когда пользователь снова напишет боту (см. middleware get_user).
		# Помеченным просто перестают отправляться сообщения.
		db_users.mark_user_deleted_tg(int(user_id))
		db_users.close()
		return True
	else:
		return False

def message_to_edit_not_found(e):
	return "message to edit not found" in str(e)


# Telegram could not download the media we handed it: dead/blocked host, broken url,
# non-image content or an unsupported file. The menu has to degrade to a text one instead of dying
def media_fetch_failed(e):
	error_text = str(e)
	return "failed to get HTTP URL content" in error_text \
			or "wrong file identifier/HTTP URL specified" in error_text \
			or "wrong file identifier" in error_text \
			or "wrong remote file identifier" in error_text \
			or "IMAGE_PROCESS_FAILED" in error_text \
			or "PHOTO_INVALID_DIMENSIONS" in error_text \
			or "WEBPAGE_MEDIA_EMPTY" in error_text \
			or "MEDIA_EMPTY" in error_text \
			or "Bad Request: PHOTO_EXT_INVALID" in error_text
