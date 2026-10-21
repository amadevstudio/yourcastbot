# -*- coding: utf-8 -*-
"""What a user hears when a new summary does not fit: the plans, or what is left.

Shared by the Summary button (summaryModule) and summaries of new episodes
(auto.py): one offer, one set of storefront rules.
"""
from app.i18n.messages import get_message
from app.service.ai.quota import Quota
from config import ai_summary_hours_per_month


def length_text(seconds, language_code) -> str:
    """'1 h 30 min', '45 min', '5 h': minutes rounded up."""
    hours, minutes = divmod(-(-int(seconds) // 60), 60)
    parts = [get_message('summaryHours', language_code).format(h=hours)] if hours else []
    if minutes or not hours:
        parts.append(get_message('summaryMinutes', language_code).format(m=minutes))
    return ' '.join(parts)


def offer_message(language_code, quota: Quota) -> dict:
    """No plan: every plan with its Stars invoice, as at the free episode limit. A running plan:
    an invoice would only top it up (storefront rules), so the Stars page and change-plan.
    The top plan: only what is left."""
    from app.service.payment.storefront import relay_nudge_markup
    from app.service.record.free_limit import plans_offer
    if not quota.limit:
        text = get_message('summaryForPlans', language_code).format(
            relay=ai_summary_hours_per_month.get(3, 0), silver=ai_summary_hours_per_month.get(2, 0),
            bronze=ai_summary_hours_per_month.get(1, 0))
        plans_text, rows = plans_offer(language_code)
        return {'type': 'text', 'text': text + '\n\n' + plans_text.strip(), 'reply_markup': rows,
                'disable_web_page_preview': True}
    text = get_message('summaryQuota', language_code).format(
        limit=length_text(quota.limit, language_code),
        left=length_text(quota.left, language_code),
        needed=length_text(quota.needed, language_code))
    if quota.top_plan:
        return {'type': 'text', 'text': text, 'disable_web_page_preview': True}
    more = (get_message('summaryTrialMore', language_code).format(relay=ai_summary_hours_per_month.get(3, 0))
            if quota.trial else get_message('summaryBiggerPlan', language_code))
    return {'type': 'text', 'text': text + ' ' + more,
            'reply_markup': relay_nudge_markup(language_code), 'disable_web_page_preview': True}
