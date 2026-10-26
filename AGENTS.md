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

## Episode text

A caption holds 1024 characters, and the bot owner's Telegram Premium does
not raise that for bots (Bot API 10.3 checked: Premium only allows custom
emoji). The description used to be cut to ~1000. Now (`app/service/record/text_format.py`,
`users.episode_format`):

- **brief** (default since 2026-10-22, NULL in the column; the owner's call:
  the text under an episode is the summary, the feed's text on request, at no
  new AI cost): the audio with its header only, and under it "Summary" (AI
  on) and "Show notes" (`DESCRIPTION_ACTION` `desc`, the episode's ref). The
  sender keeps every delivered episode with its description
  (`ai_episodes.descr`, `ai.remember_episode`, AI on or off);
  `episodeTextModule.show_description` sends it as a collapsible quote
  replying to the audio, or a toast when there is none. A format chosen in
  Settings stays (16 users on 2026-10-22). Locks:
  `python app/core/sender/test_record_delivery.py`, `python tools/botsim/test_botsim.py`.
- **rich** (the default before 2026-10-22): one `sendRichMessage` with the
  player and the whole description (`lib/telegram/rich_message.py`, up to
  32768 characters; pyTelegramBotAPI 4.11 has no such method, it goes
  through `apihelper._make_request`). The first one a user gets is followed
  once by a note on how to switch (`users.flags` JSON key `rich_hint_sent`: one-off per-user marks and small choices are keys there, not columns; button
  `episodeFormatSeparate`).
  The description keeps its http(s) links (`telegram_html.protect_links` /
  `restore_links`); other schemes and empty anchors are text. Past 32000
  characters the links go and the text stays. Separate/caption/meta show plain
  text. Lock: `python lib/telegram/test_rich_message.py`.
- **separate** (Settings, or the note's button): the audio with a header-only
  caption, then the description in `<blockquote expandable>` (one message,
  under 4096, no link preview: a link in it is not a card under the episode).
- **caption** (Settings): the old way, the description cut to the caption.
- **meta** (Settings): the header only, no description, as in channels.
- Channels and chats with `description_mode` none are not users here: no
  format lookup, the caption as before. `/settings` is a list of sections (Episode text;
  Reminders, without a plan only), each a page of its own (`settsText`,
  `settsRem`) and each button names what is set; the episode text page has
  five buttons (one per format, brief first, the current marked). The note after the first
  rich message has its own action (`episodeFormatHint`) because it also closes
  the note. Lock: `python app/controller/builders/test_settings_screens.py`.
- A rich message that fails for a reason of its own (not a blocked user, not
  a flood, not a refused file) falls back to separate for that chat and
  counts toward a 10-minute pause of rich messages (`rich_message.available`):
  the text is never lost and a broken method is not hammered.
- Over 50 MB the agent uploads a plain audio: header caption, description
  after it as in separate; chats that reuse the cached `file_id` get the rich
  message. A refused URL is a refused file (download, then rich upload), never
  a reason for the old caption.
- Locks: `python lib/telegram/test_rich_message.py`,
  `python db/test_episode_format.py`, `python app/core/sender/test_record_delivery.py`.

## Subscription storefront

`/subscription` sells Relay first (Stars). That is not permission to
remove plan management or hide Bronze/Silver.

- `/subscription` asks how to pay first (the owner's call, 2026-10-22):
  "Subscription" (`bs_recur`: every plan by a Stars subscription, Relay
  first, then Patreon) and "One-time payment" (`bs_once`: Stars, CryptoBot,
  Robokassa for the creator, Relay's longest prepaid bundle), then
  change-plan. Every pay method stays one level down; none is dropped.
  Lock: `python app/service/payment/test_storefront.py`.
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
- Under the D-3 text (Relay's verbatim, first) goes what the plan brought
  (`relay_remind.recap_text`): episodes delivered and summaries received in
  the last 30 days, podcasts on auto-delivery now. Nothing delivered and no
  summary: no recap. The ledger started on 2026-10-21: the episode count
  shows only when it covers the 30 days or the user's whole time (joined
  after it began), else a two-week trial read "1 episode". It never fails
  the reminder.
  Lock: `python app/jobs/test_relay_remind.py`.

## Referrals, paywall, prepaid months, win-back

- A payment awards the inviter once per invitee, whatever the pay method
  (Stars, the CryptoBot and Robokassa webhooks): `award_referrer_for_payment`
  takes `users.ref_id` off the invitee (`claim_referrer`, one transaction)
  before `giveAward('replenished')`. Never award before the claim: a crash in
  between loses one bonus, never doubles it. A `/start` link names an
  existing user other than oneself, or nobody (`user_exists_tg`):
  `get_user_by_tg` creates a row for any number. An invitee's welcome plan is
  `tariff_ref_invitee_period` longer. A user with podcasts and no plan who
  sends /start is "returning" and gets the 2-day plan, unless the row is
  under a day old (`paymentSafeModule._joined_recently`): a first command
  from the bot's menu (/search) creates the user with no plan, and a
  newcomer who subscribed before /start got 2 days instead of 14. "Invite a friend" (`referral.invite_row`,
  the share sheet with the user's own link) goes in D-3, plan-off and after a
  Stars payment, below Stars and change-plan.
  Lock: `python app/service/payment/test_referral_award.py`.
- A Stars invoice names its plan (payload `v`). With no plan running the
  payment switches to that plan and turns it on when the balance covers
  one period at the price the invoice sold it for (`b / m` of the payload,
  `planPrice`; today's price if lower): an invoice sent before a price rise
  and paid after it still turns its plan on
  (`applyPaymentReplenishmentOnce(planId=..., planPrice=...)`): before, a free user who paid
  for Relay got a balance and "choose a plan", and an ended Bronze paid for
  Relay renewed Bronze. A running plan is only topped up, as before (a
  mid-period change has a price difference: the change-plan page). "No
  plan running" includes a row with no plan and days on it (tariff 0 with
  `time_left`, 67 rows from before on 2026-10-26): a free user there paid
  for Bronze, got "money came" and stayed free with the money on the
  balance. An invoice without `v` (sent before) is the old top-up.
- The free limits (the 16th podcast, the manual update, the channel page)
  carry `relay_nudge_markup(invoice=True)`: Relay's invoice in one tap
  (`bs_stars_pay` without `v` bills the showcase plan) and change-plan.
  The channel page of a running Bronze or Silver keeps the Stars page there
  (an invoice would only top up the running plan).
  D-3, plan-off and the digest keep the Stars page of every plan.
  Locks: `python app/service/payment/test_paywall.py` (bot requirements),
  `python app/service/payment/test_storefront.py`.
- Prepaid months and offers (`app/service/payment/offers.py`) credit the full
  price and charge the discounted one; the tick renews month by month from
  the balance, so nothing else knows about them. The Stars payload carries
  `m` / `d` / `o`; the pre-checkout accepts only `offer_discount(m, o)` and,
  for an offer, `offer_open`. `process_successful_payment` checks the payment
  matches its invoice and nothing else: money Telegram took is credited as
  sold. A plain top-up keeps `m` / `d` / `o` out of the payload. Months are
  sold to a Relay plan or to a user with no plan running
  (`prepaid_months_sold`), never to a running Bronze or Silver (the balance
  would renew that plan for years). The longest bundle is also a button on
  the one-time payment page (`bs_once`), after the pay methods.
  Lock: `python app/service/payment/test_stars_invoice.py` (bot requirements).
- A plan by a Stars subscription (`app/service/payment/stars_subscription.py`,
  action `bs_stars_sub`, the plan in `v`, else the user's own, else Relay): an invoice link (`createInvoiceLink` with
  `subscription_period`, the raw request; `sendInvoice` has no
  subscriptions) that Telegram charges every 30 days. Payload `u: 1`, one
  month of that plan at its price, no discount. Every charge, the first and each renewal,
  arrives as a payment of that payload with its own charge id
  (`MessageActionPaymentSentMe` `recurring_init` / `recurring_used`) and is
  credited once like any Stars payment: the tick renews the plan from the
  balance. A plan the first charge turns on runs `GRACE_HOURS` past the next
  charge, so the renewal lands before the tick could end it.
  `users.flags` `stars_sub_until` (and the first charge id, the plan and the
  cents a charge credits): while it runs, no second subscription (the page
  shows the next charge instead; refused at the pre-checkout too: Telegram
  would charge both), and no D-3 when its charge pays for the plan that ends
  at today's price (`covers`; another plan or a raised price gets the D-3).
  Sold when no plan runs or that same plan runs (another running plan would
  renew itself from the charges: a toast says to switch first). The
  change-plan page switching a subscriber to another plan (or off) cancels the
  subscription (`editUserStarSubscription`, raw request; its paid period runs
  out, the flags go) and offers one for the new plan: Bronze's $1 charges
  would leave Relay unpaid, Relay's $5 would overpay Bronze. A cancel
  Telegram refuses keeps the flags and tells the user to cancel in Settings.
  Offered on the subscription page, and in D-3 and plan-off for the user's own
  plan, below the rows that were there. A cancel by the user is not reported
  (no such update in Telethon): no charge comes and the plan ends at the
  tick. Locks: `python app/service/payment/test_stars_invoice.py`,
  `python app/jobs/test_relay_remind.py`.
- Win-back (`app/jobs/winback.py`, `db/winback.py`): a schedule starts only
  from the tick's plan-off list, for Relay (`start_winback`); the old
  expiries (15.5k on 2026-10-20) are never mailed. Messages at
  `winback_after_days`, each claimed before it is sent (at most once); a
  flood wait gives it back for the next hour; the user is re-read when it
  goes (back on a plan or gone ends the schedule). The first month at
  `winback_offer_discount` % off is open once the offer was sent and until
  `users.flags.winback_offer_used`, set in the payment's own transaction
  (`applyPaymentReplenishmentOnce(userFlag=...)`).
  Lock: `python app/jobs/test_winback.py`.
- Patreon (`patreonPaymentModule`): the bot cannot tell whose email it is
  told, so one membership pays one account. An email another account has is
  not saved (`savePaymentServiceEmail` answers False, text `email_taken`;
  case and spaces do not matter), and accounts that already share one are
  credited once a month between them (`one_row_per_email`: the monthly check
  is the email's, not the account's). The creator's debug address
  (`creator_email`, 100 cents) credits the creator's account only.
  The email is not verified, on purpose for now (the owner's call,
  2026-10-23: few patrons, small sums): the first account to save an
  address holds it. A Patreon login (OAuth) is the fix if Patreon grows.
  A month's credit is a payment (`db/patreon.py` `credit_month`): the
  balance, a `payment_history` row (`patreon`, invoice id the month,
  `2026-10`, the pledge's cents; a pledge of nothing is `credited`, not
  `paid`) and `last_replenishment` in one transaction, and a `payment`
  event. Before, Patreon wrote no row: revenue, payers and "ever paid" never
  saw a patron. Credits before that are `last_replenishment` only, so "paid
  for" is `tariff_rows.paid_for_days` (a payment or a Patreon credit).
  Lock: `python app/service/payment/test_patreon_credit.py` (CD gate).
- CryptoBot and Robokassa webhooks (`scripts/payment/cryptoBot.py`,
  `subscription_income.py`) credit through `credit.credit_once`
  (`applyPaymentReplenishmentOnce`, as Stars): the invoice is checked and
  written in the transaction that credits it, so a retried, concurrent or
  replayed webhook (CryptoBot delivers "at least one time"; a Robokassa
  signature never changes for its invoice) credits nothing and is still
  answered OK. An unsigned Robokassa
  request reaches the creator only: it names any uid, never write to it or
  make its users row. Lock: `python scripts/payment/test_webhook_credit.py`
  (the scripts run whole, Telethon stubbed; bot requirements).
- Moving to a cheaper plan (the change-plan page) gives back half of the
  days left, only to a chat that ever paid (`tariff_rows.paid_for_days`: a
  payment, or a Patreon replenishment): the welcome trial's or referral days
  never become balance. Lock: `python tools/botsim/test_botsim.py`,
  `python db/test_tariff_rows.py`.

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
- **Added by a bare RSS link** (or an OPML import the catalog did not
  match): downloaded like a listed one since 2026-10-22 (`trustRssPodcasts`,
  default on). With it off: up to 20 MB by URL; bigger gets the link and
  `tooBigRecordRss`; Telegram refusing the URL is "unavailable".
- **Public addresses only.** Every fetch of a URL a feed named (the feed,
  the episode file, its HEAD, a transcript, a cover) goes through
  `lib/net/public_only.py` (`Requester`'s adapter, `public_only.session()`):
  a connection to a non-global address (local services, a cloud's metadata
  endpoint) is refused on the connected socket,
  redirects and names that resolve locally included. Anyone can publish a
  feed, listed or not. Do not fetch a feed's URL with bare `requests`.
  Tests serving from 127.0.0.1 call `public_only.allow_private(True)`.
  Lock: `python lib/net/test_public_only.py` (CD gate).
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
A podcast page holds 4096 characters: the description is cut to
`card.CARD_TEXT_LIMIT` after a sentence (Persian show 1886700489 sent 4061
characters, most of them blank lines and dots: `MESSAGE_TOO_LONG`, no page).
Lock: `python app/service/podcast/test_card.py` (CD gate),
`python app/service/record/test_caption.py`.

## Podcast catalog

Search, the podcast page, subscribing and feed recovery ask
`app/service/podcast/catalog.py`, never Apple's URLs directly: Apple's
directory with the Podcast Index beside it (its Apple-format `search` and
`lookup`, no key). The Index lists podcasts by their Apple id, so
`itunes_id` and "iTunes-listed" delivery mean what they did.

- Search asks both at once: Apple's results first, in Apple's order, then
  the Index's others. Either answering is enough; a slow Index is waited
  for 2 s once Apple answered.
- Lookup is Apple's; the Index only when Apple fails or has no feed for the
  id. The Index's feedUrl can be an older address of the show (feedburner
  for TED Talks Daily): subscribing through it keeps the channel's stored
  `rss_link` (`add_sub` writes it), and feed recovery still validates the
  stored URL first, then Apple's, then the Index's.
Lock: `python app/service/podcast/test_catalog.py` (CD gate; the page and
subscribe parts run where the bot's requirements are installed),
`python db/test_feed_recovery.py`.

## OPML import

An OPML file (subscriptions exported from another app) sent to the bot in a
private chat, in any state, is read before the routes (`initialize_routes`
`opml_file`, `.opml`, or `.xml` typed as XML; at most 2 MB; it stops the
other handlers, a document never reaches search as an empty text). The
import runs in a thread of its own, one per chat (`opmlModule`), with a
status line and a result naming what was added, had, failed and is over
the free limit (Relay's invoice and change-plan, as at the limit on the
podcast page). A feed is matched (`app/service/podcast/opml.py`): a channel
we poll with that address, else the catalog result with the same feed, else
the one result with exactly that name when the two feeds share an episode
or the file's address is gone (apps keep old addresses: megaphone for
Darknet Diaries, radio-t.com for a feedburner feed), else the feed as RSS.
A wrong "else RSS" makes a duplicate RSS-only channel (no download over
20 MB), so keep the iTunes match. The file is user data: no DTD, at most
100 feeds. Lock: `python app/service/podcast/test_opml.py` (CD gate; the
message part runs where the bot's requirements are installed).

## Podcast page speed

The podcast page, the episode list and a click on an episode each read the
feed. They used to download it every tap: 12 s for a 66 MB feed of 10k
episodes, ~2 s for a slow host.

- `feed_cache` (`app/service/podcast/feed_cache.py`): those three paths pass
  `cached=True` (`podcast_info_query` -> `rss.get_rss_root_with_status`).
  A copy checked in the last 5 minutes is read from disk; an older one is
  asked for with its ETag (304: read from disk; changed: that one download
  replaces it). Any uncached full fetch of the feed (the updater found a new
  version, a manual refresh, feed recovery) drops the copy, so a new episode
  is never hidden behind it. The updater and recovery never read the copy.
  At most 300 MB, least recently used first, and only while the disk keeps
  512 MB + room for episode downloads.
- A cover Telegram refuses (`failed to get HTTP URL content`, cdn.mave.digital
  15 times on 2026-10-21) is marked in `telegram_cache` for 7 days
  (`app/service/podcast/cover.py`): the page goes at once as one text
  message with its buttons. The refusal and, while marked, an open start a
  background check at most once an hour (send to the storage chat): by URL,
  and when Telegram still refuses the URL, as a file we download (an image,
  at most 5 MB: the mave cover is a 208 KB JPEG our server gets at once).
  Through, its file_id is cached and the mark goes. A page without its picture is a text
  message. The page's own buttons (subscribe, notify, rate) refresh its keyboard
  only (`keyboard_editor`), never the media: Telegram's `editMessageMedia` turns
  a text message into a photo, so once the check cached the cover the next tap
  replaced the page's text with a captionless cover (2026-10-26), and the
  screen, stored as text, answered "no text in the message to edit" to every
  later button. Such a screen is now sent again (`message_has_no_text`).
Locks: `python app/service/podcast/test_feed_cache.py`,
`python app/service/podcast/test_cover.py` (CD gates; the rss, page and
editor parts run where the bot's requirements are installed).

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

## Back

A stored screen stack outlives the code: about a third of them (3.9k of 11.7k,
Oct 2026) hold names from the bot before its rewrite (`pc`, `srch`, `welc`),
and `empty` is a route with no screen. "Back" to a name that is not a screen
(`goBackModule.is_screen`) opens the main menu on a clean stack, as a command
does; it was a `KeyError` or `'NoneType' has no attribute 'get'` with no answer.
Lock: `python app/core/navigation/test_go_back.py`.

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
- Every live listener is paid or free. A user with no `user_tariff_cs` row
  (or NULL in it) used to be in neither list of `SQLighter.get_uccs_by_channel`
  (`NULL != 0` is not true): their channels were polled and skipped, the feed
  never fetched, nothing sent (653 legacy users and 1116 channels on
  2026-10-09, most of the "empty latest id" count). Now the free list is the
  exact NULL-safe complement of the paid one, and the supervisor gives every
  user without a row the "no tariff" row at start (`db/tariff_rows.py`:
  tariff_id 0, no balance, no days, as the product writes it when a plan is
  switched off). These users are free: they are polled with their channels
  and get the weekly digest (one per user, mute button). Polling those
  channels is paid for by Circle pace. `/api/diag/feed?channel=` and
  `/api/diag/digest` show a user with no usable tariff row again (it reads 0
  after a restart; "in neither list" must stay 0).
  Lock: `python db/test_tariff_rows.py` (CD gate).
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

## Feed recovery and digest episodes

Feed errors pause a feed, never `user_channel_cs.notify`. `feed_recovery`
stores coalesced repair jobs, leases, daily retries and pause notices. A
404/410 queues a check immediately; other repeated failures queue at the
existing threshold. Manual refresh failures also queue a check. The jobs
role validates the stored URL first; only when it fails does it ask iTunes
(exact collection id) and validate the returned RSS. A feed that answers
keeps its address: a check of a healthy show must not move it to the
catalog's URL (other guids/dates there break every cursor). RSS-only feeds
are only rechecked. A `www.` address the host refuses while the same one
without `www.` answers (`podcast_info_query` retries so; Europe 1 answered
403 every hour for 11 feeds) is stored without it by the circle: it is the
feed that was parsed, and the next circle asks that address first
(`podcastsUpdater._answered_feed_url`; lock:
`python app/jobs/test_updater_not_modified.py`). Manual refreshes queue a check at most every five
minutes.

The stored URL answering again ends the failure cooldown and keeps the
validators. A new URL also clears the validators and the refetch guard.
Neither changes channel/subscription cursors or delivery queues:
the normal circle catches up, with its existing quiet-start/order/limit
rules. Leases fence stale workers; a concurrent URL edit wins over repair.
Old failure markers seed repair jobs without changing old `notify=0`
preferences or sending historical notices. Pause notices go to paid
listeners with notify on, as before the pause (free ones have the digest),
one per feed, and not again for a week if the feed flaps
(`NOTICE_REPEAT_SECONDS`). Repair jobs, the bookmark of the latest episode
and digest flags are side tasks of the circle: a failure there is a WARN,
never a lost delivery. There is no status screen or "check feed" button
on purpose: recovery is automatic, the notice says so.
Locks: `python db/test_feed_recovery.py`, `python db/test_channel_poll.py`,
`python app/jobs/test_updater_not_modified.py` (real loop, bot requirements).

`db/listening.py` stores text/callback references, not audio. The digest
holds the latest episode per show, up to five shows per message, keeping
Relay/change-plan/mute controls and rechecking tariff/notify at send time.
ACK deletes only the revision shown. An episode someone already has a
summary of shows its first line (`ai.gist`, by channel and title, the
episode's own language first): nothing new is made for a digest.
"Listen" is the ordinary rec button
and searches by hash from the start (positions change); three to a row. Snapshots nothing
refers to expire after 90 days; a hard user delete takes the user's queued
digest episodes. A "listen later" list was tried and left out (it halved
episode titles in the list for little use). Locks:
`python db/test_listening.py`, `python app/jobs/test_digest_episodes.py`.

RSS failures and Python/library exceptions go to dated `rss`/`runtime_*`
logs, visible through the existing read-only diagnostics. `/api/diag/outbox`
also reports recovery queue aggregates; no new write endpoint or token.
Locks: `python lib/tools/test_runtime_logging.py`,
`python app/admin_web/test_diag.py`.

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

## Amplitude

Taps reach Amplitude from the bot role (`analytics_serving`, one event per
route; the user is `users.id`). The event is the route, so a button inside it
(`nrec`, `desc`, `sum`, `wSub`...) is the event property `action`: without
it "Listen", "Show notes" and "Summary" were all `recs`. What the bot does on its own goes through
`app/service/analytics_events.track` (any role; the payment scripts pass
`sync=True`): `digest_sent {episodes}`, `plan_off {level, paid_before}`
(the tick did not renew it; `paid_before` false is a trial that did not
convert), `payment {method, amount_cents, ...}` (Stars, CryptoBot),
`summary_ready {cached, seconds}`, `episode_delivered {mode, format}` (one per
user chat that got the audio, from the sender: most listeners never tap, so
without it Amplitude counted them as gone). These carry the running plan's
level as the user property `plan` (0: none). A digest's Listen button carries
`"s": "d"` (compact JSON, within 64 bytes), so its tap has
`source: digest`. A link `t.me/<bot>?start=src_<name>` (a launch post:
`src_ph`, `src_x`) is a bare /start (the welcome screen), never an action; a
user it signs up keeps it (`users.flags` `source`, the first link only), and
`new_user` carries `link_source`, also as the user property (lock:
`python app/controller/builders/test_onboarding.py`,
`python app/service/payment/test_referral_award.py`). Tracking never fails the caller and never creates a
user row (it reads `users`, not `get_user_by_tg`). Nor does it slow one: events go
through a queue that drops when full (`DroppingQueue`, 10k) to one thread
that survives a bad event, each request has a timeout, and the sender only
queues `episode_delivered` (its user lookups run on that thread). A tap is
answered before its event is made.
Lock: `python app/service/test_analytics_events.py` (CD gate),
`python app/jobs/test_digest_episodes.py`.

## Usage ledger and economics

`usage_events` (`db/usage.py`) is one row per chat per delivered episode
(`rec`: a click, `circle`: automatic, by the outbox action), with the MB we
downloaded for it (shared by the chats it served, 0 when Telegram fetched
the URL), and one row per AI summary with what the APIs charged. The
sender writes it after the delivery (`Sender._record_usage`); it never fails
a send. The free weekly limit and the admin page "Economics"
(`app/admin_web/economics.py`, `GET /api/economics?days=`) read it.
Revenue comes from `payment_history` (the creator's own test payments are
not revenue); the server bill (`config.server_usd_month`) is spread over
chats by load. A channel's deliveries count for the user who added it.
Locks: `python db/test_usage.py`, `python app/admin_web/test_economics.py`
(CD gate), `python app/core/sender/test_record_delivery.py`.

The page "Product" (`app/admin_web/product.py`, `GET /api/product?days=`)
is the newcomers' funnel and the product's use from the database: who
subscribed to a show of their own (the welcome show every newcomer gets
does not count), got an episode, asked for a summary, paid, blocked the
bot; plans now (a trial ending in 3 days without the balance to renew);
payments (first-time payers); summaries, questions, auto opt-ins; the
digest; newcomers by week; the share of newcomers whose first 30 days are
over who paid in them (`paid_first_days`, all and those with a show of
their own): a fixed window, so moving the trial's start cannot inflate it. Read-only, the creator's tests are not payments,
blocked users hold no plan. Taps and the digest's clicks are Amplitude's.
Lock: `python app/admin_web/test_product.py` (CD gate).

## Welcome screen

`/start` is a new message (`resending` for a command): a newcomer's welcome
plan, sent just before it, used to be edited into the screen and never read.
It shows the top podcasts in the user's language (then worldwide) as
checkboxes, and a tap on one subscribes to it; a second tap unsubscribes
(`app/controller/builders/onboarding.py`, actions `wPick` / `wSub`,
state independent: the welcome message stays in the chat). It used to tick
only, with a button that subscribed to the ticked ones: people ticked and
left (26 ticks, 2 subscribe taps in two days, October 2026). "Done" (`wSub`)
now only names what is subscribed. A tick is the chat's subscription, read
on each tap. The list must not move when one is ticked, so each button holds
the chat's newest subscription row when the screen was drawn (`u`): rows up
to it stay out of the list (/start again offers new podcasts), later ones are
ticks. A checksum of the list rides along: a changed list is redrawn, never
subscribed to. A button drawn before (a bitmask `m`, no `u`) holds ticks
that were never subscribed: its subscribe button still subscribes them, its
tick redraws the new screen. Search and "skip to menu" stay on the screen. Subscribing keeps the free
subscription limit. The new user's TED Talks Daily subscription
(`referral_processing`) is unchanged: the digest audience comes from it.
A link from Apple Podcasts typed into search opens that podcast.
Lock: `python app/controller/builders/test_onboarding.py` (the behaviour
runs where the bot's requirements are installed).

## First episode after subscribing

A subscription from the podcast page or the welcome screen queues the show's
newest episode at once (`recsModule.send_latest_episode`, off the tap's
thread): a newcomer used to wait days for a new episode and saw nothing come.
It is a click on that episode (the `rec` pool, one at a time per chat, the
free limit counts it); the subscription's cursor already points at it, so
the circle does not send it again. Quiet when it cannot go: a feed that
fails, the free limit, `LATEST_OPEN_LIMIT` (3) clicks already waiting
(eight ticks are not eight files). Never fails the subscription. Not for an
OPML import (up to 100 shows) or the TED Talks Daily subscription /start
makes on its own. A click on an episode is unchanged.
Lock: `python app/controller/builders/test_latest_episode.py`.

## Free weekly episodes

A listener without a running plan gets `free_rec_per_week` (10) episodes
by click in any 7 days (`app/service/record/free_limit.py`), counted from
the usage ledger (`rec`) plus their clicks still waiting in the outbox
(fast taps must not slip past). The same episode again is free. Any
running plan, the welcome trial included, has no limit, whatever its
`notify_count` (clicks are not notifies). Automatic deliveries, manual
refresh, the episode list and the digest text are not limited; the
digest's "Listen" is a click like any other. At the limit the click is
not queued: the message lists every plan with its Stars price, Relay
first, plus the page of plans (Storefront rules: no SKU hidden).
Lock: `python app/service/record/test_free_limit.py` (CD gate; the message
part runs where the bot's requirements are installed).

## AI summaries

Off until `constants.py` has `openrouterApiKey`, `openrouterModel` and
`openrouterTranscribeModel` (OpenRouter ids; no model is built in): no
button, no worker (`summary.enabled`). One key for everything:
OpenRouter's chat completions for the summary and its
`/audio/transcriptions` for speech to text, plain HTTP, no vendor SDK.

`app/service/ai/`: `openrouter.py` is the only code that talks to
OpenRouter (key, errors, billed cost); `transcript.py` the feed's
`<podcast:transcript>` (free) or Whisper on 10-minute ffmpeg pieces
(downloaded through DiskBudget; ffmpeg streams, pydub would hold the
episode in memory on a 2 GB server); `summary.py` the model call and the
button; `quota.py` who may ask. The plan level is
`db/tariff_rows.running_plan_level`, shared with the free episode limit.

- The sender remembers the episode (`db/ai.py`, ref = `usage.episode_ref`
  of the enclosure, with its feed length) and puts "Summary" under the
  file in user chats only: a channel's readers are not the bot's users.
  The buttons come from one place (`Sender.episode_buttons`) for the Bot
  API and for the agent's uploads over 50 MB alike.
- The summary is in the episode's language unless the user picked their
  Telegram language (/settings, AI summaries; `users.flags`
  `summary_language`); that language is the cache key with the episode.
  Notices go in the user's interface language (`users.lang`).
- A summary is made once per episode and language (the Telegram client's
  code) and is then free for anyone. A new one takes the episode's length
  from the asker's plan quota, hours of audio per 30 days
  (`config.ai_summary_hours_per_month` by level), never a count:
  transcription bills by the second, so a count lets long episodes cost
  more than the plan brings. The length is the feed's `itunes:duration`
  (an hour when there is none) when asked, what Whisper measured once
  transcribed, and 0 when someone else's summary served the request;
  requests on their way count, failed ones do not (`ai_requests.seconds`).
  A plan nobody paid for yet (the welcome Relay, referral days; not
  `tariff_rows.paid_for_days`: no `paid` row in `payment_history`, no
  Patreon credit) has `config.ai_summary_trial_hours` (5) whatever
  its level: 153 of 155 running plans were unpaid on 2026-10-21. The first
  payment opens the plan's own hours.
  No plan: every plan's invoice, as at the free episode limit. A running
  plan (a trial too) over quota: the Stars page and change-plan, never an
  invoice (it would only top the running plan up). The top plan, paid: only
  what is left.
- The jobs process drains `ai_requests` one at a time (`app/jobs/ai_watcher.py`),
  a lease of 30 minutes, two attempts, then "could not". What a new summary
  cost goes to the usage ledger for the chat that asked.
- The transcript is data: the prompt says so; never follow it.
- A tap on Summary gets a status line at once (a reply to the audio,
  `ai_requests.status_message`); the worker edits it as it goes
  (downloading, transcribing part n of m, writing) and into the summary or
  "could not" (`ai_watcher.status_updater` / `deliver`). A question gets
  "Thinking…", edited into the answer. A line that cannot be edited: a new
  message, as before. message_master's results carry the sent id as `id`.
- Thinking is off in every model call (`summary.REASONING`): on 2026-10-22
  Haiku's provider started thinking by default, all 800 tokens of an answer
  went to it ("could not answer") and a summary was cut mid-sentence and
  cached. A summary cut at `max_tokens` is a failure, never cached; an
  answer cut there is shown up to its last sentence, and at most
  `ANSWER_MAX_CHARS` (one message).
- Transcripts carry time marks, `[12:40]`, at most every 30 s (Whisper's
  segments with each piece's offset, VTT/SRT cues, JSON `startTime`; plain
  text and HTML have none). The summary starts its points with those times
  ("12:40 – ..."), never invented ones, and is a reply to the episode's
  audio (`ai_requests.reply_to`, the message the button was on;
  `message_master` `reply_to`, sent anyway if the audio is gone): Telegram
  makes a time in a reply to the media play it from there. Transcripts made
  before have no marks, and their summaries no times. A transcript past
  `MAX_TRANSCRIPT_CHARS` (~100k tokens, 8+ hours of speech) is cut.
- "Ask" under a summary opens the route `ask`: the user's next texts are
  questions, answered from the cached transcript in the incoming worker
  (one call, `ANSWER_TIMEOUT`, the transcript a prompt-cache block), as a
  reply to the audio. "Done" (`askDone`) leaves: its button goes and the
  menu comes as a new message (a `menu` tap redraws the old question
  screen up the chat: it looked like nothing happened). Half an hour after
  the last question, or a link, a text is a search again; a voice message
  or a photo is asked to be typed. Questions need the
  transcript (a summary first) and a running plan: `QUESTIONS_PER_DAY` (20),
  a trial `TRIAL_QUESTIONS_PER_DAY` (5; at its limit it hears what paying
  gives, with the Stars page and change-plan), in the last 24 hours (usage ledger
  kind `ask`, its cost in the AI spend). No plan: every plan's invoice.
- "Ask about the podcast" on the podcast page (AI on; route `showAsk`,
  `app/service/ai/show_ask.py`, `showAskModule`): questions about the whole
  show, answered from what is already there (the owner's call, 2026-10-26:
  nothing is transcribed for it). The material is the channel's transcripts
  someone paid for (`ai.channel_transcripts`, matched to the feed by the
  enclosure's ref, else the title) and the newest episodes' title, date and
  description from the feed copy `feed_cache` keeps, within `CONTEXT_CHARS`
  (a prompt-cache block). Each episode is labelled (E1 the newest); the
  model cites the labels, the answer shows them as numbers with one download
  button per cited episode (the rec button by hash from the start, as the
  digest's; at most `MAX_CITED`) and a line on what it was based on. One
  question, one text answer with Back (to the page); the next question is
  typed on the same screen, no history. Same daily count as questions about
  an episode (usage kind `ask`, ref `show:<channel>`), the same offers at
  the limit or without a plan; `question_answered {scope: show}`.
  Lock: `python app/service/ai/test_show_ask.py` (CD gate),
  `python tools/botsim/test_botsim.py`.
- Summaries of new episodes (opt-in, /settings AI summaries, `users.flags`
  `auto_summary`, action `sumAuto`; turning it on without a plan says
  they come with one; `app/service/ai/auto.py`): after the
  circle delivers an episode (`Sender._queue_auto_summaries`, circle only,
  never a click) each chat that turned it on and whose plan's hours cover
  the episode gets it queued, charged like a tap; no plan: none (the
  plan-off notice told them). A plan whose hours do not cover the episode:
  none, and once in 30 days (`users.flags` `summary_quota_noticed`, when)
  a note that the episode came without its summary, with the offer a tap
  over the hours gets (`app/service/ai/offer.py`, shared with
  summaryModule), a reply to the audio. A failure is quiet. `ai_requests.auto`: taps are claimed
  first, and a tap on an automatic request makes it a tap. The summary
  answers the delivered audio: the sender notes each chat's audio message
  (`_note_audio_message`, Bot API, rich and agent sends; bookkeeping that
  never fails a delivery).
- Once per user (`app/service/ai/hint.py`, `users.flags` `summary_hint_sent`):
  after a delivered episode with the Summary button, a chat with a plan
  running (a trial too) that never asked for a summary gets a note on what
  it does, a reply to that audio. Without a plan the button is an invoice:
  no note. Never in the same delivery as the rich message note; never fails
  a delivery (`Sender._send_summary_hints`).
Lock: `python app/service/ai/test_summary.py` (CD gate; the worker part
runs where the bot's requirements are installed),
`python app/core/sender/test_record_delivery.py`,
`python app/service/record/test_free_limit.py`.

## Nightly backup

`app/jobs/backup_db.py` runs `scripts/backup_to_yandex.sh` once a day
(00:15) while the bot keeps writing. The database is in WAL mode, so a
`tar` over the live `db/` can pair the main file with a `-wal` from
another moment ("file changed as we read it"): an archive that may not
restore. The script archives copies made by SQLite's backup API
(`scripts/db_snapshot.py`, one read transaction, checked by
`integrity_check`); a copy that fails the check is never uploaded. Never
point `tar` at the live database again.
Lock: `python scripts/test_db_snapshot.py` (CD gate).

## botsim

`tools/botsim` runs the real bot in one process against a fake Telegram
(Telethon events in, Bot API responses out) on a fresh or copied database:
`python tools/botsim/cli.py -c "send /start" -c "tap menu"` prints what the
user would see. Use it to walk a flow end to end before shipping it (it
found the OPML duplicate channels and the `flush=` TypeError). It needs the
bot's requirements; a copy of a real database stays outside the repo.
README: `tools/botsim/README.md`. Lock: `python tools/botsim/test_botsim.py`.

## Tests

Run the smallest existing suite that covers the change (for send jobs:
`python db/test_send_outbox.py`). A refactor of claim/dispatch is
incomplete without a test for the invariant you think you preserved.
