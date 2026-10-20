from typing import Literal

AvailableRoutes = Literal[
    'start', 'privacy',
    'menu',
    'subs', 'feedStatus', 'listenLater',
    'search',
    'podcast', 'recs',
    'another',
    'update',
    'donate',
    'botSub', 'bs_trfs', 'bs_trf_v', 'bs_patr', 'bs_patrem',
    'bs_cryptobot', 'bs_crbot_input',
    'bs_stars', 'bs_stars_pay',
    'bs_robokassa', 'bs_robokassa_input',
    'help',
    'setts', 'settsText', 'settsRem',
    'addChByRss', 'addBRss',
    'MyTgChannels', 'addTgChannel', 'myTgChnlList', 'myTgChannel', 'myTgChSubs',
    'topGnrs', 'top_ch',

    # Admin commands
    'usersCount', 'admin_restartBot', 'addToBalance', 'cmd',

    'empty'
]


AvailableCommands = Literal[
    'start',
    'menu',
    'subscriptions', 'delivery_status', 'listen_later',
    'search',
    'subscription', 'payment',
    'top',
    'my_tg_channels',
    'settings'
]


AvailableActions = Literal[
    'update',
    'subscription', 'notifications',
    'rate',
    'rec', 'nrec', 'feedCheck', 'saveLater', 'removeLater', 'playLater',
    'digestMute', 'digestToggle',
    'episodeFormatRich', 'episodeFormatSeparate', 'episodeFormatCaption', 'episodeFormatMeta',
    'episodeFormatHint',
    'bs_patrupd',
    'myTgChDel', 'changeTgChActive', 'myTgChDel', 'myTgChSubChActive'
]
