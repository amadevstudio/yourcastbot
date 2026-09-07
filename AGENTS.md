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
- **Admin broadcasts** are `admin_mail_jobs` processed by a jobs-role
  thread. Do not dump mailings onto rec/circle/send workers. The admin
  HTTP API is a fourth supervisor role (`admin`) bound to localhost.

## Tests

Run the smallest existing suite that covers the change (for send jobs:
`python db/test_send_outbox.py`). A refactor of claim/dispatch is
incomplete without a test for the invariant you think you preserved.
