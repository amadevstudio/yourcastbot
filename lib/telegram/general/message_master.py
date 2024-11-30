import copy
import enum
import json
import typing
from io import TextIOWrapper
from typing import TypedDict, Literal, Required, Sequence
from urllib.parse import unquote

from app.routes.routes_list import AvailableActions, AvailableRoutes
from lib.telegram.general.errors import bot_blocked_reaction, get_timeout_from_error_bot, message_to_edit_not_found
from lib.telegram.telebot import types as telegram_types

from agent.bot_telebot import bot
from app.repository.storage import storage, telegram_cache
from lib.telegram.telebot.types import InputMedia, ApiTelegramException, Message, ApiException
from lib.tools.logger import logger

MESSAGE_TYPES = Literal['text', 'image', 'audio']


class MasterMessages(enum.Enum):
    text: MESSAGE_TYPES = 'text'
    image: MESSAGE_TYPES = 'image'
    audio: MESSAGE_TYPES = 'audio'


# Python don't allow use extra keys
class InlineButtonCallbackData(TypedDict):
    tp: AvailableRoutes | AvailableActions


class InlineButtonData(TypedDict, total=False):
    text: Required[str]
    callback_data: str | (dict[str, str | int | float | None] | InlineButtonCallbackData)  # So it's useless
    url: str


PARSE_MODES = Literal['MarkdownV2', 'HTML']
DEFAULT_PARSE_MODE: PARSE_MODES = 'HTML'


class BaseStructureInterface(TypedDict, total=False):
    type: Required[MESSAGE_TYPES]
    markup_type: Literal['inline']
    reply_markup: list[list[InlineButtonData]]
    parse_mode: PARSE_MODES
    disable_web_page_preview: bool


class TextStructureInterface(BaseStructureInterface):
    text: Required[str]


class ImageStructureInterface(BaseStructureInterface):
    text: str
    image: Required[str]  # TODO: | telebot.types.InputMedia?
    file_id: str


class AudioDataType(TypedDict, total=False):
    duration: int
    performer: str
    title: str


class AudioStructureInterface(BaseStructureInterface):
    text: str
    audio: Required[TextIOWrapper | str | int]
    file_id: str
    audio_data: AudioDataType


MessageStructuresInterface = TextStructureInterface | ImageStructureInterface | AudioStructureInterface


class ResultMessageStructuresInterface(TypedDict, total=False):
    id: Required[int]
    type: Required[MESSAGE_TYPES]
    message: Message | None


def build_new_prev_message_structure(message_id: int,
                                     message_type: MESSAGE_TYPES,
                                     message: Message | None = None) -> ResultMessageStructuresInterface:
    result: ResultMessageStructuresInterface = {
        'id': message_id,
        'type': message_type,
        'message': message
    }

    return result


def image_digger(image_message_structure: ImageStructureInterface) -> str:
    file_id = image_message_structure.get('file_id')
    if file_id is not None:
        return file_id

    return image_message_structure['image']


def prepare_images(message_structures: Sequence[BaseStructureInterface]):
    for i, message_structure in enumerate(message_structures):
        if 'image' not in message_structure:
            continue

        image_str = message_structure.get('image', None)
        if isinstance(image_str, str):
            # Unquote url
            typing.cast(ImageStructureInterface, message_structures[i])['image'] = unquote(image_str)
            file_id = telegram_cache.get_file_id(
                typing.cast(ImageStructureInterface, message_structures[i])['image'], 'img')
            typing.cast(ImageStructureInterface, message_structures[i])['file_id'] = file_id
    return message_structures


