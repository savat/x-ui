-- Unified VPN Panel - SQLite schema (all timestamps are UTC, ISO-8601 "YYYY-MM-DDTHH:MM:SSZ")
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS admins (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'superadmin'
                    CHECK (role IN ('superadmin', 'admin', 'support')),
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until    TEXT,
    created_at      TEXT NOT NULL,
    last_login      TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'disabled', 'expired')),
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    max_devices     INTEGER NOT NULL DEFAULT 0,   -- NOT enforced in Phase 1 (see docs/ARCHITECTURE.md)
    max_connections INTEGER NOT NULL DEFAULT 1,   -- 0 = unlimited
    quota           INTEGER NOT NULL DEFAULT 0,   -- bytes, Phase 2 (not measured yet)
    note            TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_users_status  ON users(status);
CREATE INDEX IF NOT EXISTS idx_users_expires ON users(expires_at);

CREATE TABLE IF NOT EXISTS protocol_accounts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    protocol    TEXT NOT NULL,                    -- zivpn
    uuid        TEXT,
    secret      TEXT,                             -- protocol credential (zivpn). Never logged.
    config      TEXT NOT NULL DEFAULT '{}',       -- JSON, adapter-owned
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'revoked', 'revoke_failed')),
    created_at  TEXT NOT NULL,
    UNIQUE (user_id, protocol)
);
CREATE INDEX IF NOT EXISTS idx_pa_protocol ON protocol_accounts(protocol);

CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    protocol        TEXT NOT NULL,
    source_ip       TEXT,
    device          TEXT,
    connected_at    TEXT NOT NULL,
    last_seen       TEXT,
    disconnected_at TEXT
);

CREATE TABLE IF NOT EXISTS servers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    ip          TEXT,
    hostname    TEXT,
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER,                           -- admins.id of the actor (NULL = system)
    actor      TEXT,
    action     TEXT NOT NULL,
    detail     TEXT,
    ip         TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);
