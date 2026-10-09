# Agent notes

This repository is public. Do not commit secrets, tokens, private hostnames,
or production credentials. Gitignored `constants.py` / `constant_texts.py`
stay local.

Commit only what the product and its tests need. Debugging leftovers
(commented-out debug code, one-off scripts, sample payloads), agent working
files (scratch, reports, dumps, notes) and real user data (Telegram ids,
balances, payments, log lines) stay out of code, tests, docs and commit
messages. Tests use made-up ids; scratch lives outside the repo.

## Do not drop existing behavior

A refactor that replaces *how* something works must keep *what* it
guarantees, unless the task explicitly changes that guarantee.

Before deleting a dispatcher, map, queue, or “legacy” path:

1. Name the invariant it enforced (fairness, ordering, one-resource-per-user,
   timeout, idempotency).
2. Re-implement that invariant in the new path (SQLite claim, new worker
   pool, etc.).
3. Add a test that fails if the invariant is gone.
4. Mention the invariant in the PR. Silence means it was not reviewed.

Do not treat an old in-memory structure as dead weight. `user_threads` was
not “queue code to delete”; it was “one chat books one send worker.”
Moving work into `send_outbox` without that rule let one user occupy the
whole rec pool. Incoming pin-to-slot *was* removed on purpose (it stalled
other chats). Rec booking was not. Those are different policies.

If you are unsure whether an old check is still required, keep it and ask.
Do not drop it to make the new design look simpler.

This is the default for user-facing paths too: menus, live SKUs, pay
methods, admin commands, Telegram heartbeats. A new default (Relay,
Stars first) is copy and button order. It is not permission to hide
an old plan, an old pay method, or a management screen.

## Subscription storefront

`/subscription` sells Relay first (Stars). That is not permission to
remove plan management or hide Bronze/Silver.

- Keep `bs_trfs` on the main `/subscription` keyboard. The change-plan
  page lists every SKU (Bronze / Silver / Relay + disable).
- Stars, Crypto, and Robokassa list every live SKU. Relay may be first.
- Digest / D-3 / expiry nudges keep change-plan next to the Relay CTA.
- D-3 ("Relay ends in N days, $5") goes only to users who will expire:
  balance below the tariff price. The hourly tick renews the others, so
  for them it was false (`get_users_nearing_expiry`; lock:
  `python app/jobs/test_relay_remind.py`).
- Do not write a test that a live SKU or the picker is gone. The lock
  is `python app/service/payment/test_storefront.py`.
- The D-3 reminder and the daemon's "not prolonged" notice name the plan
  that ends, the user's own (`plan_ending_text` / `plan_off_text` in
  `app/service/payment/storefront.py`), not always Relay. Relay's text stays
  as it is; Bronze and Silver get neutral ones that name the plan as an
  apposition (localized plan names have a gender, they cannot replace
  "Relay" inside a sentence). Both still offer Relay first, with change-plan
  next to it. Locks: `python app/jobs/test_relay_remind.py`,
  `python app/i18n/test_relay_copy.py`.

## Tariff clock

`balance_watcher` ticks hourly through `run_tariff_tick`
(`app/jobs/tariff_tick.py`). A user whose balance covers the next period
never sits at `time_left = 0`: every tariff check reads 0 as "no tariff",
so for that hour the updater lists them as nosub, sends the "without
Relay" digest and moves their `last_guid` past the episode. Renew on the
last hour (`time_left <= 1`, the same condition in `prolong_users` and
`get_users_who_can_be_prolonged`), before the countdown. The digest
re-reads the tariff when it sends, not when it was queued.
Locks: `python app/jobs/test_tariff_tick.py`,
`python app/jobs/test_digest_outbox.py`.

## Episode delivery

Decided by file size and podcast source (`app/service/record/delivery.py`),
never by `service_name`: since the ETag updater every channel with an
`rss_link` arrives as `rss`, iTunes-listed or not.

- **iTunes-listed** (`itunes_id` set): up to 20 MB Telegram fetches the URL.
  Bigger, or refused by Telegram: download once, Bot API up to 50 MB,
  agent up to 2 GB, every other recipient reuses the file_id. Over 2 GB:
  too big with links.
- **Added by a bare RSS link**: never downloaded by us unless
  `trustRssPodcasts` is on. Up to 20 MB by URL; bigger gets the link and
  `tooBigRecordRss`. Telegram refusing the URL is "unavailable", not a
  download.
- Every `podcast_info` carries `itunes_listed`. A missing key means
  RSS-only (safe default), so a builder that drops it silently breaks
  delivery for listed podcasts.
- Downloads go through `DiskBudget` (512 MB stay free for SQLite, logs,
  backup). Do not write episode files around it.
