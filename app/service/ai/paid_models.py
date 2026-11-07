# -*- coding: utf-8 -*-
"""Better AI models for chats that pay, turned on by the payment.

Each model is optional in constants.py (config.ai_paid_transcribe_model,
config.ai_paid_summary_model); with neither nothing here shows or changes.
The transcription one labels who speaks ("Speaker 2: ..."); the other writes
summaries and answers questions. The owner's call (2026-11-02): no higher
cost without paying users, so the free models stay for everyone else.

- Who: a chat that paid (tariff_rows.paid_for_days: a payment or a Patreon
  credit) with a plan running, and users.flags FLAG on. A payment turns it on
  (db/payment_effects, effect PAID_MODELS, app/jobs/payment_effects.py) unless
  the user turned it off: their choice stays. /settings (AI) shows the switch
  to such chats only. A plan that ends keeps the flag; the models come back
  with the plan.
- A transcript is made once per episode and is free to anyone after, so the
  better one serves every later reader. A paying chat asking for an episode
  whose transcript Whisper made gets it made again with speakers (charged to
  its hours as a new one; over them, the Whisper file). The feed's own
  transcript is the publisher's: it is used for everyone, so nothing is
  promised about it.
- Copy (`standing`): the trial is told what paying adds, an ended paid plan
  what renewing brings back, a chat that never had a plan what a paid plan
  brings; a paying chat that turned the models off is told nothing.
"""
from app.i18n.messages import get_message
from app.service.plan import entitlements
from config import ai_paid_summary_model, ai_paid_transcribe_model, ai_summary_model, ai_transcribe_model, db_path
from lib.tools.logger import logger

FLAG = 'paid_models'  # users.flags: 1 on (a payment sets it), 0 the user turned it off
TOGGLE_ACTION = 'aiPaid'
SPEAKERS = 'speakers'  # ai_transcripts.source of a transcript made by the paid model, with speakers

# standing(): what the chat has, for the copy
ON = 'on'  # paid, a plan running, the models on
TURNED_OFF = 'turned_off'  # paid, a plan running, the user turned them off (or the payment's effect has not run)
LAPSED = 'lapsed'  # paid before, no plan running now
TRIAL = 'trial'  # a plan running that nobody paid for (the welcome trial, referral days)
NO_PLAN = 'no_plan'  # never paid, no plan running


def available() -> bool:
    return bool(ai_paid_transcribe_model or ai_paid_summary_model)


def standing(chat_id, database=None) -> str | None:
    """ON / TURNED_OFF / LAPSED / TRIAL / NO_PLAN; None when no paid model is configured."""
    if not available():
        return None
    from db.sqliteAdapter import SQLighter
    database = db_path if database is None else database
    rights = entitlements.of(chat_id, database)
    running = rights.running and rights.ai
    if not rights.paid:
        return TRIAL if running else NO_PLAN
    if not running:
        return LAPSED
    db = SQLighter(database)
    try:
        flag = db.get_user_flag(chat_id, FLAG)
    finally:
        db.close()
    return ON if flag == 1 else TURNED_OFF


def _on(chat_id, database=None) -> bool:
    try:
        return standing(chat_id, database) == ON
    except Exception as e:  # a model choice never fails a request: the usual model then
        logger.warn('paid models:', chat_id, type(e).__name__, e)
        return False


def speakers(chat_id, database=None) -> bool:
    """This chat's new transcripts are made by the paid model, with speakers."""
    return bool(ai_paid_transcribe_model) and _on(chat_id, database)


def speakers_fit(chat_id, seconds, database=None) -> bool:
    """speakers(), and making `seconds` of audio with the paid model fits the plan's AI budget
    (quota.budget): past it, Whisper."""
    if not speakers(chat_id, database):
        return False
    from app.service.ai import quota
    try:
        return quota.paid_transcribe_fits(chat_id, seconds, database=database)
    except Exception as e:  # a model choice never fails a request: the usual model then
        logger.warn('paid models budget:', chat_id, type(e).__name__, e)
        return False


def transcribe_model(with_speakers) -> str:
    return ai_paid_transcribe_model if with_speakers and ai_paid_transcribe_model else ai_transcribe_model


