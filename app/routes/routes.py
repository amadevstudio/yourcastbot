from typing import TypedDict, Callable, Literal, Dict, Optional, Required

from app.controller.builders import welcomeModule, menuModule, subsModule, searchModule, podcastModule, recsModule, \
    helpModule, channelModule, topModule, adminModule
from app.jobs import podcastsUpdater
from app.routes.routes_list import AvailableCommands, AvailableRoutes, AvailableActions
from app.routes.ptypes import ControllerParams
from app.service.payment import paymentModule, patreonPaymentModule, cryptoBotPaymentModule, robokassaPaymentModule


class RouteActionsInterface(TypedDict, total=False):
    method: Required[Callable[[ControllerParams], None]]
    state_independent: bool  # Available in any state, default is False


class RouteInterface(TypedDict, total=False):
    method: Required[Callable[[ControllerParams], None | bool]]
    available_from: Required[list[Literal['command', 'message', 'call']]]  # Which types of action trigger the route
    commands: Optional[list[AvailableCommands]]  # Commands that triggers the route
    routes: Optional[list[AvailableRoutes]]  # Routes that can be reached directly
    waits_for_input: Optional[bool]  # If the route may trigger 'empty' state and the route waits for input, auto goback
    states_for_input: Optional[list[AvailableRoutes]]  # States for message input (for example, its own name)
    actions: Optional[Dict[AvailableActions, RouteActionsInterface]]  # Buttons which don't change pages
    validator: Optional[Callable[[ControllerParams], bool]]
    # have_under_keyboard: bool | None # Not implemented


