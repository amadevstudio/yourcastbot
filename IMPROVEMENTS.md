# Improvements Plan

## Priority 1 — Reliability

### Replace shelve with thread-safe storage
- `shelve` at module level without locking — corruption risk under concurrent writes
- Navigation states, resend flags, message structures all stored there
- Options: `dbm` with `threading.Lock` wrapper, Redis, or SQLite WAL-mode table
- Affects: `app/repository/storage/storage.py`, all callers

### SQLite connection management
- Current: open/close per operation, `SQLighter(db_path)` scattered across codebase
- `podcastsUpdater.py` opens/closes 5-10 times per channel iteration
- Fix: connection pool or context manager with WAL mode, reduce open/close churn
- `db/sqliteAdapter.py` — 1695 lines, needs splitting by domain (users, channels, payments, subscriptions)

### Graceful shutdown
- All threads `daemon=True` — process kill = immediate death
- No flush of pending queues, no shelve sync
- Add signal handlers (SIGTERM/SIGINT), drain queues before exit

## Priority 2 — Safety

### Tests for payment flows
- Zero tests in project
- Payment modules (Robokassa, Patreon, CryptoBot) handle money — most critical to test
- Start with: subscription activation, expiry check, balance operations
- Add at least integration tests for `paymentSafeModule.is_subscription_active`

### Config validation
- `constants.py` not in repo, all secrets imported as module attributes
- Missing constant = crash at import with unclear error
- Add `.env` support with `python-dotenv`, validate required vars at startup

## Priority 3 — Code Quality

### Consistent naming
- Mixed: `camelCase` (`telegramId`), `snake_case` (`channel_link`), abbreviations (`utg`, `pgd`)
- DB columns in camelCase, Python code in snake_case — confusing at boundaries
- Gradual migration to snake_case, starting with new code

### Split sqliteAdapter.py
- 1695 lines, single file
- Split by domain: `UserRepository`, `ChannelRepository`, `PaymentRepository`, `SubscriptionRepository`
- Extract common query patterns

### Async-native architecture
- Telethon is async, but wrapped in threads with `run_until_complete`
- Each `RecordSender` creates own event loop
- Long-term: migrate to native async with `asyncio.Queue` instead of `threading` + `queue.Queue`

## Priority 4 — Features & DX

### Docker compose for development
- Current `docker-compose.yml` is minimal (no DB volume, no env file)
- Add: persistent volume for SQLite, `.env` file mounting, health checks

### Logging improvements
- Custom `Logger` class — consider structured logging (`structlog` or stdlib `logging`)
- Add request IDs for tracing user actions across threads

### Deployment pipeline
- GitHub Actions workflow fixed (`script_stop`, `python3`, venv auto-creation)
- Consider: health check endpoint, zero-downtime restart, rollback strategy

## Not Worth Doing

- Full ORM migration (SQLAlchemy) — too much churn for current scale
- Rewrite in aiogram/pyrogram — working Telethon setup, not broken
- Microservices split — monolith is fine for this scale
