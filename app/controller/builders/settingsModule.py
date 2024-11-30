# import json
#
# from telebot import types
#
# from app.controller.general.notify import notify
# from app.service.payment.paymentSafeModule import is_subscription_active
# from lib.telegram.general.message_master import message_master
# from app.i18n.messages import get_message
# from app.repository.storage import storage
# from config import db_path, std_bitrate
# from db.sqliteAdapter import SQLighter
#
#
# def openSettings(bot, data):
#     stmsg = constructSettingsMessage(data.from_user.language_code)
#     message_master(
#         bot, data.chat.id, stmsg["message"], stmsg["markup"])
#     storage.clear_user_storage(data.chat.id)
#     storage.add_user_state(data.chat.id, "menu")
#     storage.add_user_state(data.chat.id, "setts")
#
#
# def constructSettingsMessage(language_code):
#     message_text = "*" \
#                    + get_message("bot_settings", language_code) + "*"
#     menuKeyBoard = types.InlineKeyboardMarkup()
#     menuKeyBoard.add(types.InlineKeyboardButton(
#         text=get_message("bitrate", language_code),
#         callback_data="{\"tp\": \"s_btrt\"}"))
#     menuKeyBoard.add(types.InlineKeyboardButton(
#         text=get_message("goBackMenu", language_code),
#         callback_data="{\"tp\": \"bck\"}"))
#
#     result = {
#         "message": message_text,
#         "markup": menuKeyBoard
#     }
#     return result
#
#
# def bitrateSettings(bot, call, changeState=True):
#     if call.message:
#
#         db_users = SQLighter(db_path)
#         user = db_users.get_user_by_tg(call.chat.id)
#         subscription = db_users.getUserSubscriptionByTg(call.chat.id)
#
#         bitrate = std_bitrate
#         if user['bitrate'] is not None:
#             # если больше максимального, нет тарифа и одновременно действие подписки
#             if not is_subscription_active(subscription):
#                 db_users.update_bitrate_by_tg(call.chat.id, None)
#             else:
#                 bitrate = user['bitrate']
#
#         db_users.close()
#
#         btrtsmsg = construct_bitrate_settings_message(
#             call.from_user.language_code, bitrate)
#
#         message_master(
#             bot, call.chat.id, btrtsmsg['message'],
#             btrtsmsg['markup'], call.message.message_id)
#
#         if changeState:
#             storage.add_user_state(call.chat.id, "setts_btrt")
#
#
# def construct_bitrate_settings_message(language_code, bitrate):
#     if bitrate is None:
#         bitrate_text = get_message('original', language_code).lower()
#     else:
#         bitrate_text = bitrate
#
#     bitrateSettingsMsg = get_message(
#         "bitrate_settings_description", language_code) + " " + bitrate_text
#
#     menuKeyBoard = types.InlineKeyboardMarkup()
#     menuKeyBoard.add(types.InlineKeyboardButton(
#         text=('* ' if bitrate is None else '')
#              + get_message("do_not_change_bitrate", language_code),
#         callback_data=json.dumps({"tp": "chbtrt", "v": None})))
#     b1 = types.InlineKeyboardButton(
#         text=('* ' if bitrate == '128' else '') + "128 kbit/s",
#         callback_data="{\"tp\": \"chbtrt\", \"v\": \"128\"}")
#     b2 = types.InlineKeyboardButton(
#         text=('* ' if bitrate == '96' else '') + "96 kbit/s",
#         callback_data="{\"tp\": \"chbtrt\", \"v\": \"96\"}")
#     menuKeyBoard.add(b1, b2)
#     b1 = types.InlineKeyboardButton(
#         text=('* ' if bitrate == '64' else '') + "64 kbit/s",
#         callback_data="{\"tp\": \"chbtrt\", \"v\": \"64\"}")
#     b2 = types.InlineKeyboardButton(
#         text=('* ' if bitrate == '40' else '') + "40 kbit/s",
#         callback_data="{\"tp\": \"chbtrt\", \"v\": \"40\"}")
#     menuKeyBoard.add(b1, b2)
#     menuKeyBoard.add(types.InlineKeyboardButton(
#         text=get_message("goBack", language_code),
#         callback_data="{\"tp\": \"bck\"}"))
#
#     return {
#         "message": bitrateSettingsMsg,
#         "markup": menuKeyBoard
#     }
#
#
# def changeBitrate(bot, call):
#     if call.message:
#         # ограничение подписок
#         db_users = SQLighter(db_path)
#         subscription = db_users.getUserSubscriptionByTg(call.chat.id)
#
#         # если больше максимального, нет тарифа и одновременно действие подписки
#         if subscription is None or not (subscription['tariff_id'] > 0 and subscription['time_left'] > 0):
#             db_users.update_bitrate_by_tg(call.chat.id, None)
#             app.controller.general.error.goBackError(
#                 bot, "withoutTariffCantChooseBitrate", call.chat.id,
#                 call.from_user.language_code,
#                 call.message.message_id)
#             db_users.close()
#             return
#
#         call_data = json.loads(call.data)
#         bitrate = call_data['v']
#         try:
#             user = db_users.get_user_by_tg(call.chat.id)
#             if user['bitrate'] == bitrate:
#                 return
#
#             db_users.update_bitrate_by_tg(call.chat.id, bitrate)
#             db_users.close()
#
#             if bitrate is None:
#                 bitrate_text = get_message(
#                     'original', call.from_user.language_code).lower()
#             else:
#                 bitrate_text = bitrate
#             notify(
#                 bot, call, get_message(
#                     "bitrate_changed", call.from_user.language_code) + bitrate_text)
#
#             btrtsmsg = construct_bitrate_settings_message(
#                 call.from_user.language_code, bitrate)
#             message_master(
#                 bot, call.chat.id, btrtsmsg['message'],
#                 btrtsmsg['markup'], call.message.message_id)
#         except Exception:
#             try:
#                 notify(
#                     bot, call,
#                     get_message("somethingWentWrong", call.from_user.language_code),
#                     alert=True)
#             except Exception:
#                 pass