- Too-big / unavailable notices go only to chats that did not get the audio.
- "Too big" is the size or Telegram's 413, never a failed try. A file over
  50 MB that the agent delivered to nobody (connection, event loop) goes
  back to the outbox; after `MAX_ATTEMPTS` the chats hear "unavailable".
  "Too big" is terminal and a circle cursor has already moved, so a wrong
  one loses the episode for good. Match 413 as a number, not a substring
  (a FloodWait of 4130 s). Lock: `python app/core/sender/test_record_delivery.py`.
- Enclosure, channel and iTunes URLs go through `normalize_url`, never
  `quote`: trackers embed an encoded URL (`/track/.../https%3A%2F%2F...`)
  that must reach the network unchanged. In HTML, `telegram_html.href`.
- The feed's `<channel>` is `feed_xml.channel_element(root)`, never the
  root's first child: Acast puts `<script xmlns=xhtml>` before it, and
  TED Talks Daily (10k listeners) plus ~1.4k channels parsed to no items,
  cursors `__`. Locks: `python app/service/podcast/test_feed_xml.py`,
  `python app/jobs/test_updater_not_modified.py`.
- Locks: `python app/core/sender/test_record_delivery.py`,
  `python app/service/record/test_delivery.py`, `python lib/requests/test_url.py`.

## Feed text in messages

Titles, show names, descriptions and dates from feeds (and Telegram channel
titles) are data. They reach a message, button or inline result only
through `lib/markup/telegram_html`: `plain_text` for plain fields (buttons,
audio title and performer, inline titles), `text` between our tags,
`escape` for text that is already plain, `href` for links. Our messages
are HTML; Telegram HTML knows only `&lt; &gt; &amp; &quot;`, so a pasted
entity shows as text ("educational:&nbsp; explaining" on the podcast page)
and a stray `<` rejects the message. Job payloads keep the raw feed text;
it is decoded once, where it is shown. Cards are built in
`app/service/podcast/card.py`, captions in `app/service/record/caption.py`.
Only `telegram_html` imports `lib.markup.cleaner`.
Lock: `python app/service/podcast/test_card.py` (CD gate),
`python app/service/record/test_caption.py`.

## Screen state

The saved state of a screen is gone when a button of an old message is
tapped, or the state store was restarted. `storage.get_user_state_data`
then answers `None` and the central loader hands handlers `{}`: a lost
state is `None` or missing keys, never something a handler can read. A
handler that subscripts the state asks `state_lost(state, *keys)`
(`app/routes/screen_state.py`) for the keys it uses anyway, before any
database access, and answers with `render_outdated_screen` (a page: the
screen is replaced, with a back button, before any "Loading...") or
`notify_outdated_screen` (an action: a toast), both in
`app/controller/general/notify.py`, text `screenOutdated`. Never a
KeyError/TypeError (`open_recs` left the chat on "Loading..."; `remove_sub`
failed after the unsubscription was written). Ask for keys, not truthiness:
a podcast not in the database has `id` None and is a live state; ask only
for keys the handler subscripts anyway, so a live state is never refused.
`get_user_state_data` keeps returning `None`: other callers test for it.
Locks: `python app/controller/builders/test_open_recs.py`,
`python app/controller/builders/test_screen_state.py` (CD gate; the
behaviour part runs where the bot's requirements are installed).

## Episode cursor

Which episodes the circle sends is decided by one cursor per subscription
(`user_channel_cs.last_guid` / `last_date`), not by a delivery log. The
updater moves it when it queues the circle job, before Telegram. The
outbox (done after ACK, retries, dead-enclosure notice) covers a job that
exists; it cannot bring back an episode no job was queued for. So
anything that moves a cursor without queueing a job for that chat skips
the episode for good. On purpose: the nosub digest ("reminded = seen")
and opening the episode list (the chat saw it). Never on purpose: a
paying user read as free (see Tariff clock).

- Opening page 1 of the episode list copies the channel's cursor into the
  subscription (`SQLighter.mark_sub_seen`), so the "new" mark goes out.
  Not for a chat with a paid tariff and notify on: the circle sends it the
  file and moves its cursor then. Never a cursor built from the feed (it
  reads as "behind"), never `channels.last_*`, never a `__` channel cursor.
  Until 2026-10 this never ran (the builtin `id` was passed for the chat),
  so muted subscriptions kept "new" for good.
  Lock: `python db/test_mark_sub_seen.py`.

- A 304 means "the feed is what was parsed last time", not "every payer
  got it". A manual refresh parses for one chat and stores the ETag for
  all. `paid_targets_behind` (`app/jobs/feed_health.py`): if a paid
  cursor is behind the channel, refetch without validators and parse.
  Free listeners behind do not force a download.
- At most one such refetch per feed version and channel
  (`refetch_allowed`, `bot_runtime_kv` `feed_refetch_<id>`).
  `add_sub` also writes `channels.last_*`, in its own format;
  when a full parse of the same version still leaves payers "behind"
  (early return: all current, or no items), refetching again only costs a
  download and 6 s per circle. Without the guard channels 21 and 1899
  refetched every circle.
- A cursor `__` (the feed parsed to no items when it was saved) reads as
  the channel's stored latest when that is real (as `add_sub` would set
  it): the next episode is delivered. Only when the channel's latest is
  also `__` (first parse of a fixed feed) it gets a quiet start: moved to
  the newest episode without sending or reminding, and the cursor sync
  runs even when nothing was sent (else it stays `__` and every later
  episode is "quiet": payers never get files). A real, older cursor
  catches up as usual (at most 4 episodes). A channel whose latest is
  `__` reminds nobody.
