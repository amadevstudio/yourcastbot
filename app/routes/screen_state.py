# -*- coding: utf-8 -*-
"""What a handler may assume about the saved state of its screen.

The state is gone when a button of an old message is tapped, or the state
store was restarted. storage.get_user_state_data then answers None, and the
central loader (app/routes/state_data.py) hands handlers `{}`: so a lost
state shows up as None or as missing keys, never as an error the handler can
read. A handler asks state_lost() for the keys it subscripts anyway, and
answers with notify_outdated_screen (app/controller/general/notify.py)
instead of a KeyError or an AttributeError.
No imports: the CD gate runs it without the bot's requirements.
"""


def state_lost(state, *required_keys) -> bool:
    """The state is missing or empty, or lacks a key the handler needs.

    Key presence, not truthiness: a state may hold None for a key (a podcast
    that is not in the database has id None) and still be a live state.
    """
    return not state or any(key not in state for key in required_keys)