def build_markup(message_structure: TextStructureInterface):
    markup = message_structure.get('reply_markup')
    if markup is None or len(markup) == 0:
        return None

    keyboard_builder = None

    # Inline markup
    if message_structure.get('markup_type', 'inline') == 'inline':
        keyboard_builder = telegram_types.InlineKeyboardMarkup()
        for row in markup:
            if row is None:
                continue

            row_buttons = []
            for button_data in row:
                if button_data is None:
                    continue

                # button_data = cast(InlineButtonData, button_data)
                # if validate_typed_dict_interface(button_data, InlineButtonData):
                callback_data = None
                if 'callback_data' in button_data:
                    if isinstance(button_data['callback_data'], str):
                        callback_data = button_data['callback_data']
                    elif isinstance(button_data['callback_data'], dict):
                        callback_data = json.dumps(button_data['callback_data'])

                row_buttons.append(telegram_types.InlineKeyboardButton(
                    text=button_data['text'],
                    callback_data=callback_data,
                    url=button_data.get('url', None)
                ))

            keyboard_builder.row(*row_buttons)

    # # Reply markup
    # else:
    #     keyboard_builder = keyboard.ReplyKeyboardBuilder()
    #     for row in markup:
    #         row_buttons = []
    #         for button_data in row:
    #             button_data = cast(InlineButtonData, button_data)
    #             if validate_typed_dict_interface(button_data, ButtonRequestChatData):
    #                 button_data = cast(ButtonRequestChatData, button_data)
    #
    #                 user_administrator_rights, bot_administrator_rights = [telegram_types.ChatAdministratorRights(
    #                     can_delete_messages=rights.get('can_delete_messages', None)
    #                 ) if rights is not None else None for rights in [
    #                                                                            button_data.get(
    #                                                                                'user_administrator_rights', None),
    #                                                                            button_data.get(
    #                                                                                'bot_administrator_rights', None)]]
    #
    #                 row_buttons.append(keyboard.KeyboardButton(
    #                     text=button_data.get('text', ''),
    #                     request_chat=telegram_types.KeyboardButtonRequestChat(
    #                         request_id=button_data['request_id'],
    #                         chat_is_channel=button_data['chat_is_channel'],
    #                         chat_is_forum=button_data.get('chat_is_forum', None),
    #                         chat_has_username=button_data.get('chat_has_username', None),
    #                         chat_is_created=button_data.get('chat_is_created', None),
    #                         user_administrator_rights=user_administrator_rights,
    #                         bot_administrator_rights=bot_administrator_rights,
    #                         bot_is_member=button_data.get('bot_is_member', None)
    #                     )
    #                 ))
    #
    #         keyboard_builder.row(*row_buttons)
    return keyboard_builder


def skip_not_modified(e: Exception):
    if (
            'specified new message content and reply markup are exactly the same as a current content'
            ' and reply markup of the message'
    ) not in str(e):
        return False


def render_messages(chat_id: int,
                    message_structures: list[MessageStructuresInterface] | None = None, resending: bool = False) \
        -> list[ResultMessageStructuresInterface]:
    if message_structures is None:
        message_structures = []

    resending |= storage.get_user_resend_flag(chat_id)

    previous_message_structures = storage.get_message_structures(chat_id) if resending is False else []

    try:
        new_message_structures: list[ResultMessageStructuresInterface] = message_master(
            bot, chat_id, resending=resending, message_structures=message_structures,
            previous_message_structures=previous_message_structures)

        def prepare_for_cache(m: ResultMessageStructuresInterface) -> ResultMessageStructuresInterface:
            return {
                'id': m['id'],
                'type': m['type']
            }

        prepared_for_cache_message_structures: list = [prepare_for_cache(m) for m in new_message_structures]
        storage.set_user_message_structures(chat_id, prepared_for_cache_message_structures)
        storage.del_user_resend_flag(chat_id)

        return new_message_structures

    except (ApiTelegramException, ApiException) as e:
        pause = get_timeout_from_error_bot(e)
        if pause is not None:
            # TODO: Schedule resending?
            return previous_message_structures

        elif bot_blocked_reaction(e, chat_id):
            return previous_message_structures

        elif message_to_edit_not_found(e):
            return render_messages(chat_id, message_structures, resending=True)

        else:
            logger.err(e)
            raise e

    except Exception as e:
        logger.err(e)
        raise e


# For messages not included in state system: promo, podcast upload statuses etc...
def outer_sender(chat_id: int, message_structures: list[MessageStructuresInterface]) \
        -> list[ResultMessageStructuresInterface]:
    try:
        result = message_master(bot, chat_id, resending=True, message_structures=message_structures)
        storage.set_user_resend_flag(chat_id)
        return result

    except (ApiTelegramException, ApiException) as e:
        pause = get_timeout_from_error_bot(e)

        if pause:
            # TODO: Schedule resending?
            return []
        elif bot_blocked_reaction(e, chat_id):
            return []
        else:
            logger.err(e)
            raise e

    except Exception as e:
        logger.err(e)
        raise e


