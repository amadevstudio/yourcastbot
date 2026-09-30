# -*- coding: utf-8 -*-
"""Hourly tariff clock: renew, then take an hour. No Telegram imports.

Runs from balance_watcher. A user with a tariff and enough balance must
never sit at time_left = 0: every tariff check (get_uccs_by_channel,
is_user_have_bot_subscription, is_subscription_active) reads 0 as "no
tariff". Renewing only at 0 left a paying user free for an hour each
period: the updater sent them the nosub digest and moved their last_guid
past the episode they paid to get.

Lock: python app/jobs/test_tariff_tick.py
"""
from config import db_path, tariff_period
from db.sqliteAdapter import SQLighter


def run_tariff_tick(database=None, period=tariff_period):
    """Renew who is on the last hour, then count everyone down.

    Returns (prolonged_users, not_prolonged_users, tariffs) for the
    messages balance_watcher sends. Both lists are read before the update.
    """
    db = SQLighter(db_path if database is None else database)
    try:
        prolonged_users = db.get_users_who_can_be_prolonged()
        not_prolonged_users = db.get_users_who_cannot_be_prolonged()
        # rowcount не сверяем со списком: если пользователя нет, число не совпадёт
        db.prolong_users(period)
        db.decrease_all_time_left()
        #  если не отключить, то можно накручивать рефералов, надо хранить
        # db.delete_payment_records_without_user()
        tariffs = db.getTariffs()
    finally:
        db.close()
    return prolonged_users, not_prolonged_users, tariffs
