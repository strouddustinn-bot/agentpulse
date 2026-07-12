-- Migration: 001_initial_schema.sql
-- Creates all core tables for the AgentPulse backend.
-- All datetime columns are ISO-8601 TEXT (UTC).
-- All IDs are TEXT UUIDs for cross-database portability.
-- Foreign keys are off by default and enforced via application-level checks
-- to keep SQLite operational without PRAGMA foreign_keys complications in tests.

-- ─────────────────────────────────────────────────────────────────────────────
-- Schema version tracking
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS _schema_version (
    version  INTEGER PRIMARY KEY,
    applied  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    rollback TEXT
);

-- ─────────────────────────────────────────────────────────────────────────────
-- agents
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agents (
    id               TEXT    NOT NULL PRIMARY KEY,
    tenant_id        TEXT    NOT NULL DEFAULT 'default',
    hostname         TEXT    NOT NULL,
    os               TEXT    NOT NULL,
    architecture     TEXT    NOT NULL,
    agent_version    TEXT    NOT NULL,
    config_version   TEXT    NOT NULL DEFAULT '',
    machine_id       TEXT    NOT NULL DEFAULT '',
    status           TEXT    NOT NULL DEFAULT 'offline',
    enrolled_at      TEXT    NOT NULL,
    last_seen_at     TEXT    NOT NULL,
    policy_id        TEXT    NOT NULL DEFAULT '',
    tags             TEXT    NOT NULL DEFAULT '[]',
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agents_tenant      ON agents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_agents_last_seen  ON agents(last_seen_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- agent_credentials  — one per agent, never updated once issued
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_credentials (
    id              TEXT    NOT NULL PRIMARY KEY,
    agent_id        TEXT    NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    credential_hash TEXT    NOT NULL,
    credential_prefix TEXT  NOT NULL,
    created_at      TEXT    NOT NULL,
    revoked_at      TEXT,
    expires_at      TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cred_hash  ON agent_credentials(credential_hash);
CREATE INDEX IF NOT EXISTS idx_cred_agent        ON agent_credentials(agent_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- enrollment_tokens — one-time-use tokens issued by the dashboard
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS enrollment_tokens (
    id                  TEXT    NOT NULL PRIMARY KEY,
    tenant_id           TEXT    NOT NULL DEFAULT 'default',
    token_hash          TEXT    NOT NULL UNIQUE,
    created_by_cred_id  TEXT    NOT NULL,
    created_at          TEXT    NOT NULL,
    expires_at          TEXT    NOT NULL,
    consumed_at         TEXT,
    consumed_by_agent_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_token_hash         ON enrollment_tokens(token_hash);

-- ─────────────────────────────────────────────────────────────────────────────
-- check_ins  — one per check-in cycle
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS check_ins (
    id                 INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    agent_id           TEXT    NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    idempotency_key    TEXT    NOT NULL UNIQUE,
    sequence           INTEGER NOT NULL DEFAULT 1,
    agent_timestamp    TEXT    NOT NULL,
    received_at        TEXT    NOT NULL,
    hostname           TEXT    NOT NULL,
    agent_version      TEXT    NOT NULL,
    config_version     TEXT    NOT NULL DEFAULT '',
    status             TEXT    NOT NULL,
    uptime_seconds     INTEGER NOT NULL DEFAULT 0,
    observations       INTEGER NOT NULL DEFAULT 0,
    breaches           INTEGER NOT NULL DEFAULT 0,
    alerts             INTEGER NOT NULL DEFAULT 0,
    anomalies          INTEGER NOT NULL DEFAULT 0,
    escalations        INTEGER NOT NULL DEFAULT 0,
    blocked            INTEGER NOT NULL DEFAULT 0,
    errors             INTEGER NOT NULL DEFAULT 0,
    offline_queue_depth INTEGER NOT NULL DEFAULT 0,
    payload_json       TEXT    NOT NULL,
    is_duplicate       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_checkin_agent_seq   ON check_ins(agent_id, sequence DESC);
CREATE INDEX IF NOT EXISTS idx_checkin_received     ON check_ins(received_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_checkin_idem   ON check_ins(idempotency_key);

-- ─────────────────────────────────────────────────────────────────────────────
-- check_results  — one row per check type per check-in
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS check_results (
    id                    INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    check_in_id           INTEGER NOT NULL REFERENCES check_ins(id) ON DELETE CASCADE,
    check_id              TEXT    NOT NULL,
    check_type            TEXT    NOT NULL,
    status                TEXT    NOT NULL,
    severity              TEXT    NOT NULL,
    executed_at           TEXT    NOT NULL,
    duration_ms           INTEGER NOT NULL,
    value                 REAL,
    unit                  TEXT    NOT NULL DEFAULT '',
    message               TEXT    NOT NULL DEFAULT '',
    evidence              TEXT    NOT NULL DEFAULT '[]',
    consecutive_failures  INTEGER NOT NULL DEFAULT 0,
    is_baseline_anomaly   INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_result_checkin       ON check_results(check_in_id);
CREATE INDEX IF NOT EXISTS idx_result_check_type    ON check_results(check_type);

-- ─────────────────────────────────────────────────────────────────────────────
-- incidents
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS incidents (
    id                   TEXT    NOT NULL PRIMARY KEY,
    tenant_id            TEXT    NOT NULL DEFAULT 'default',
    agent_id             TEXT    NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    check_id             TEXT    NOT NULL,
    check_type           TEXT    NOT NULL,
    status               TEXT    NOT NULL DEFAULT 'open',
    severity             TEXT    NOT NULL,
    title                TEXT    NOT NULL,
    body                 TEXT    NOT NULL DEFAULT '',
    evidence             TEXT    NOT NULL DEFAULT '[]',
    opened_at            TEXT    NOT NULL,
    acknowledged_at      TEXT,
    acknowledged_by      TEXT    NOT NULL DEFAULT '',
    resolved_at          TEXT,
    resolved_by          TEXT    NOT NULL DEFAULT '',
    remediation_id      TEXT,
    policy_id           TEXT    NOT NULL DEFAULT '',
    is_baseline_anomaly INTEGER NOT NULL DEFAULT 0,
    tags                TEXT    NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_incident_agent       ON incidents(agent_id);
CREATE INDEX IF NOT EXISTS idx_incident_status      ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incident_opened      ON incidents(opened_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- incident_events  — immutable audit trail for incident state changes
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS incident_events (
    id          INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT    NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    event_type  TEXT    NOT NULL,
    actor       TEXT    NOT NULL DEFAULT 'agent',
    actor_id    TEXT    NOT NULL DEFAULT '',
    body        TEXT    NOT NULL DEFAULT '{}',
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ie_incident          ON incident_events(incident_id);
CREATE INDEX IF NOT EXISTS idx_ie_type              ON incident_events(event_type);

-- ─────────────────────────────────────────────────────────────────────────────
-- remediation_runs
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS remediation_runs (
    id                   TEXT    NOT NULL PRIMARY KEY,
    incident_id          TEXT    NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    agent_id             TEXT    NOT NULL,
    action               TEXT    NOT NULL,
    target               TEXT    NOT NULL DEFAULT '',
    risk                 TEXT    NOT NULL,
    status               TEXT    NOT NULL DEFAULT 'pending',
    created_at           TEXT    NOT NULL,
    executed_at          TEXT,
    duration_ms          INTEGER,
    action_taken         TEXT    NOT NULL DEFAULT '',
    output               TEXT    NOT NULL DEFAULT '',
    exit_code            INTEGER,
    verification_passed  INTEGER,
    error                TEXT    NOT NULL DEFAULT '',
    rollback_available   INTEGER NOT NULL DEFAULT 0,
    idempotency_key      TEXT    NOT NULL UNIQUE,
    policy_id            TEXT    NOT NULL DEFAULT '',
    cooldown_active      INTEGER NOT NULL DEFAULT 0,
    attempt              INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_remediation_incident  ON remediation_runs(incident_id);
CREATE INDEX IF NOT EXISTS idx_remediation_status    ON remediation_runs(status);
CREATE INDEX IF NOT EXISTS idx_remediation_idem     ON remediation_runs(idempotency_key);

-- ─────────────────────────────────────────────────────────────────────────────
-- audit_events  — append-only log of all important state transitions
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_events (
    id           INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    tenant_id    TEXT    NOT NULL DEFAULT 'default',
    timestamp    TEXT    NOT NULL,
    component    TEXT    NOT NULL,
    event_type   TEXT    NOT NULL,
    actor        TEXT    NOT NULL DEFAULT '',
    agent_id     TEXT,
    incident_id  TEXT,
    remediation_id TEXT,
    outcome      TEXT    NOT NULL,
    body         TEXT    NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp  ON audit_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_agent      ON audit_events(agent_id);
CREATE INDEX IF NOT EXISTS idx_audit_incident   ON audit_events(incident_id);
CREATE INDEX IF NOT EXISTS idx_audit_type        ON audit_events(event_type);

-- ─────────────────────────────────────────────────────────────────────────────
-- Apply schema version
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO _schema_version (version, rollback)
VALUES (1, NULL);