def message_deleter(chat_id: int, message_id: int):
    bot.delete_message(chat_id, message_id)


def message_editor(chat_id: int, message_structure: MessageStructuresInterface, old_message_id: int):
    [message_structure] = prepare_images([message_structure])
    reply_markup = build_markup(message_structure)
    try:
        if message_structure['type'] == MasterMessages.text.value:
            bot.edit_message_text(
                text=message_structure.get('text', None),
                chat_id=chat_id,
                message_id=old_message_id,
                parse_mode=message_structure.get('parse_mode', DEFAULT_PARSE_MODE),
                reply_markup=reply_markup,
                disable_web_page_preview=message_structure.get('disable_web_page_preview', None))

        elif message_structure['type'] in [MasterMessages.image.value, MasterMessages.audio.value]:
            if message_structure['type'] == MasterMessages.image.value:
                media = InputMedia(
                    type="photo",
                    media=image_digger(typing.cast(ImageStructureInterface, message_structure)))
            elif message_structure['type'] == MasterMessages.audio.value:
                media = InputMedia(
                    type="audio",
                    media=typing.cast(AudioStructureInterface, message_structure)['audio'])
            else:
                media = None

            bot.edit_message_media(
                media=media,
                chat_id=chat_id,
                message_id=old_message_id,
                reply_markup=reply_markup)
            if message_structure.get('text', None) is not None:
                bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=old_message_id,
                    caption=message_structure.get('text', None),
                    parse_mode=message_structure.get('parse_mode', DEFAULT_PARSE_MODE))
        else:
            raise TypeError(f"Not implemented: {message_structure['type']}")

    except ApiTelegramException as e:
        if skip_not_modified(e):
            raise e


