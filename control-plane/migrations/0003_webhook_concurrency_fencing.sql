PRAGMA foreign_keys = ON;

-- One tenant maps to one active Stripe subscription record. Account linking is
-- based only on exact Stripe customer + subscription identifiers, never email.
CREATE UNIQUE INDEX subscriptions_tenant_unique ON subscriptions(tenant_id);
ALTER TABLE subscriptions ADD COLUMN stripe_event_created_at INTEGER NOT NULL DEFAULT 0;

-- Webhook processing leases are fenced by a per-attempt token so an expired
-- worker cannot overwrite the result of a newer retry owner.
ALTER TABLE stripe_events ADD COLUMN lease_token TEXT;
ALTER TABLE stripe_events ADD COLUMN lease_expires_at INTEGER;
ALTER TABLE stripe_events ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0);
-- New events persist a body fingerprint. Legacy rows use an empty sentinel;
-- the first signed retry may claim it, after which the payload is immutable.
ALTER TABLE stripe_events ADD COLUMN payload_sha256 TEXT NOT NULL DEFAULT ''
  CHECK (length(payload_sha256) IN (0, 64));
