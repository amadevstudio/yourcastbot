-- The bot's database schema, structure only: a fresh database for botsim (README.md).
-- Taken from the production schema; no rows but the plans, whose prices the bot shows anyway.
-- Refresh: sqlite3 -readonly <db> .schema, then keep the IF NOT EXISTS forms.
CREATE TABLE IF NOT EXISTS admins (
id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
mail TEXT NOT NULL,
password TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS user_channel_cs (
                id integer PRIMARY KEY,
                user_telegram_id integer NOT NULL,
                channel_id integer NOT NULL,
                last_guid text,
                last_date text,
                notify integer
            , rate integer);
CREATE TABLE IF NOT EXISTS tariffs (
                id integer PRIMARY KEY,
                level integer NOT NULL,
                price integer NOT NULL,
                notify_count integer NOT NULL,
                compression integer
            , channel_control integer);
CREATE TABLE IF NOT EXISTS user_tariff_cs (
                id integer PRIMARY KEY,
                uid integer NOT NULL,
                tariff_id integer NOT NULL,
                balance integer
                notify_count integer,
                time_left integer
            , notify_count interger);
CREATE TABLE IF NOT EXISTS "users" (
                "id"    INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
                "telegramId"    INTEGER NOT NULL UNIQUE,
                "lang"    char(15),
                "bitrate"    char(7),
                "ref_id"    integer, deleted_at text, nosub_digest_enabled INTEGER NOT NULL DEFAULT 1, nosub_digest_sent_at TEXT, created_at TEXT, episode_format TEXT, rich_hint_sent INTEGER NOT NULL DEFAULT 0, flags TEXT);
CREATE TABLE IF NOT EXISTS "channels" (
                    id integer PRIMARY KEY AUTOINCREMENT UNIQUE,
                    itunes_id integer,
                    name text,
                    rss_link text
                , last_guid TEXT, last_date TEXT, http_etag TEXT, http_last_modified TEXT);
CREATE TABLE IF NOT EXISTS genres (
                id integer PRIMARY KEY,
                name text
            );
CREATE TABLE IF NOT EXISTS genre_to_podcast (
                podcast_id integer NOT NULL,
                genre_id integer NOT NULL,
                is_main integer,
                PRIMARY KEY (podcast_id, genre_id)
            );
CREATE TABLE IF NOT EXISTS payment_service_user_data (
                user_id integer NOT NULL,
                service_type text NOT NULL,
                email text NOT NULL,
                last_replenishment text,
                active integer NOT NULL,
                PRIMARY KEY (user_id, service_type)
            );
CREATE TABLE IF NOT EXISTS tg_channels (
                id integer PRIMARY KEY AUTOINCREMENT UNIQUE,
                user_id integer NOT NULL,
                tg_id integer NOT NULL,
                active integer NOT NULL
            );
CREATE TABLE IF NOT EXISTS subscription_to_tg_channel_cs (
                user_channel_cs_id integer NOT NULL,
                tg_channel_id integer NOT NULL,
                PRIMARY KEY (user_channel_cs_id, tg_channel_id)
            );
CREATE TABLE IF NOT EXISTS payment_history (
                user_id integer NOT NULL,
                service_type text NOT NULL,
                invoice_id text,
                invoice_hash text,
                status text,
                amount integer,
                datetime text,
                PRIMARY KEY (user_id, service_type, invoice_id)
            );
CREATE TABLE IF NOT EXISTS bot_runtime_kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS send_outbox (id INTEGER PRIMARY KEY, created_at TEXT, action TEXT NOT NULL, user_id TEXT NOT NULL, payload_json TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, leased_until TEXT NULL, available_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS send_outbox_claim_idx ON send_outbox (status, available_at, id);
CREATE INDEX IF NOT EXISTS ucc_user_notify_idx ON user_channel_cs (user_telegram_id, notify);
CREATE INDEX IF NOT EXISTS ucc_channel_notify_idx ON user_channel_cs (channel_id, notify);
CREATE INDEX IF NOT EXISTS utc_uid_idx ON user_tariff_cs (uid);
CREATE TABLE IF NOT EXISTS digest_outbox (
    user_telegram_id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL
, status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0, leased_until TEXT NULL, available_at TEXT);
CREATE INDEX IF NOT EXISTS digest_outbox_claim_idx
    ON digest_outbox (status, available_at, user_telegram_id)
;
CREATE TABLE IF NOT EXISTS admin_mail_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by TEXT,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    parse_mode TEXT NOT NULL DEFAULT '',
    attachment_type TEXT NOT NULL DEFAULT '',
    attachments_json TEXT NOT NULL DEFAULT '[]',
    to_creator_only INTEGER NOT NULL DEFAULT 1,
    recipients_text TEXT NOT NULL DEFAULT '',
    language TEXT,
    total INTEGER NOT NULL DEFAULT 0,
    sent INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    started_at TEXT,
    finished_at TEXT
, cursor_index INTEGER NOT NULL DEFAULT 0, recipients_json TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS admin_mail_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    tgid TEXT NOT NULL,
    result TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS admin_mail_events_job ON admin_mail_events(job_id);
CREATE TABLE IF NOT EXISTS telegram_cache ( key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS telegram_cache_expires ON telegram_cache (expires_at);
CREATE TABLE IF NOT EXISTS listening_episodes (
    id INTEGER PRIMARY KEY, source TEXT NOT NULL, episode_hash TEXT NOT NULL,
    title TEXT NOT NULL, show_name TEXT NOT NULL, callback_json TEXT NOT NULL,
    seen_at REAL NOT NULL, UNIQUE(source,episode_hash)
);
CREATE TABLE IF NOT EXISTS channel_episode (
    channel_id INTEGER PRIMARY KEY, episode_id INTEGER NOT NULL, episode_cursor TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS digest_episodes (
    user_telegram_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, episode_id INTEGER NOT NULL,
    revision TEXT NOT NULL, created_at REAL NOT NULL,
    PRIMARY KEY(user_telegram_id,channel_id)
);
CREATE TABLE IF NOT EXISTS feed_recovery (
    channel_id INTEGER PRIMARY KEY,
    status TEXT NOT NULL,
    paused INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL,
    available_at REAL NOT NULL,
    leased_until REAL,
    lease_token TEXT,
    checked_at REAL,
    recovered_at REAL,
    result TEXT,
    notice_cursor INTEGER NOT NULL DEFAULT 0,
    notice_done INTEGER NOT NULL DEFAULT 0,
    notice_after REAL NOT NULL DEFAULT 0,
    notice_token TEXT
);
CREATE INDEX IF NOT EXISTS feed_recovery_due
    ON feed_recovery(status, available_at);
CREATE TABLE IF NOT EXISTS winback (
    user_telegram_id INTEGER PRIMARY KEY,
    ended_at REAL NOT NULL,
    stage INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS usage_events (
    id INTEGER PRIMARY KEY, at REAL NOT NULL, user_id INTEGER NOT NULL, kind TEXT NOT NULL,
    ref TEXT, mb REAL NOT NULL DEFAULT 0, cost_usd REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS usage_events_user ON usage_events(user_id, kind, at);
CREATE INDEX IF NOT EXISTS usage_events_at ON usage_events(at);
CREATE TABLE IF NOT EXISTS ai_episodes (
    ref TEXT PRIMARY KEY, link TEXT NOT NULL, channel_id INTEGER, title TEXT NOT NULL,
    show TEXT NOT NULL, seen_at REAL NOT NULL, seconds INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ai_transcripts (
    ref TEXT PRIMARY KEY, text TEXT NOT NULL, source TEXT NOT NULL,
    cost_usd REAL NOT NULL, created_at REAL NOT NULL, seconds REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ai_summaries (
    ref TEXT NOT NULL, lang TEXT NOT NULL, text TEXT NOT NULL,
    cost_usd REAL NOT NULL, created_at REAL NOT NULL, PRIMARY KEY (ref, lang)
);
CREATE TABLE IF NOT EXISTS ai_requests (
    id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL, ref TEXT NOT NULL, lang TEXT NOT NULL,
    status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL, leased_until REAL, seconds INTEGER NOT NULL DEFAULT 0
, reply_to INTEGER, auto INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ai_requests_chat ON ai_requests(chat_id, created_at);
CREATE INDEX IF NOT EXISTS ai_requests_status ON ai_requests(status, id);
CREATE TABLE IF NOT EXISTS feed_cache (
    url TEXT PRIMARY KEY, file TEXT NOT NULL, size INTEGER NOT NULL,
    etag TEXT, last_modified TEXT, checked_at REAL NOT NULL, used_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS feed_cache_used ON feed_cache(used_at);

INSERT OR IGNORE INTO tariffs (id, level, price, notify_count, compression, channel_control) VALUES
    (1, 1, 100, 60, 0, 0), (2, 2, 200, 400, 1, 0), (3, 3, 500, -1, 1, 1);