def summary_model(chat_id, database=None) -> str:
    """The model of this chat's new summaries and of its answers."""
    return ai_paid_summary_model if ai_paid_summary_model and _on(chat_id, database) else ai_summary_model


def what(language_code) -> str:
    """What the paid models give, as configured: a phrase that follows a colon."""
    key = ('paidModelsWhatBoth' if ai_paid_transcribe_model and ai_paid_summary_model
           else 'paidModelsWhatTranscript' if ai_paid_transcribe_model else 'paidModelsWhatSummary')
    return get_message(key, language_code)


def settings_help(language_code) -> str:
    """What /settings says to a chat that has them (on or turned off), with what they do not change:
    the feed's own transcript, a summary made before."""
    lines = [get_message('paidModelsSettingsHelp', language_code).format(what=what(language_code))]
    if ai_paid_transcribe_model:
        lines.append(get_message('paidModelsFeedNote', language_code))
    if ai_paid_summary_model:
        lines.append(get_message('paidModelsCachedNote', language_code))
    return ' '.join(lines)


def pitch(chat_id, language_code, database=None) -> str:
    """One line on what paying adds (or brings back), for the copy of the summary note and D-3;
    '' for a paying chat that has them or turned them off, or when none is configured."""
    try:
        kind = standing(chat_id, database)
    except Exception as e:
        logger.warn('paid models pitch:', chat_id, type(e).__name__, e)
        return ''
    key = {TRIAL: 'paidModelsTrial', LAPSED: 'paidModelsLapsed', NO_PLAN: 'paidModelsNoPlan'}.get(kind)
    return get_message(key, language_code).format(what=what(language_code)) if key else ''


def ending_line(chat_id, language_code, database=None) -> str:
    """D-3 of a paying chat that has them: they stop with the plan. '' otherwise."""
    try:
        return get_message('paidModelsEnding', language_code).format(what=what(language_code)) \
            if standing(chat_id, database) == ON else ''
    except Exception as e:
        logger.warn('paid models ending:', chat_id, type(e).__name__, e)
        return ''


def transcript_note(chat_id, source, language_code, database=None, over_quota=False) -> str:
    """Under a transcript file Whisper made: what a paid plan's transcript would have been ('' for a
    paying chat, for the feed's transcript and for one made with speakers). `over_quota`: a chat with
    them whose hours did not cover making it again with speakers."""
    if source != 'whisper' or not ai_paid_transcribe_model:
        return ''
    if over_quota:
        return get_message('paidTranscriptOverQuota', language_code)
    try:
        kind = standing(chat_id, database)
    except Exception as e:
        logger.warn('paid models note:', chat_id, type(e).__name__, e)
        return ''
    key = {TRIAL: 'paidTranscriptTrial', LAPSED: 'paidTranscriptLapsed', NO_PLAN: 'paidTranscriptNoPlan'}.get(kind)
    return get_message(key, language_code) if key else ''


def turn_on(user_id, database=None) -> bool:
    """The payment's effect: the flag on unless the user chose (it is set); True if it was turned on now.
    Idempotent: a second run finds it set."""
    from db.connection import connect_sqlite
    connection = connect_sqlite(db_path if database is None else database)
    try:
        with connection:
            return connection.execute(
                "UPDATE users SET flags = json_set(COALESCE(flags, '{}'), '$.%s', 1) "
                "WHERE id = ? AND json_extract(COALESCE(flags, '{}'), '$.%s') IS NULL" % (FLAG, FLAG),
                (int(user_id),)).rowcount > 0
    finally:
        connection.close()


def paying_users(database=None) -> list[int]:
    """users.id of the chats that paid (as paid_for_days reads it) and have a plan running: those who
    paid before the effect existed."""
    from db.connection import connect_sqlite
    database = db_path if database is None else database
    connection = connect_sqlite(database)
    try:
        running = connection.execute(
            "SELECT DISTINCT u.id, u.telegramId FROM users u JOIN user_tariff_cs ut ON ut.uid = u.id "
            "WHERE ut.tariff_id > 0 AND ut.time_left > 0").fetchall()
    finally:
        connection.close()
    return [user_id for user_id, telegram_id in running
            if telegram_id and _paid_with_ai(entitlements.of(telegram_id, database))]


def _paid_with_ai(rights) -> bool:
    return rights.running and rights.paid and rights.ai
