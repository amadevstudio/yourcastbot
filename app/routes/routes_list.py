from typing import Literal

AvailableRoutes = Literal[
    'start', 'privacy',
    'menu',
    'subs',
    'search',
    'podcast', 'recs',
    'another',
    'update',
    'donate',
    'botSub', 'bs_trfs', 'bs_trf_v',
        'bs_patr', 'bs_patrem',
        'bs_cryptobot', 'bs_crbot_input',
        'bs_robokassa', 'bs_robokassa_input',
    'help',
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
    'subscriptions',
    'search',
    'subscription', 'payment',
    'top',
    'my_tg_channels'
]


AvailableActions = Literal[
    'update',
    'subscription', 'notifications',
    'rate',
    'rec', 'nrec',
    'bs_patrupd',
    'myTgChDel', 'changeTgChActive', 'myTgChDel', 'myTgChSubChActive'
]
