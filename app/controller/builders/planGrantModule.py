# -*- coding: utf-8 -*-
"""Free Bronze for subscribing to the owner's channels: its screen (route channels.SCREEN, from
/subscription and from the "free Bronze is off" message) and "Check" (channels.CHECK_ACTION, state
independent: the button of an older screen still works). The rules: app/service/plan/channels.py.
Lock: python app/service/plan/test_channels.py
"""
from app.controller.general.notify import notify
from app.i18n.messages import get_message
from app.routes.message_tools import go_back_inline_markup
from app.routes.ptypes import ControllerParams
from app.service import analytics_events
from app.service.plan import channels
from db import plan_grants
from lib.telegram.general.message_master import render_messages

ANSWERS = {
    plan_grants.BUSY: 'chanPlanBusy',
    plan_grants.UNKNOWN: 'error',
    'missing': 'chanPlanMissing',
    'failed': 'chanPlanCheckFailed',
    'unavailable': 'chanPlanUnavailable',
}


def open_screen(data: ControllerParams):
    render_messages(data['chat_id'], [channels.screen_message(data['chat_id'], data['language_code'])])


def check(data: ControllerParams):
    language_code = data['language_code']
    outcome, absent = channels.start(data['chat_id'], channels.settings())
    if outcome in ANSWERS:
        notify(data['callback'], data['message'],
               get_message(ANSWERS[outcome], language_code).format(channels=channels.names(absent)), alert=True)
        return False
    if outcome == plan_grants.STARTED:
        notify(data['callback'], data['message'], '')
        analytics_events.track(data['chat_id'], 'plan_grant_started', {'kind': channels.KIND})
        render_messages(data['chat_id'], [{
            'type': 'text', 'text': get_message('chanPlanOn', language_code),
            'reply_markup': go_back_inline_markup(language_code)}])
        return True
    notify(data['callback'], data['message'], get_message('chanPlanActive', language_code))
    open_screen(data)
    return True
