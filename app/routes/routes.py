from typing import TypedDict, Callable, Literal, Dict, Optional, Required

from app.controller.builders import welcomeModule, menuModule, subsModule, searchModule, podcastModule, recsModule, \
    helpModule, channelModule, topModule, adminModule, settingsModule, summaryModule, episodeTextModule
from app.jobs import podcastsUpdater
from app.routes.routes_list import AvailableCommands, AvailableRoutes, AvailableActions
from app.routes.ptypes import ControllerParams
from app.service.ai import auto as ai_auto, summary as ai_summary
from app.service.record.text_format import DESCRIPTION_ACTION, EPISODE_FORMAT_ACTIONS, EPISODE_FORMAT_HINT_ACTION
from app.service.payment import (
    paymentModule,
    patreonPaymentModule,
    cryptoBotPaymentModule,
    robokassaPaymentModule,
    starsPaymentModule,
)


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
            'routes': ['menu', 'search', 'podcast'],
            'actions': {
                # the welcome checkboxes work from any screen: the first message stays in the chat
                'wPick': {'method': welcomeModule.toggle_pick, 'state_independent': True},
                'wSub': {'method': welcomeModule.subscribe_picked, 'state_independent': True},
            },
        },

        'privacy': {
            'method': helpModule.privacy,
            'available_from': ['command'],
        },

        'menu': {
            'method': menuModule.send_menu_message,
            'available_from': ['command', 'call'],
            'routes': ['subs', 'search', 'another', 'update', 'botSub', 'help', 'addChByRss', 'myTgChannels', 'setts'],
        },

        'search': {
            'method': searchModule.search,
            'available_from': ['command', 'call', 'message'],
            # a podcast's name typed on the welcome screen or the menu is a search too:
            # it used to be ignored there (only the search screen took text)
            'states_for_input': ['search', 'start', 'menu'],
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
                },
                # Summary under an episode file: the file stays in the chat
                ai_summary.ACTION: {
                    'method': summaryModule.request_summary,
                    'state_independent': True,
                },
                # Show notes under a brief episode: the feed's text, a reply to the audio
                DESCRIPTION_ACTION: {
                    'method': episodeTextModule.show_description,
                    'state_independent': True,
                },
            }
        },

        # Questions about an episode: the Ask button under a summary, then the user's text
        ai_summary.ASK_ACTION: {
            'method': summaryModule.ask,
            'available_from': ['call', 'message'],
            'waits_for_input': True,
            'actions': {
                ai_summary.ASK_DONE_ACTION: {
                    'method': summaryModule.finish_ask,
                    'state_independent': True,
                },
            },
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
            'routes': ['bs_trfs', 'bs_patr', 'bs_cryptobot', 'bs_stars', 'bs_robokassa']
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
        'bs_stars': {
            'method': starsPaymentModule.open_subscription_page,
            'available_from': ['call'],
            'routes': ['bs_stars_pay', 'bs_stars_sub']
        },
        'bs_stars_pay': {
            'method': starsPaymentModule.send_invoice,
            'available_from': ['call']
        },
        'bs_stars_sub': {
            'method': starsPaymentModule.send_subscription_offer,
            'available_from': ['call']
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

        'setts': {
            'method': settingsModule.open_settings,
            'available_from': ['command', 'call'],
            'commands': ['settings'],
            'routes': ['settsText', 'settsSum', 'settsRem'],
            'actions': {
                'digestMute': {
                    'method': settingsModule.mute_digest_reminders,
                    'state_independent': True,
                },
                'digestToggle': {
                    'method': settingsModule.toggle_digest_reminders,
                    'state_independent': True,
                },
                EPISODE_FORMAT_HINT_ACTION: {
                    'method': settingsModule.use_separate_episode_format,
                    'state_independent': True,
                },
                **{action: {
                    'method': settingsModule.set_episode_format_handler(episode_format),
                    'state_independent': True,
                } for action, episode_format in EPISODE_FORMAT_ACTIONS.items()},
                **{action: {
                    'method': settingsModule.set_summary_language_handler(choice),
                    'state_independent': True,
                } for action, choice in ai_summary.LANGUAGE_ACTIONS.items()},
                ai_auto.TOGGLE_ACTION: {
                    'method': settingsModule.toggle_auto_summary,
                    'state_independent': True,
                },
            }
        },

        'settsText': {
            'method': settingsModule.open_episode_text_settings,
            'available_from': ['call'],
        },

        'settsSum': {
            'method': settingsModule.open_summary_settings,
            'available_from': ['call'],
        },

        'settsRem': {
            'method': settingsModule.open_reminder_settings,
            'available_from': ['call'],
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