class RouteMap:
    ROUTES: Dict[AvailableRoutes, RouteInterface | None] = {
        'start': {
            'method': welcomeModule.start,
            'available_from': ['command', 'call'],
            'routes': ['menu', 'search', 'podcast']
        },

        'privacy': {
            'method': helpModule.privacy,
            'available_from': ['command'],
        },

        'menu': {
            'method': menuModule.send_menu_message,
            'available_from': ['command', 'call'],
            'routes': ['subs', 'search', 'another', 'update', 'botSub', 'help', 'addChByRss', 'myTgChannels'],
        },

        'search': {
            'method': searchModule.search,
            'available_from': ['command', 'call', 'message'],
            'routes': ['podcast'],
            'waits_for_input': True,
        },

        'subs': {
            'method': subsModule.show_subs,
            'available_from': ['command', 'call', 'message'],
            'commands': ['subscriptions'],
            'routes': ['podcast'],
            'waits_for_input': True,
        },

        'podcast': {
            'method': podcastModule.channel_query,
            'available_from': ['call'],
            'routes': ['recs'],
            'actions': {
                'subscription': {
                    'method': podcastModule.switch_subscription
                },
                'notifications': {
                    'method': podcastModule.change_channel_notify
                },
                'rate': {
                    'method': podcastModule.rate
                }
            }
        },
        'recs': {
            'method': recsModule.open_recs,
            'available_from': ['call', 'message'],
            'actions': {
                'rec': {
                    'method': recsModule.send_record,
                    'state_independent': True,
                },
                'nrec': {
                    'method': recsModule.send_record,
                    'state_independent': True,
                }
            }
        },

        'another': {
            'method': helpModule.show_another_projects,
            'available_from': ['call', 'command'],
        },

        'update': {
            'method': podcastsUpdater.update_feed,
            'available_from': ['call', 'command']
        },

        'donate': {
            'method': paymentModule.open_donate_page,
            'available_from': ['call', 'command']
        },

        'botSub': {
            'method': paymentModule.open_subscription_page,
            'available_from': ['call', 'command'],
            'commands': ['subscription', 'payment'],
            'routes': ['bs_trfs', 'bs_patr', 'bs_cryptobot']
        },
        'bs_trfs': {
            'method': paymentModule.open_subscription_tariffs_page,
            'available_from': ['call'],
            'routes': ['bs_trf_v']
        },
        'bs_trf_v': {
            'method': paymentModule.choose_bot_subscription_tariff,
            'available_from': ['call']
        },
        'bs_patr': {
            'method': patreonPaymentModule.open_subscription_page,
            'available_from': ['call'],
            'actions': {
                'bs_patrupd': {
                    'method': patreonPaymentModule.patreon_force_watcher
                }
            },
            'routes': ['bs_patrem']
        },
        'bs_patrem': {
            'method': patreonPaymentModule.patreon_email_input_page,
            'available_from': ['call', 'message'],
        },
        'bs_cryptobot': {
            'method': cryptoBotPaymentModule.open_subscription_page,
            'available_from': ['call'],
            'routes': ['bs_crbot_input']
        },
        'bs_crbot_input': {
            'method': cryptoBotPaymentModule.open_amount_input_page,
            'available_from': ['call', 'message'],
            'waits_for_input': True,
        },
        'bs_robokassa': {
            'method': robokassaPaymentModule.open_subscription_payment_page,
            'available_from': ['call'],
            'routes': ['bs_robokassa_input'],
        },
        'bs_robokassa_input': {
            'method': robokassaPaymentModule.generate_subscription_payment_message,
            'available_from': ['call', 'message'],
            'waits_for_input': True,
            'states_for_input': ['bs_robokassa', 'bs_robokassa_input']
        },

        'help': {
            'method': helpModule.open_help,
            'available_from': ['call', 'command'],
        },

        'addChByRss': {
            'method': searchModule.open_adding_by_rss_page,
            'available_from': ['call'],
            'routes': ['addBRss', 'podcast']
        },
        'addBRss': {
            'method': searchModule.show_adding_rss_result,
            'available_from': ['call', 'message'],
            'states_for_input': ['addBRss', 'addChByRss']
        },

        'myTgChannels': {
            'method': channelModule.open_connecting_channel,
            'available_from': ['command', 'call'],
            'commands': ['my_tg_channels'],
            'routes': ['addTgChannel', 'myTgChnlList']
        },
        'addTgChannel': {
            'method': channelModule.channel_input_page,
            'available_from': ['call', 'message']
        },
        'myTgChnlList': {
            'method': channelModule.open_channel_list,
            'available_from': ['call', 'message'],
            'routes': ['myTgChannel']
        },
        'myTgChannel': {
            'method': channelModule.open_connected_channel,
            'available_from': ['call'],
            'routes': ['myTgChSubs'],
            'actions': {
                'myTgChDel': {
                    'method': channelModule.delete_channel
                },
                'changeTgChActive': {
                    'method': channelModule.change_channel_active
                }
            }
        },
        'myTgChSubs': {
            'method': channelModule.open_channel_subs,
            'available_from': ['call', 'message'],
            'actions': {
                'myTgChSubChActive': {
                    'method': channelModule.change_channel_sub_active

                }
            }
        },

        'topGnrs': {
            'method': topModule.show_genres,
            'available_from': ['call', 'message', 'command'],
            'commands': ['top'],
            'waits_for_input': True
        },
        'top_ch': {
            'method': topModule.show_top,
            'available_from': ['call', 'message'],
            'waits_for_input': True
        },

        'usersCount': {
            'method': adminModule.send_users_count_to_creator,
            'available_from': ['command'],
            'validator': adminModule.is_admin
        },
        'admin_restartBot': {
            'method': adminModule.restart_bot,
            'available_from': ['command'],
            'validator': adminModule.is_admin
        },
        'addToBalance': {
            'method': adminModule.add_to_balance,
            'available_from': ['command'],
            'validator': adminModule.is_admin
        },
        'cmd': {
            'method': adminModule.show_commands,
            'available_from': ['command'],
            'validator': adminModule.is_admin
        },

        'empty': None
    }

# Disabled routes
# # страница оплаты
    # @thonbot.on(events.CallbackQuery(
    # 	func=lambda call: getTp(call.data) == 'bs_pmnt'))
    # async def openSubscriptionPaymentPage(event):
    # 	data = await telebot_msg_or_call_parody(event)
    # 	handleEventInThread({
    # 		'action': paymentModule.openSubscriptionPaymentPage, 'data': data})
    # # показать сообщение с сылкой на подписку и суммой из кнопки или сообщения
    # def test_subscription_amount(event):
    # 	return test_message(event, 'bs_pmnt')
    # @thonbot.on(events.NewMessage(incoming=True, func=test_subscription_amount))
    # @thonbot.on(events.CallbackQuery(
    # 	func=lambda call: getTp(call.data) == "bs_pmnt_inpv"))
    # async def generateSubsctiptionPaymentMessage(event):
    # 	data = await telebot_msg_or_call_parody(event)
    # 	handleEventInThread({
    # 		'action': paymentModule.generateSubsctiptionPaymentMessage, 'data': data})
    # Patreon
    # подписаться через Patreon