- A 304 on a channel whose latest is `__` counts every payer as behind
  (one refetch per version). An unchanged feed answers 304 every circle
  and is never parsed, so its first good parse came with the next
  episode, and the quiet start skipped exactly that episode (6 Minute
  English, ~1.3k channels after the parser fix).
- A live listener with no `user_tariff_cs` row (or NULL in it) is in
  neither list of `SQLighter.get_uccs_by_channel`: `NULL != 0` is not true,
  so they are neither "paid" nor "without a tariff". `_get_channel_to_poll`
  still picks their channels (any live `notify=1` listener), the circle then
  finds both lists empty and skips the channel: no fetch, no failure counted,
  nothing sent to them. On 2026-10-09: 653 legacy users (registered before
  `created_at`), 1116 channels. They are most of the "empty latest id" count.
  `/api/diag/feed?channel=` and `/api/diag/digest` show it. Giving them a
  list means fetching those channels: ~540 more full downloads per circle at
  6 s each, about +55 min on a circle of about an hour. Decide the cost
  before changing the lists.
- A free listener is reminded of a later episode, not of a different id
  (`nosub_users_behind` with dates): the same episode's id changes when
  the host re-renders its pubDate (`+0300` vs `GMT`) or edits a title, and
  `channels.last_*` is also written by `add_sub`.
  Unknown dates (`get_strped_datetime` answers 1970 for junk) fall back to
  ids. Lock: `python app/jobs/test_nosub_rule.py` (CD gate).
- Locks: `python app/jobs/test_feed_health.py`,
  `python app/jobs/test_quiet_start.py` (CD gate),
  `python app/jobs/test_updater_not_modified.py` (needs the bot's
  requirements).

## Updater restarts

A deploy stops the updater mid-circle. That is not a problem: the SIGTERM
handler leaves `updater_clean_stop` (`bot_runtime_kv`), the next start
processes the same channel again and sends nothing to the creator. Only a
crash (supervisor flag) or a circle cut short without SIGTERM skips that
channel and sends `#restarted` with the channel id. So `#problem
#restarted` always means something went wrong.
Lock: `python app/jobs/test_updater_resume.py`.

## Circle pace

The circle fetches a feed in full for ~550 of ~3400 channels (the rest answer
304 or have no recipients). It used to sleep 6 s after every full fetch, so
~55 of its ~58 minutes were sleeping. The invariant behind it is "do not hit
one host again and again", so the rule is per host (`app/jobs/circle_pace.py`):
a host is fetched in full at most once per 6 s, any two full fetches are 1 s
apart, a 304 or a skipped channel never waits (as before). A circle starts at
most once an hour (`circle_rest_seconds`; the rest was a flat 10 min after a
~58 min circle): a faster circle must not mean 3-4x the requests to the feed
hosts. A circle that did not finish retries after 10 min, not an hour. The
time this frees is what makes it affordable to poll more channels.
Locks: `python app/jobs/test_circle_pace.py` (CD gate),
`python app/jobs/test_updater_circle.py` (the real loop, needs the bot's
requirements).

## Send workers (current contract)

Configured in `threads_config`:

| Pool | Role |
|------|------|
| `send` | Incoming Telegram handlers (buttons, menus) |
| `rec` | User-tapped episode downloads |
| `circle` | Automatic RSS fanout |
| `update` | Manual / scheduled feed refresh |

Rules:

- **One user, one in-flight job per pool.** `claim()` must not lease a
  second `rec` (or `circle` / `update`) row for a `user_id` that already
  has a leased row of that action. Extra clicks wait. Other users may use
  idle workers.
- **`rec` and `circle` are separate pools.** Circle must not take rec
  slots. Do not “fix” latency by parking a spare rec worker or merging
  the pools.
