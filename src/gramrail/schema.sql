CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    dedupe_key TEXT,
    state TEXT NOT NULL CHECK(state IN ('queued','running','succeeded','failed','cancelled','uncertain')),
    priority INTEGER NOT NULL,
    run_after REAL NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL,
    recovery TEXT NOT NULL CHECK(recovery IN ('retry','uncertain')),
    lease_token TEXT,
    lease_until REAL,
    result TEXT,
    progress TEXT,
    error TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(bot_id, dedupe_key)
);
CREATE INDEX IF NOT EXISTS jobs_due ON jobs(bot_id,state,run_after,priority);
CREATE INDEX IF NOT EXISTS jobs_expired ON jobs(state,lease_until);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id TEXT NOT NULL,
    resource TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    name TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS events_scope ON events(bot_id,seq);
CREATE TABLE IF NOT EXISTS updates (
    bot_id TEXT NOT NULL,
    update_id INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY(bot_id,update_id)
);
CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL,
    definition TEXT NOT NULL,
    state TEXT NOT NULL,
    revision INTEGER NOT NULL,
    data TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active','completed')),
    dedupe_key TEXT,
    fingerprint TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(bot_id,dedupe_key)
);
CREATE TABLE IF NOT EXISTS signals (
    run_id TEXT NOT NULL REFERENCES workflows(id),
    event_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    response TEXT NOT NULL,
    PRIMARY KEY(run_id,event_key)
);
CREATE TABLE IF NOT EXISTS forms (
    bot_id TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    definition TEXT NOT NULL,
    step INTEGER NOT NULL,
    answers TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('active','completed','cancelled','expired')),
    revision INTEGER NOT NULL,
    expires_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY(bot_id,chat_id,user_id)
);
CREATE TABLE IF NOT EXISTS rate_limits (
    key TEXT PRIMARY KEY,
    next_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cursors (
    bot_id TEXT PRIMARY KEY,
    offset INTEGER NOT NULL
);
