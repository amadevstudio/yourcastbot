# -*- coding: utf-8 -*-
"""What a user hears when a new summary does not fit: the plans, or what is left.

Shared by the Summary button (summaryModule) and summaries of new episodes
(auto.py): one offer, one set of storefront rules. A plan whose AI budget for
the 30 days is spent (quota.budget) hears that, whatever was asked.
"""
from app.i18n.messages import get_message
from app.service.ai.quota import Quota
from app.service.plan import features


def _hours(level):
    """A paid level's hours of AI audio in 30 days, as its profile has them."""
    return features.profile(features.level_key(level))['ai_hours']


def length_text(seconds, language_code) -> str:
    """'1 h 30 min', '45 min', '5 h': minutes rounded up."""
    hours, minutes = divmod(-(-int(seconds) // 60), 60)
    parts = [get_message('summaryHours', language_code).format(h=hours)] if hours else []
    if minutes or not hours:
        parts.append(get_message('summaryMinutes', language_code).format(m=minutes))
    return ' '.join(parts)


def budget_message(language_code, level) -> dict:
    """The plan's AI for these 30 days is spent; below the top plan a bigger one gives more
    (the Stars page and change-plan: an invoice would only top the running plan up)."""
    text = get_message('aiBudgetSpent', language_code)
    if level >= features.top_level():
        return {'type': 'text', 'text': text, 'disable_web_page_preview': True}
    from app.service.payment.storefront import relay_nudge_markup
    return {'type': 'text', 'text': text + ' ' + get_message('summaryBiggerPlan', language_code),
            'reply_markup': relay_nudge_markup(language_code), 'disable_web_page_preview': True}


def offer_message(language_code, quota: Quota, transcript=False) -> dict:
    """No plan: every plan with its Stars invoice, as at the free episode limit. A running plan:
    an invoice would only top it up (storefront rules), so the Stars page and change-plan.
    The top plan: only what is left. `transcript`: asked for the transcript, not a summary."""
    from app.service.payment.storefront import relay_nudge_markup
    from app.service.record.free_limit import plans_offer
    if quota.budget:
        return budget_message(language_code, quota.level)
    if not quota.limit:
        text = get_message('transcriptForPlans' if transcript else 'summaryForPlans', language_code).format(
            relay=_hours(3), silver=_hours(2), bronze=_hours(1))
        plans_text, rows = plans_offer(language_code)
        return {'type': 'text', 'text': text + '\n\n' + plans_text.strip(), 'reply_markup': rows,
                'disable_web_page_preview': True}
    text = get_message('transcriptQuota' if transcript else 'summaryQuota', language_code).format(
        limit=length_text(quota.limit, language_code),
        left=length_text(quota.left, language_code),
        needed=length_text(quota.needed, language_code))
    if quota.top_plan:
        return {'type': 'text', 'text': text, 'disable_web_page_preview': True}
    more = (get_message('summaryTrialMore', language_code).format(relay=_hours(3))
            if quota.trial else get_message('summaryBiggerPlan', language_code))
    return {'type': 'text', 'text': text + ' ' + more,
            'reply_markup': relay_nudge_markup(language_code), 'disable_web_page_preview': True}
