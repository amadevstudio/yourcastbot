# Improvements Plan

## Done

### Shelve thread safety
- Added `threading.RLock()` to `app/repository/storage/storage.py` (26 functions wrapped)
- Added `threading.RLock()` to `app/repository/storage/telegram_cache.py` (4 functions wrapped)
- RLock (not Lock) — needed because `add_user_state()` calls `get_user_curr_state()` internally

### SQLite WAL mode + busy_timeout
- `db/sqliteAdapter.py`: constructor now sets `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=30000`, `timeout=30`
- Concurrent reads now work without blocking, writer retries internally on contention

### SQLighter context manager
- Added `__enter__`/`__exit__` to `SQLighter` — supports `with SQLighter(db_path) as db:`
- Backwards-compatible: existing open/close pattern still works

### SQLighter caller migration to `with` statement
- All 37+ sites in `app/` migrated from manual `.close()` to `with` statement
- Files: default_middleware, podcastsUpdater, paymentSafeModule, patreonPaymentModule, adminModule, advertisingModule, channelModule, menuModule, podcastModule, recsModule, searchModule, subsModule, topModule, welcomeModule, paymentModule, robokassaPaymentModule, cryptoBotPaymentModule, subscription.py, balance_watcher.py, errors.py
- Fixed connection leak in `paymentSafeModule.giveAward` (early return without `.close()`)
- Scripts/ and migrations/ left as-is (run once, low risk)

### Graceful shutdown
- `main.py`: signal handlers for SIGTERM/SIGINT
- Syncs and closes both shelve stores before exit
- Prevents data loss on supervisor restart / deploy

### CI/CD deployment fixes
- `.github/workflows/main.yml`: `script_stop: true` (fail on first SSH error)
- `python` → `python3`, auto-create venv if missing

### Bug fixes
- **`is_not_modified_error` (was `skip_not_modified`)** — inverted logic silently swallowed ALL `ApiTelegramException` in message edit paths. Both return paths (False/None) were falsy, so `raise` never executed. Renamed, rewrote with correct boolean semantics.
- **`render_messages` infinite recursion** — recursive call on `message_to_edit_not_found` had no depth limit. Added `_retry=False` parameter with guard.
- **`<br>` → `<b>`** in podcastsUpdater notification message (broken HTML tag)
- **Thread name typo** in `main.py`: `t_balance_watcher.name` was set to `'Patreon payment watcher'` instead of `t_patreon_watcher.name`

### Mutable default arguments
- `telegram_cache.py`: `expiration_date=datetime.now()+timedelta(3)` → `None` with body computation
- `sqliteAdapter.py`: `get_channel_or_next(channel_set=[])` → `channel_set=None`
- `message_master.py`: `message_master(message_structures=[])` → `None`

### Vulnerable dependencies
- `lxml` 4.9.2 → >=6.1.0
- `requests` pinned → >=2.33.0
- `urllib3` 1.26.19 → >=2.6.3

## Priority 1 — Reliability

### Connection pooling (Phase 2 of SQLite work)
- Thread-local connections via `threading.local()` in new `db/connection.py`
- `SQLighter` accepts optional existing connection for reuse
- `get_db()` convenience function — eliminate `SQLighter(db_path)` + `.close()` pattern
- podcastsUpdater: 12 opens/cycle → 1 reuse per cycle
- Graceful connection cleanup in shutdown handler

### Retry logic for Telegram API calls
- `message_master.py` retries on `message_to_edit_not_found` but not on rate limits (429) or temporary failures
- `recordSender` has no retry on send failure — record lost
- Add exponential backoff wrapper for Telegram API calls

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

### Split sqliteAdapter.py
- 1695 lines, single file
- Split by domain: `UserRepository`, `ChannelRepository`, `PaymentRepository`, `SubscriptionRepository`
- Extract common query patterns

### Consistent naming
- Mixed: `camelCase` (`telegramId`), `snake_case` (`channel_link`), abbreviations (`utg`, `pgd`)
- DB columns in camelCase, Python code in snake_case — confusing at boundaries
- Gradual migration to snake_case, starting with new code

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
- Health check endpoint, zero-downtime restart, rollback strategy

## Not Worth Doing

- Full ORM migration (SQLAlchemy) — too much churn for current scale
- Rewrite in aiogram/pyrogram — working Telethon setup, not broken
- Microservices split — monolith is fine for this scale
