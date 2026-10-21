# botsim: the bot without Telegram

botsim runs the real bot in one Python process and talks to it as a user
would: send `/start`, type a search, tap a button, send a file. Telegram is
replaced by a fake on both sides, so nothing reaches Telegram, and you see
what the user would see: new and edited messages with their buttons, toasts
and alerts, the Amplitude events, the warnings in the log.

What runs is the real thing: the Telethon handlers `initialize_routes`
registers (with their filters and order), the incoming dispatcher
(`TheSender._serve_locked`: user rows, middlewares, the state store), the
routes, the services and the database. Only the edges are fake.

| Edge | In production | In botsim |
|------|---------------|-----------|
| Updates in (messages, taps, files) | Telethon client | `FakeClient` collects the handlers; `dispatch()` runs them as Telethon does |
| Messages out | pyTelegramBotAPI -> `apihelper._make_request` -> Bot API | `FakeBotApi` keeps each chat (ids, text, buttons, edits, deletes) and answers like the Bot API |
| Uploads over 50 MB | Telethon agent | none (an error says so) |
| Amplitude | HTTP | recorded in the step |
| Logger | log files | collected, WARN / ERR shown in the step |
| Catalog, feeds | HTTP | HTTP, or blocked with `--offline` |
| AI summaries | OpenRouter | a canned summary and answer (`ai='fake'`), or real with `ai='real'` |
| Database | `db/yourcast.db` | a fresh one from `schema.sql`, or a copy you pass |

Needs the bot's requirements (`requirements.txt`).

## Command line

```sh
# a fresh database, offline, a scenario on the command line
python tools/botsim/cli.py --offline --lang ru -c "send /start" -c "tap меню" -c "tap Настройки"

# with the network: search, a podcast page, an episode, its summary, a question
python tools/botsim/cli.py --lang en \
  -c "send /start" -c "tap search" -c "send Darknet Diaries" -c "tap 0,0" \
  -c "tap Listen" -c "tap 0,0" -c "deliver" -c "tap Summary" -c "ai" \
  -c "tap Ask" -c "send Who is the guest?" -c "tap Done"

# a scenario file, against a copy of a real database (the copy is deleted after)
python tools/botsim/cli.py --db /path/to/snapshot.db --user 1001 scenario.txt
```

Actions, one per line in a scenario file (`#` starts a comment):

| Action | What the user does |
|--------|--------------------|
| `send TEXT` | sends a message: `/start`, a search, a question |
| `tap TEXT` | taps a button of the bot's latest message that has it (exact text first, else a part of it) |
| `tap ROW,COL` | taps a button of the bot's latest message with buttons, by position from 0 |
| `data JSON` | taps a button with this callback data (an old screen, a crafted button) |
| `file PATH [MIME]` | sends a document (an OPML file) |
| `deliver` | the episodes the taps queued, sent as the send workers would |
| `ai` | the summaries queued, made as the jobs process would |
| `screen [N]` | prints the last N messages of the chat |
| `user ID [LANG]` | acts as another user from now on |

Each action prints a step:

```
>>> tap '📝 Summary' on #1007  (0.0 s)
    handlers: action_processor(recs, sum)
  [toast] Preparing the summary: 1–2 minutes
  amplitude: recs {'original_command': 'recs', 'request_type': 'call'}
>>> run_ai  (0.0 s)
  [new #1009 text reply to #1007]
    📝 <b>Darknet Diaries – 181: Ricky</b>
    ...
    [❓ Ask about it]
```

`handlers` are the Telethon handlers that took the update, in order
(`processor(search)` is the route `search`; `opml_file (stop)` stopped the
others). A handler that raised shows as `... raised Error: text`. The exit
code is 1 when an action failed or an ERR was logged.

`deliver` sends every episode by its URL (`by_url=True`): Telegram would
fetch it, nothing is downloaded. `BotSim.deliver(by_url=False)` runs the
real size rules (a download, a Bot API upload up to 50 MB); there is no
agent for bigger files.

## Python

```python
from tools.botsim import sim

sim.boot(network=False, ai='fake')          # before anything else of the bot is imported
user = sim.BotSim(user_id=1001, lang='en')
step = user.send('/start')
assert step.handlers[-1] == 'processor(start)'
step = user.tap('menu')                     # by text, or user.tap((row, col))
print(step)                                 # or step.new, step.edited, step.toasts, step.analytics, step.errors
print(user.screen(3))
sim.shutdown()
```

`boot()` once per process: the bot reads `config.db_path` and `work_dir` at
import time. It points `work_dir` (feed copies, downloads) at a scratch
directory, so a run leaves nothing in the checkout.

Tests: `python tools/botsim/test_botsim.py` walks a new user (/start, the
welcome plan, menu, settings, the storefront, an OPML file, a summary and a
question). Where the requirements are not installed (CI) it is skipped.

## Data

- A fresh database is `schema.sql`: the production schema, structure only,
  and the plans (their prices are what the bot shows anyway). Refresh it
  from `sqlite3 -readonly <db> .schema` when the schema changes.
- `--db` takes a copy of a real database. The bot writes to it (new users,
  subscriptions, states), so the CLI works on a temporary copy unless
  `--in-place`. A real database holds user data: keep copies outside the
  repository and delete them after.
- Test users are made-up ids (1001, 999000111). Acting as a real id on a
  copy is possible; nothing is sent to that person.

## What it does not show

- How Telegram renders a message (HTML, rich messages, a time in a reply
  that plays the audio from there).
- Real uploads, Stars payments (only the pre-checkout and payment handlers
  can be called with crafted updates), inline mode.
- Load, concurrency, the send pools and their claim order (their tests are
  in `db/test_send_outbox.py` and `app/core/balancers/`).

For those, a real Telegram: your account against the bot, or a test bot on
Telegram's test environment.

## Similar tools

Bots on one library can usually mock that library: aiogram's own tests use
a mocked bot, python-telegram-bot had `ptbtest`, and `tgintegration` drives
a bot from a real user account (Pyrogram). This bot listens with Telethon
and answers with pyTelegramBotAPI, so none of them covers both sides:
botsim fakes Telethon's events and the Bot API's responses.
