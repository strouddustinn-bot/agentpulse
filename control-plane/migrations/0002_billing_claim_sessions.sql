PRAGMA foreign_keys = ON;

-- Pre-payment checkout claim state. Created when a checkout is started
-- (before the tenant necessarily exists), updated to 'ready' once Stripe
-- confirms payment via webhook, and terminally 'claimed' by the one-time
-- POST /v1/onboarding/claim exchange recorded in onboarding_claims.
CREATE TABLE checkout_sessions (
  stripe_checkout_session_id TEXT PRIMARY KEY,
  claim_nonce_hash TEXT NOT NULL UNIQUE,
  price_id TEXT NOT NULL,
  plan TEXT NOT NULL CHECK (plan IN ('starter','pro','business')),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','ready','claimed','expired','canceled')),
  tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  ready_at INTEGER,
  claimed_at INTEGER,
  retention_purge_at INTEGER
);
CREATE INDEX checkout_sessions_status_expiry ON checkout_sessions(status, expires_at);
CREATE INDEX checkout_sessions_tenant ON checkout_sessions(tenant_id);

-- Hashed, HttpOnly browser sessions issued once by a verified claim.
-- The raw session token and CSRF secret are never persisted, only their
-- SHA-256 hashes; rotated_from_id preserves rotation lineage for audit.
CREATE TABLE browser_sessions (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  session_hash TEXT NOT NULL UNIQUE,
  csrf_token_hash TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  last_seen_at INTEGER,
  rotated_from_id TEXT,
  revoked_at INTEGER,
  retention_purge_at INTEGER,
  UNIQUE(id, tenant_id),
  FOREIGN KEY (rotated_from_id, tenant_id) REFERENCES browser_sessions(id, tenant_id)
);
CREATE INDEX browser_sessions_tenant_active ON browser_sessions(tenant_id, revoked_at, expires_at);

-- Normalized entitlement status, separate from the raw Stripe subscription
-- status, so route-level checks depend on one deterministic value that
-- accounts for the approved three-day failed-payment grace period.
ALTER TABLE subscriptions ADD COLUMN entitlement_status TEXT NOT NULL DEFAULT 'blocked' CHECK (entitlement_status IN ('active','grace','blocked'));
ALTER TABLE subscriptions ADD COLUMN grace_period_ends_at INTEGER;
UPDATE subscriptions
SET entitlement_status = CASE
  WHEN status IN ('active','trialing') THEN 'active'
  ELSE 'blocked'
END;

-- Explicit webhook processing outcome, distinct from the free-text
-- processing_error detail already recorded on this table.
ALTER TABLE stripe_events ADD COLUMN outcome TEXT NOT NULL DEFAULT 'pending' CHECK (outcome IN ('pending','processed','skipped','failed'));
ALTER TABLE stripe_events ADD COLUMN retention_purge_at INTEGER;
UPDATE stripe_events
SET outcome = CASE
  WHEN processing_error IS NOT NULL THEN 'failed'
  WHEN processed_at IS NOT NULL THEN 'processed'
  ELSE 'pending'
END;
