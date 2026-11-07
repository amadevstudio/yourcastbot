# -*- coding: utf-8 -*-
"""What a chat may do now: its running plan read once, its features from one profile.

`of(chat_id)` answers what the AI quota and the click limits used to read each
on its own (`running_plan_level`, `paid_for_days`, config's dicts by level):
no plan running is features.NONE; a plan nobody paid for (no payment, no
Patreon credit: `tariff_rows.paid_for_days`) is features.TRIAL whatever its
level; a plan paid for is its level's profile. A new kind of plan is a new
profile and the rule that picks it here, not a check in every reader.
No Telegram imports: the jobs role reads it.
Lock: python app/service/plan/test_entitlements.py
"""
from typing import NamedTuple

from app.service.plan import features
from db import tariff_rows


class Entitlements(NamedTuple):
    level: int  # the running plan's level, 0: none
    price: int  # its price, cents
    paid: bool  # money of this chat ever reached its balance, plan running or not
    profile: str  # the features' profile: features.NONE, features.TRIAL, features.level_key(level)
    features: dict

    @property
    def running(self) -> bool:
        return self.level > 0

    @property
    def trial(self) -> bool:
        return self.profile == features.TRIAL

    @property
    def ai(self) -> bool:
        return bool(self.features['ai'])

    def get(self, feature):
        return self.features[feature]


def for_plan(level, paid, price=0) -> Entitlements:
    """The entitlements of a plan of `level` (0: none) for a chat that paid or not."""
    level = int(level or 0)
    if level <= 0:
        name = features.NONE
    else:
        name = features.level_key(level) if paid else features.TRIAL
    return Entitlements(level, int(price or 0), bool(paid), name, features.profile(name))


def of(chat_id, database=None) -> Entitlements:
    level, price = tariff_rows.running_plan(chat_id, database)
    return for_plan(level, tariff_rows.paid_for_days(chat_id, database), price)
