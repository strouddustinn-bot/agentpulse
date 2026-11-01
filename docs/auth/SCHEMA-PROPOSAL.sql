-- DESIGN ONLY. DO NOT APPLY. Review and promote to control-plane/migrations after sign-off.
-- No existing billing/host data is altered.
CREATE TABLE tenant_clerk_org_links (
 tenant_id TEXT PRIMARY KEY REFERENCES tenants(id) ON DELETE RESTRICT,
 clerk_org_id TEXT NOT NULL UNIQUE,
 linked_by_clerk_user_id TEXT NOT NULL,
 linked_at INTEGER NOT NULL
);
CREATE TABLE tenant_member_links (
 tenant_id TEXT NOT NULL REFERENCES tenant_clerk_org_links(tenant_id) ON DELETE RESTRICT,
 clerk_user_id TEXT NOT NULL,
 activated_at INTEGER NOT NULL,
 revoked_at INTEGER,
 PRIMARY KEY (tenant_id, clerk_user_id)
);
CREATE INDEX tenant_members_by_clerk_user ON tenant_member_links(clerk_user_id, revoked_at);
CREATE TABLE platform_admin_grants (
 clerk_user_id TEXT PRIMARY KEY,
 granted_by TEXT NOT NULL,
 granted_at INTEGER NOT NULL,
 revoked_at INTEGER
);
CREATE TABLE identity_audit_events (
 id TEXT PRIMARY KEY,
 actor_clerk_user_id TEXT NOT NULL,
 tenant_id TEXT,
 event_type TEXT NOT NULL,
 reason TEXT,
 created_at INTEGER NOT NULL
);
CREATE INDEX identity_audit_by_tenant ON identity_audit_events(tenant_id,created_at DESC);
-- IMPORTANT: link creation needs a transactional claim; foreign keys enforced.
-- Test repeated claims, deleted users, role revocation and legacy-session coexistence.