- **Same episode:** `pending`/`leased` for that chat+episode is reused;
  `done`/`failed` may enqueue again.
- **Incoming `send` workers** share one queue. Serialize a chat with
  `UserGate`. Do not pin a chat to one incoming slot (that is the
  `/usersCount` stall). This does **not** apply to rec/circle/update.
- Hung HTTP on a rec worker must fail fast (timeouts, no long urllib3
  retry storms). A dead CDN must not hold a lease indefinitely.
- **Stuck worker.** Heartbeat renews every in-flight lease while the
  process lives, so a call that never returns used to hold its row, its
  user's place in the pool and its slot until a restart (MAX_ATTEMPTS
  never counted). A job with no progress (claim or `touch()`) for
  `STALL_SECONDS` (30 min) is released (`release_stalled`): the lease
  expires, the row is retried, the slot gets a fresh thread. Long work
  must touch: download/upload progress does, each chat of a fanout, and
  the manual refresh per feed. Locks: `python db/test_send_outbox.py`,
  `python app/core/balancers/test_record_balancer.py`,
  `python app/core/sender/test_record_delivery.py`.
- **Claim order.** Clicks newest first (the person is waiting now).
  Circle oldest first: one row per episode, one in flight per channel, so
  a catch-up arrives in order and an old row is never passed forever.
- **A stalled download resumes** (`Requester.download_chunked`): a quiet
  read in the middle of a file continues from the byte it stopped at
  (`Range` + `If-Range`, only on a 206 for that offset), at most 3 times, and
  a retry that brings no bytes is the last. Quiet before the first byte gets
  one more plain GET. A CDN dead for two quiet reads still fails in about a
  minute. Lock: `python lib/requests/test_download_resume.py`.
- **Dead enclosure** (timeout, DNS, Telegram could not fetch the URL) is
  terminal: do not spend `MAX_ATTEMPTS` on it. Tell the user with site +
  file links.
- **Host cooldown** (`bot_runtime_kv`, 30 min) is a separate rule. One
  timeout/DNS fault only counts (once per job, HEAD + GET is one); the
  second in another job within 10 min cools the host. One hiccup must not
  refuse a CDN's podcasts for half an hour. Cool the host the error names
  (`host='...'`), never the redirector in the URL (podtrac, pdst.fm);
  the check covers hosts a tracker link carries in its path. Locks:
  `python app/jobs/test_feed_health.py`, `python lib/net/test_enclosure.py`.
- Expected Telegram outcomes (blocked user, 429, stale edit) are WARN,
  not ERR.
- **Admin broadcasts** are `admin_mail_jobs` processed by a jobs-role
  thread. Do not dump mailings onto rec/circle/send workers. The admin
  HTTP API is a fourth supervisor role (`admin`) bound to localhost.

## Diagnostics API

`GET /api/diag/ping|audit|missed?tg=&hour=|refetches?hours=|digest?hours=|outbox?hours=|errors?hours=&q=|feed?channel=`
(`app/admin_web/diag.py`) serve the missed-episode reports for agents
without server access. Rules:

- Own token `diagToken` in `constants.py` (>= 32 chars, `Authorization:
  Bearer`). Unset or short: 404. It never opens admin endpoints, and the
  admin cookie never opens diag.
- Read-only: GET only, the DB is opened `mode=ro`. Do not add actions
  (resend, edit, mail) behind this token; those belong to the admin login.
- Who got a circle episode comes from the updater log line
  `Sending automatically ... to {...}`, never from a done `send_outbox`
  row: the sender rewrites `chat_ids` to the chats still waiting, so a
  done row lists nobody. Logs keep 3 days; past that, say "unknown".
- `refetches?hours=` counts 304 refetches per channel: more than one per
  channel without a new feed version means the refetch guard is off.
- `outbox?hours=` counts `send_outbox` rows per pool and status, and the
  open ones (pending, leased) of any age: an old pending row or an expired
  lease means a pool is not draining. Aggregates only, no chat ids.
- `errors?hours=` groups ERR / WARN of every role log by message;
  `errors?q=` lists every line containing q (an enclosure URL finds that
  job's `Exit sending <link>: delivered n/m, MB, outcome`). Numbers of 5+
  digits (chat ids) are masked in both.
- `feed?channel=` is the only call that touches the network: a GET of the
  URL stored for that channel (and of iTunes' feedUrl when it differs),
  never a URL from the request. It shows the XML the parser sees.
- Locks: `python app/admin_web/test_diag.py` (CD gate),
  `python app/admin_web/test_admin_web.py`.

## Tests

Run the smallest existing suite that covers the change (for send jobs:
`python db/test_send_outbox.py`). A refactor of claim/dispatch is
incomplete without a test for the invariant you think you preserved.
