# Agent notes

This repository is public. Do not commit secrets, tokens, private hostnames,
or production credentials. Gitignored `constants.py` / `constant_texts.py`
stay local.

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
- Do not write a test that a live SKU or the picker is gone. The lock
  is `python app/service/payment/test_storefront.py`.

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
- Enclosure, channel and iTunes URLs go through `normalize_url`, never
  `quote`: trackers embed an encoded URL (`/track/.../https%3A%2F%2F...`)
  that must reach the network unchanged. In HTML, `telegram_html.href`.
- Locks: `python app/core/sender/test_record_delivery.py`,
  `python app/service/record/test_delivery.py`, `python lib/requests/test_url.py`.

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

- A 304 means "the feed is what was parsed last time", not "every payer
  got it". A manual refresh parses for one chat and stores the ETag for
  all. `paid_targets_behind` (`app/jobs/feed_health.py`): if a paid
  cursor is behind the channel, refetch without validators and parse.
  Free listeners behind do not force a download.
- At most one such refetch per feed version and channel
  (`refetch_allowed`, `bot_runtime_kv` `feed_refetch_<id>`). The episode
  list and `add_sub` also write `channels.last_*`, in their own formats;
  when a full parse of the same version still leaves payers "behind"
  (early return: all current, or no items), refetching again only costs a
  download and 6 s per circle. Without the guard channels 21 and 1899
  refetched every circle.
- Locks: `python app/jobs/test_feed_health.py` (CD gate),
  `python app/jobs/test_updater_not_modified.py` (needs the bot's
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

`GET /api/diag/ping|audit|missed?tg=&hour=|refetches?hours=|feed?channel=` (`app/admin_web/diag.py`) serve
the missed-episode reports for agents without server access. Rules:

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
- `feed?channel=` is the only call that touches the network: a GET of the
  URL stored for that channel (and of iTunes' feedUrl when it differs),
  never a URL from the request. It shows the XML the parser sees.
- Locks: `python app/admin_web/test_diag.py` (CD gate),
  `python app/admin_web/test_admin_web.py`.

## Tests

Run the smallest existing suite that covers the change (for send jobs:
`python db/test_send_outbox.py`). A refactor of claim/dispatch is
incomplete without a test for the invariant you think you preserved.