def message_master(
        bot, chat_id, resending: bool = False,
        message_structures: list[MessageStructuresInterface] = [],
        previous_message_structures: list[ResultMessageStructuresInterface] = []
) -> list[ResultMessageStructuresInterface]:
    # Process images
    message_structures = prepare_images(copy.deepcopy(message_structures))

    def message_structure_filter(filtrating_message_structure):
        return filtrating_message_structure['type'] in typing.get_args(MESSAGE_TYPES)

    message_structures = list(filter(message_structure_filter, message_structures))

    # Mark old messages as delete, new as send and old-to-new as edit
    messages_to_delete = []  # old messages
    messages_to_edit = {}  # old message id => new message structure
    messages_to_send = []  # new messages

    if resending:
        previous_message_structures = []

    # Constructing
    i = 0
    message_structures_len = len(message_structures)
    for previous_message_structure in previous_message_structures:
        if i >= message_structures_len:
            messages_to_delete.append(previous_message_structure)
            continue

        message_structure = message_structures[i]
        if previous_message_structure['type'] != message_structure['type']:
            messages_to_delete.append(previous_message_structure)
        else:
            messages_to_edit[previous_message_structure['id']] = message_structure
            i += 1

    for j in range(i, message_structures_len):
        messages_to_send.append(message_structures[j])

    # Array to return
    new_message_structures = []

    # Deleting unwanted messages
    for message_to_delete in messages_to_delete:
        try:
            bot.delete_message(chat_id, message_to_delete['id'])
        except Exception:
            messages_to_send = message_structures
            messages_to_edit = {}
            break

    result: telegram_types.Message | None

    # Editing old messages
    for message_to_edit_id in messages_to_edit:
        edit_message_structure: MessageStructuresInterface = messages_to_edit[message_to_edit_id]

        reply_markup = build_markup(edit_message_structure)

        try:
            if edit_message_structure['type'] == MasterMessages.text.value:
                result = bot.edit_message_text(
                    text=edit_message_structure.get('text', None),
                    chat_id=chat_id,
                    message_id=message_to_edit_id,
                    parse_mode=edit_message_structure.get('parse_mode', DEFAULT_PARSE_MODE),
                    reply_markup=reply_markup,
                    disable_web_page_preview=edit_message_structure.get('disable_web_page_preview', None))

            elif edit_message_structure['type'] in [MasterMessages.image.value, MasterMessages.audio.value]:
                if edit_message_structure['type'] == MasterMessages.image.value:
                    media = InputMedia(
                        type='photo',
                        media=image_digger(typing.cast(ImageStructureInterface, edit_message_structure)))
                elif edit_message_structure['type'] == MasterMessages.audio.value:
                    media = InputMedia(
                        type='audio',
                        media=typing.cast(AudioStructureInterface, edit_message_structure)['audio'])
                else:
                    media = None

                result = bot.edit_message_media(
                    media=media,
                    chat_id=chat_id,
                    message_id=message_to_edit_id,
                    reply_markup=reply_markup)
                bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_to_edit_id,
                    caption=edit_message_structure.get('text', None),
                    parse_mode=edit_message_structure.get('parse_mode', DEFAULT_PARSE_MODE))

            else:
                result = None

            if result is not None:
                new_message_structures.append(
                    build_new_prev_message_structure(result.message_id,
                                                     typing.cast(MESSAGE_TYPES, edit_message_structure['type']),
                                                     result))

        except ApiTelegramException as e:
            if skip_not_modified(e):
                raise e

            new_message_structures.append(
                build_new_prev_message_structure(message_to_edit_id,
                                                 typing.cast(MESSAGE_TYPES, edit_message_structure['type'])))

    # Sending new messages
    for message_to_send in messages_to_send:
        send_message_structure = message_to_send

        reply_markup = build_markup(send_message_structure)

        if send_message_structure['type'] == MasterMessages.text.value:
            result = bot.send_message(
                chat_id=chat_id,
                text=send_message_structure.get('text', None),
                parse_mode=send_message_structure.get('parse_mode', DEFAULT_PARSE_MODE),
                reply_markup=reply_markup,
                disable_web_page_preview=send_message_structure.get('disable_web_page_preview', None))

        elif send_message_structure['type'] == MasterMessages.image.value:
            result = bot.send_photo(
                chat_id=chat_id,
                photo=image_digger(typing.cast(ImageStructureInterface, send_message_structure)),
                caption=send_message_structure.get('text', None),
                parse_mode=send_message_structure.get('parse_mode', DEFAULT_PARSE_MODE),
                reply_markup=reply_markup)

        elif send_message_structure['type'] == MasterMessages.audio.value:
            result = bot.send_audio(
                chat_id=chat_id,
                audio=typing.cast(AudioStructureInterface, send_message_structure)['audio'],
                duration=typing.cast(AudioStructureInterface, send_message_structure).get('audio_data', {}).get(
                    'duration', None),
                performer=typing.cast(AudioStructureInterface, send_message_structure).get('audio_data', {}).get(
                    'performer', None),
                title=typing.cast(AudioStructureInterface, send_message_structure).get('audio_data', {}).get(
                    'title', None),
                caption=send_message_structure.get('text', None),
                parse_mode=send_message_structure['parse_mode'],
                reply_markup=send_message_structure['reply_markup'])

        else:
            result = None

        if result is not None:
            # Save message type
            message_type = \
                send_message_structure['type'] if send_message_structure.get('markup_type', 'inline') != 'reply' \
                    else f"{send_message_structure['type']}_reply"
            new_message_structures.append(
                build_new_prev_message_structure(result.message_id, message_type, result))

            # Save files id
            if result.photo is not None and send_message_structure.get('file_id', None) is None:
                if isinstance(typing.cast(ImageStructureInterface, send_message_structure)['image'], str):
                    telegram_cache.add_file_id(
                        typing.cast(ImageStructureInterface, send_message_structure)['image'],
                        result.photo[0].file_id, 'img')
                elif isinstance(typing.cast(AudioStructureInterface, send_message_structure)['audio'], str):
                    telegram_cache.add_file_id(
                        typing.cast(str, typing.cast(AudioStructureInterface, send_message_structure)['audio']),
                        result.photo[0].file_id, 'audio')

    return new_message_structures
