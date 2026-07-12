PRAGMA foreign_keys = ON;

CREATE TABLE tenants (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL COLLATE NOCASE UNIQUE,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE subscriptions (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  stripe_customer_id TEXT NOT NULL,
  stripe_subscription_id TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL CHECK (status IN ('incomplete','trialing','active','past_due','canceled','unpaid','paused')),
  price_id TEXT NOT NULL,
  plan TEXT NOT NULL CHECK (plan IN ('starter','pro','business')),
  agent_limit INTEGER NOT NULL CHECK (agent_limit > 0),
  current_period_end INTEGER,
  updated_at INTEGER NOT NULL
);
CREATE INDEX subscriptions_tenant_status ON subscriptions(tenant_id, status, updated_at DESC);
CREATE UNIQUE INDEX subscriptions_customer ON subscriptions(stripe_customer_id);

CREATE TABLE account_credentials (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  credential_hash TEXT NOT NULL UNIQUE,
  prefix TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  last_used_at INTEGER,
  revoked_at INTEGER
);
CREATE INDEX account_credentials_tenant ON account_credentials(tenant_id, revoked_at);

CREATE TABLE enrollment_tokens (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  created_by_credential_id TEXT NOT NULL REFERENCES account_credentials(id),
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  consumed_at INTEGER,
  consumed_by_agent_id TEXT
);
CREATE INDEX enrollment_tokens_tenant_expiry ON enrollment_tokens(tenant_id, expires_at, consumed_at);

CREATE TABLE policies (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  document TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  UNIQUE(tenant_id, version)
);

CREATE TABLE agents (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  agent_key TEXT NOT NULL,
  hostname TEXT NOT NULL,
  credential_hash TEXT NOT NULL UNIQUE,
  prefix TEXT NOT NULL,
  local_policy_ceiling TEXT NOT NULL CHECK (local_policy_ceiling IN ('off','alert','ask','auto')),
  policy_version INTEGER,
  enrolled_at INTEGER NOT NULL,
  last_seen_at INTEGER,
  revoked_at INTEGER,
  UNIQUE(tenant_id, agent_key)
);
CREATE INDEX agents_tenant_seen ON agents(tenant_id, last_seen_at DESC);

CREATE TABLE heartbeat_events (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  observed_at INTEGER NOT NULL,
  received_at INTEGER NOT NULL,
  payload TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  UNIQUE(agent_id, idempotency_key)
);
CREATE INDEX heartbeat_tenant_received ON heartbeat_events(tenant_id, received_at DESC);

CREATE TABLE incidents (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  fingerprint TEXT NOT NULL,
  kind TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open','resolved','escalated')),
  severity TEXT NOT NULL CHECK (severity IN ('info','warning','critical')),
  detail TEXT NOT NULL,
  opened_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(agent_id, fingerprint)
);
CREATE INDEX incidents_tenant_status ON incidents(tenant_id, status, updated_at DESC);

CREATE TABLE stripe_events (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  received_at INTEGER NOT NULL,
  processed_at INTEGER,
  processing_error TEXT
);

CREATE TABLE onboarding_claims (
  checkout_session_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  claimed_at INTEGER NOT NULL,
  account_credential_id TEXT NOT NULL REFERENCES account_credentials(id)
);
