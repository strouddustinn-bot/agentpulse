# AgentPulse Paid-Pilot Control Plane

## Product boundary

The control plane is a multi-tenant Cloudflare Worker backed by D1. The downloadable Linux agent remains dependency-free and owns all host observations and remediation. The cloud stores entitlement, fleet health, incidents, and policy intent; it does not execute shell commands on customer servers.

## Trust boundaries

1. Stripe → Worker: raw-body webhook authenticated with Stripe signature and replay window.
2. Customer browser/operator → Worker: one-time account credential returned after verified Checkout claim. Only its SHA-256 hash is persisted.
3. Account → enrollment: an active account creates a short-lived one-time enrollment token.
4. Linux host → enrollment: token is atomically consumed and exchanged for a unique per-agent credential. Only its hash is stored.
5. Agent → API: every heartbeat and policy request is authenticated by that agent credential and tenant resolved server-side. Tenant identifiers supplied by clients are never trusted.
6. Cloud policy → host: policy is advisory and monotonic-safe. Effective authority is the minimum of local ceiling and cloud mode using `off < alert < ask < auto`. Cloud policy can narrow authority but cannot widen it.

## MVP API contract

- `GET /health` → `{ok, service, version, environment}`.
- `POST /v1/billing/checkout` → creates a Stripe Checkout Session for an allowlisted Price ID.
- `POST /v1/stripe/webhook` → signed and idempotent subscription lifecycle ingestion.
- `POST /v1/onboarding/claim` → verifies completed Checkout and returns an account credential once.
- `POST /v1/enrollment-tokens` (account bearer) → short-lived one-time token.
- `POST /v1/agents/enroll` (enrollment bearer) → per-agent credential returned once.
- `POST /v1/agents/heartbeat` (agent bearer) → bounded, idempotent fleet event ingestion.
- `GET /v1/agents/policy` (agent bearer) → policy narrowed to the enrolled local ceiling.
- `GET /v1/fleet` (account bearer) → only the authenticated tenant's agents/incidents.
- `POST /v1/billing/portal` (account bearer) → Stripe Customer Portal session.

All JSON endpoints reject bodies over 64 KiB before parsing. Heartbeat arrays and string fields have explicit bounds. Errors use stable codes and never include secrets or raw upstream errors.

## Stripe lifecycle

Handled events: `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, and `invoice.payment_failed`. Event IDs are inserted before side effects and processed transactionally. Duplicate delivery returns success without repeating issuance. `past_due`, `unpaid`, `canceled`, or `paused` fail closed for new enrollment and heartbeat ingestion. Customer data is re-read from Stripe for onboarding and portal operations.

## D1 ownership

Every tenant-owned row carries `tenant_id`; foreign keys and tenant-leading indexes are mandatory. Credentials and enrollment tokens are stored only as SHA-256 hashes plus non-sensitive prefixes. Heartbeats use per-agent idempotency keys. Migrations are the only schema mutation path.

## Threat model

- Cross-tenant IDOR: tenant is derived from credential joins, never request input.
- Credential theft: scoped account/agent credentials, one-time enrollment, rotation/revocation, no plaintext persistence, no logging authorization headers.
- Replay: expiring enrollment tokens, single-use claim transaction, heartbeat idempotency keys, Stripe timestamp tolerance and event IDs.
- Billing bypass: active/trialing subscription checked on every enrollment and heartbeat.
- Policy escalation: server cannot return a mode above local ceiling; local config remains authoritative.
- Payload abuse: Content-Length precheck plus bounded body reader and schema bounds.
- Webhook spoofing: HMAC verification over unmodified raw bytes before parsing.
- Supply chain: pinned lockfile, CI type/tests, checksums for downloadable releases.

## Release gates

1. Worker tests run in workerd with real local D1 migrations.
2. Python agent safety suite remains green on 3.8/3.10/3.12.
3. Staging D1 migration and Worker deploy complete from CI/manual Wrangler.
4. Test-mode Stripe checkout → claim → enrollment → heartbeat → failed-payment denial passes end to end.
5. Two-tenant isolation and token replay tests pass.
6. Installer verifies a versioned release checksum and writes credentials mode 0600.
7. Agent starts alert-only; auto mode requires an explicit local allowlist.
8. Production secrets exist only in Cloudflare secret bindings.
9. Audit/incident retention and deletion runbook is documented.
10. Live billing is blocked until restricted Stripe keys, exact Price IDs, webhook endpoint, portal configuration, and a safe checkout test are verified.
