import telebot.apihelper
import telebot.types

# Aliases, NOT subclasses.
#
# telebot builds and raises its own classes, so an object it produces is an instance of
# telebot.types.Message / telebot.apihelper.ApiTelegramException and never of a class derived
# from them: issubclass(Local, real) is True, isinstance(real_instance, Local) is False.
# While these were subclasses, every `except ApiTelegramException` / `except ApiException` in
# the project was unreachable, so the 429 backoff, the "bot was blocked" reaction, the
# "message to edit not found" resend and the episode sending retries never ran - the errors
# fell through to the generic `except Exception` and were only logged and re-raised.
# Keep them plain aliases so both `except` and type annotations line up with the real objects.

Message = telebot.types.Message

InlineKeyboardMarkup = telebot.types.InlineKeyboardMarkup

InlineKeyboardButton = telebot.types.InlineKeyboardButton

ReplyKeyboardMarkup = telebot.types.ReplyKeyboardMarkup

InputMedia = telebot.types.InputMedia

# ApiTelegramException is a subclass of ApiException, catching ApiException catches both
ApiException = telebot.apihelper.ApiException

ApiTelegramException = telebot.apihelper.ApiTelegramException
