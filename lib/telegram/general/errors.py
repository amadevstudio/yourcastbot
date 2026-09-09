import re
import sys

from config import db_path
from db.sqliteAdapter import SQLighter
from lib.net.enclosure import enclosure_host_fault


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


# Чат больше не принимает сообщения. Помечаем deleted_at, не роняем процесс.
# «group chat was upgraded to a supergroup chat» — старый id мёртв навсегда;
# без этой строки дайджест nosub вылетал из updater main() и супервизор
# крутил RSS с начала круга.
_USER_UNAVAILABLE_SNIPPETS = (
	"Forbidden: bot was blocked by the user",
	"Bad Request: chat not found",
	"Forbidden: user is deactivated",
	"Forbidden: bot was kicked from the group chat",
	"Forbidden: bot was kicked from the supergroup chat",
	"Forbidden: bot is not a member of the supergroup chat",
	"Forbidden: bot is not a member of the group chat",
	"Forbidden: the group chat was deleted",
	"Bad Request: group chat was upgraded to a supergroup chat",
	"GROUP_CHAT_UPGRADED",
	"PEER_ID_INVALID",
	"Bad Request: CHAT_ID_EMPTY",
)


def user_unavailable_error(e):
	text = str(e)
	return any(snippet in text for snippet in _USER_UNAVAILABLE_SNIPPETS)


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
	text = str(e)
	return (
		"message to edit not found" in text
		or "MESSAGE_ID_INVALID" in text
		or "message identifier is not specified" in text
	)


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


def audio_source_gone(error):
	"""File cannot be sent this attempt: 404/410, Telegram URL fetch, or CDN/DNS."""
	text = str(error)
	if "failed to get HTTP URL content" in text:
		return True
	if "404 Client Error" in text or "404 Not Found" in text:
		return True
	if "410 Client Error" in text or "410 Gone" in text:
		return True
	return enclosure_host_fault(error)


def expected_send_noise(error) -> bool:
	"""Blocked user, flood, stale edit, dead enclosure — not a process bug."""
	if error is None:
		return False
	if user_unavailable_error(error):
		return True
	if message_to_edit_not_found(error):
		return True
	if get_timeout_from_error_bot(error) or get_timeout_from_error_client(error):
		return True
	if media_fetch_failed(error) or audio_source_gone(error):
		return True
	return False


def log_caught(logger, *args, error=None):
	"""From an except block: WARN for expected send noise, ERR otherwise."""
	err = error if error is not None else sys.exc_info()[1]
	if expected_send_noise(err):
		if args:
			logger.warn(*args, err)
		else:
			logger.warn(err)
		return
	if args:
		logger.err(*args)
	elif err is not None:
		logger.err(err)
	else:
		logger.err()


def request_entity_too_large(error):
	"""Bot API rejected the upload (typically over the ~50 MB bot limit)."""
	text = str(error)
	return "413" in text or "Request Entity Too Large" in text or "FILE_TOO_BIG" in text
