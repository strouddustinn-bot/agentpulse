# AgentPulse Status

**Status date:** 2026-07-12
**Repository:** `/home/dstroud/Projects/agentpulse`
**Active branch:** `productization/cloudflare-paid-pilot`
**Pre-merge HEAD:** `6381565` — `feat(agent): add secure SaaS enrollment client`

## Executive status

AgentPulse has progressed from an initial monitoring concept into a real, safety-oriented host monitoring and remediation product with:

- a dependency-light Python agent;
- guarded disk and service remediation;
- approval and audit workflows;
- statistical anomaly detection;
- Linux systemd and macOS launchd support;
- a backend check-in API;
- a persistent local/hosted dashboard;
- a commercial website and paid-beta funnel; and
- the foundation of a multi-tenant Cloudflare control plane.

The single-host agent and its core safety model are substantially implemented. The hosted paid-pilot product is not release-ready yet.

Repository reconciliation is content-complete: all 15 conflicts were resolved as a semantic union, conflict markers were removed, Cloudflare enrollment/control-plane contracts were retained, and incoming safety/backend/macOS behavior was preserved. The user explicitly directed the reconciled merge to be committed despite the executable verification gate being blocked by exhausted Novita sandbox credits. Stripe lifecycle, onboarding, release packaging, and end-to-end staging verification remain incomplete.

## Status legend

- **SHIPPED** — implemented and previously covered by tests or operational verification.
- **PARTIAL** — meaningful implementation exists, but the complete product path is unfinished or currently unverified.
- **ROADMAP** — intentionally not implemented.
- **ABANDONED** — explored but removed or superseded.
- **BLOCKED** — cannot safely progress until a prerequisite is resolved.

## 1. Core monitoring agent — SHIPPED

AgentPulse includes a dependency-light Python daemon for recurring host incidents:

- disk-pressure monitoring;
- crashed-service detection;
- memory-runaway detection;
- persistent JSON state;
- configuration validation;
- one-cycle dry-run operation;
- continuous daemon operation;
- webhook notifications;
- Linux/systemd support; and
- macOS/launchd support.

The policy model is deliberately conservative:

| Mode | Behavior |
|---|---|
| `alert` | Observe and notify only |
| `ask` | Queue remediation for operator approval |
| `auto` | Execute explicitly permitted remediation |

Every check defaults to alert-only. Autonomous remediation must be explicitly enabled.

## 2. Safe remediation loop — SHIPPED

The central remediation flow is:

```text
IMAGINE → SIMULATE → VALIDATE → EXECUTE → VERIFY → RECORD
```

Implemented safety properties include:

- simulation before every real action;
- fail-closed handling of unknown actions;
- service restart restricted to an explicit allowlist;
- no automatic process killing for memory incidents;
- post-action signal remeasurement;
- escalation to a human when remediation fails;
- no automatic retry spiral;
- approval that re-runs rather than bypasses the safety gate;
- dry-run approval previews that do not consume pending actions; and
- persistent remediation outcomes for auditability.

## 3. Disk-cleanup hardening — SHIPPED

Disk remediation received adversarial path-safety hardening:

- system paths and unsafe cleanup roots are rejected;
- repeated-slash prefix bypasses are rejected;
- symlinked-directory escapes are rejected;
- directories are never removed;
- symlinks are never followed or removed;
- only sufficiently old files are eligible;
- cleanup stays inside configured paths and globs; and
- destructive path handling is fuzz-tested.

## 4. Approval and operator workflows — SHIPPED

The pending-remediation lifecycle supports:

- queueing proposed actions;
- listing pending actions;
- approving actions;
- denying actions;
- recording approval and denial history;
- stable errors for unknown pending IDs;
- preserving entries during dry-run previews; and
- revalidating safety when approval occurs.

Relevant CLI commands include:

```text
list-pending
approve
deny
history
list-blocked
unblock-ip
```

## 5. Statistical baselines — SHIPPED

AgentPulse implements dependency-free statistical learning of normal behavior:

- online Welford mean and variance;
- per-metric baseline tracking;
- warm-up windows;
- z-score anomaly detection;
- absolute-deviation floors to reduce flapping;
- persistent baseline state; and
- advisory anomaly alerts.

This is deterministic statistical anomaly detection, not machine learning. Anomalies do not trigger remediation.

## 6. Test and verification infrastructure — SHIPPED, CURRENT RECHECK BLOCKED

The agent has a self-contained test runner that does not require pytest. Test coverage includes:

- configuration validation;
- policy decisions;
- state persistence;
- host checks;
- remediation safeguards;
- decision-loop behavior;
- approval and denial;
- backend check-ins;
- SaaS control-plane client behavior;
- path and command-injection defenses; and
- thousands of fuzz iterations.

The last documented baseline claims:

```text
102 tests
7,500 fuzz iterations
```

That count was previously documented as green. It is not a valid current release receipt because the active branch is mid-merge and has not been reverified after reconciliation.

## 7. Installation and production operation — SHIPPED/PARTIAL

Implemented operational paths include:

- Linux systemd installation;
- macOS launchd installation;
- alert-only default configuration;
- example and local-development configs;
- config validation;
- one-cycle read-only execution;
- uninstall instructions;
- a hardened dashboard systemd unit;
- Docker packaging for hosted components; and
- CI workflows for tests and builds.

Remaining release work includes versioned downloadable artifacts and mandatory checksum verification in the production installer.

## 8. Backend check-in API — SHIPPED

A FastAPI backend exists for centralized agent check-ins and fleet state.

Implemented API surface:

```text
GET  /health
POST /api/agent/checkin
GET  /api/agents
GET  /api/agents/{agent_id}/checkins
POST /api/license/verify
```

Supporting work includes:

- API-key creation and hashing;
- organization-scoped records;
- fleet storage;
- check-in history;
- SQLite persistence;
- a backend CLI;
- Docker packaging;
- backend tests; and
- best-effort agent-side check-in delivery.

The local monitoring and remediation loop remains operational when the backend is unavailable.

## 9. Persistent dashboard — SHIPPED/PARTIAL

A separate dashboard service exists with:

### Backend

- FastAPI;
- SQLite in WAL mode;
- Server-Sent Events;
- persistent history;
- metric sampling;
- agent-state ingestion;
- authenticated approve/deny operations; and
- static frontend serving.

### Frontend

- React 19;
- live host and fleet status;
- metric panels;
- activity timeline;
- pending-action controls;
- summary cards; and
- a production Vite build.

Critical safety invariant:

> The dashboard never directly modifies the agent state file. Approval and denial flow through the tested AgentPulse CLI, safety gate, and verify-or-escalate loop.

Mutating endpoints fail closed when their token is absent.

The dashboard is implemented, but its long-term role must be reconciled with the newer Cloudflare control-plane architecture.

## 10. Hosted dashboard and federation — PARTIAL

A Fly.io-oriented hosted path was implemented with:

- a Dockerized dashboard;
- persistent Fly storage;
- remote heartbeat ingestion;
- hosted fleet state;
- HTTP Basic protection for reads;
- separate ingest authentication;
- a public health endpoint; and
- SSE-based live updates.

Remote remediation is intentionally disabled because the hosted container has no safe access to a customer's local AgentPulse CLI.

This Fly/SQLite path overlaps with the Cloudflare Worker/D1 control plane. One hosted architecture must become authoritative before release.

## 11. Billing and commercial foundation — PARTIAL

Commercial groundwork includes:

| Plan | Price | Intended server allowance |
|---|---:|---:|
| Starter | $29/month | 1 |
| Pro | $99/month | 5 |
| Business | $299/month | Small fleet / beta ceiling |

Implemented or drafted work includes:

- pricing and checkout buttons;
- Stripe checkout integration in the earlier hosted path;
- signup funnel;
- paid-beta positioning;
- customer guarantee;
- Privacy Policy;
- Terms of Service;
- proprietary commercial licensing;
- billing portal work in the Fly dashboard;
- subscription synchronization and webhook scaffolding;
- plan-specific server limits; and
- Stripe setup documentation.

The complete Cloudflare purchase-to-entitlement lifecycle is not finished.

## 12. Marketing site — SHIPPED

The public site includes:

- homepage;
- features page;
- installation guide;
- signup page;
- pricing page;
- blog listing;
- operational blog posts;
- a Datadog migration campaign;
- competitor comparison pages for Datadog, Grafana, Netdata, Better Stack, New Relic, and Uptime Kuma;
- public health files;
- SEO configuration;
- GitHub Pages deployment;
- support links; and
- legal links.

Core positioning:

> Monitoring tells you something broke. AgentPulse runs the first safe fix, verifies it, and escalates if it did not work.

Public copy has received multiple truth-alignment passes to distinguish shipped behavior from roadmap claims.

## 13. Reliability and deployment experiments

### Public reliability work — SHIPPED/PARTIAL

Added:

- public health endpoints;
- a k6 load-test definition;
- static health-check files;
- Docker build support;
- deployment documentation; and
- CI/CD work.

### AWS Fargate/Terraform path — ABANDONED

An AWS deployment path was explored using:

- ECS/Fargate;
- ECR;
- ACM;
- Cloudflare DNS; and
- GitHub OIDC.

It encountered IAM/OIDC and provider friction and was subsequently removed in favor of alternative hosting. It is not a shipped deployment path.

## 14. Cloudflare paid-pilot control plane — PARTIAL

A multi-tenant Cloudflare Worker and D1 architecture is under development.

Implemented or substantially built:

- tenant-scoped D1 schema;
- hashed account credentials;
- short-lived one-time enrollment tokens;
- per-agent credentials;
- agent enrollment;
- authenticated heartbeats;
- fleet API;
- remote policy retrieval;
- local policy-ceiling enforcement;
- tenant-isolation contracts;
- idempotency structures;
- workerd tests;
- generated Worker runtime types;
- staging D1 binding;
- a dependency-free Python control-plane client;
- strict mode-0600 credential storage; and
- enrollment-token CLI contracts.

Intended trust chain:

```text
Stripe customer
  → account credential
  → one-time enrollment token
  → per-agent credential
  → heartbeat and policy APIs
```

The cloud policy is monotonic-safe: it may narrow local authority but cannot promote a locally configured host from `alert` or `ask` to `auto`.

## 15. Paid-pilot productization gaps — BLOCKED/PARTIAL

A deep audit found the enrollment, heartbeat, policy, and fleet core credible, but the complete commercial lifecycle remains unfinished.

Ranked gaps:

1. Complete Stripe Checkout Session creation using exact allowlisted Price IDs.
2. Implement the complete signed and idempotent webhook lifecycle.
3. Implement verified Checkout-to-account onboarding claim.
4. Re-fetch and validate customer and subscription state before entitlement issuance.
5. Implement the customer billing portal path.
6. Finish agent loop and enrollment CLI integration.
7. Produce versioned agent release artifacts with SHA-256 verification.
8. Document retention, deletion, backup, and incident operations.
9. Complete test-mode checkout-to-heartbeat staging verification.
10. Reconcile Fly/SQLite and Cloudflare/D1 into one authoritative hosted architecture.

Implementation subagents were dispatched for portions of this scope, but two terminated with HTTP 402 before completing the assignments. Their assigned work must not be counted as completed.

## 16. Current repository state — RECONCILED, COMMITTED BY USER DIRECTION

Content reconciliation is complete and the merge was authorized for commit before executable verification could run.

Current facts:

- Branch: `productization/cloudflare-paid-pilot`
- Pre-merge HEAD: `6381565`
- All 15 conflicted paths were resolved as a semantic union.
- No unmerged index entries remain.
- No Git conflict markers remain outside dependency artifacts.
- Incoming Linux/macOS safety behavior, backend check-ins, launchd support, docs, and CI were preserved.
- Paid-pilot control-plane configuration, strict mode-0600 credentials, enrollment CLI, bounded heartbeat delivery, Worker tests, and cloud policy ceilings were preserved.
- Legacy `dashboard/frontend/node_modules` content was removed from Git tracking and `node_modules/` is now ignored; lockfiles remain authoritative.
- Static Python compilation and JSON validation passed on the changed files.
- `git diff --cached --check` passed.

The full executable verification matrix has not run. Project policy requires code execution through Novita, and two sandbox attempts failed before startup with `BALANCE_NOT_ENOUGH`. This commit must not be interpreted as a verified green baseline; executable verification remains the next release gate.

## 17. Release readiness

### Ready or substantially ready

- Core single-host monitoring
- Conservative policy model
- Approval-gated remediation
- Disk-cleanup safety constraints
- Service allowlisting
- Verify-or-escalate loop
- Persistent state and audit history
- Statistical baselines
- Linux and macOS daemon paths
- Local backend and dashboard foundations
- Agent enrollment/control-plane client foundation
- Public product and legal site

### Not ready

- Clean reconciled branch
- Current green verification suite
- Complete Cloudflare Stripe lifecycle
- Self-service onboarding claim
- Billing portal through the authoritative control plane
- Versioned and checksum-verified releases
- End-to-end staging commercial flow
- Final deployment architecture decision
- Production activation and launch handoff

## 18. Ranked path to release

### Phase 1 — Reconcile — COMPLETE

1. All merge conflicts were resolved semantically.
2. Incoming safety, macOS, backend, check-in, documentation, and CI behavior was preserved.
3. Paid-pilot Worker/D1, enrollment, policy-ceiling, and dashboard work was preserved.
4. Tracked dependency artifacts were removed; source and lockfiles remain.
5. No conflict markers or unmerged index entries remain.

### Phase 2 — Verify the merged baseline — BLOCKED ON SANDBOX CREDITS

1. Restore Novita sandbox capacity.
2. Run the agent safety suite.
3. Run backend tests.
4. Run dashboard backend checks.
5. Run dashboard frontend type-check and build.
6. Run Worker type-check, generated-bindings check, and workerd tests.
7. Review dependency and secret exposure risks.
8. Fix every failure before concluding the merge or adding product scope.

### Phase 3 — Complete paid-pilot lifecycle

1. Implement Stripe Checkout.
2. Complete signed, replay-resistant, idempotent webhooks.
3. Implement one-time onboarding claim.
4. Implement billing portal access.
5. Enforce subscription status and plan limits at every protected boundary.
6. Finish agent enrollment and heartbeat wiring.
7. Add versioned, checksum-verified release installation.
8. Add retention, deletion, backup, and recovery documentation.

### Phase 4 — Staging proof

Verify the full test-mode path:

```text
Checkout
  → signed webhook
  → onboarding claim
  → account credential
  → enrollment token
  → agent enrollment
  → heartbeat
  → fleet visibility
  → remote policy narrowed by local ceiling
  → failed-payment denial
  → billing portal
```

Also verify:

- two-tenant isolation;
- token replay rejection;
- idempotent heartbeat ingestion;
- service degradation behavior;
- backup and restore; and
- credential revocation.

### Phase 5 — Release

1. Review the final diff and secret hygiene.
2. Create coherent release commits.
3. Generate and verify release checksums.
4. Deploy the chosen hosted architecture.
5. Re-run production smoke checks.
6. Activate live billing only after restricted keys, exact Price IDs, webhook configuration, portal configuration, and safe checkout are verified.

## Bottom line

AgentPulse is no longer a prototype. Its core agent, safety model, operator workflow, statistical baselines, backend, dashboard, and commercial foundation are real.

It is not yet a finished paid SaaS product. The critical path is disciplined closure rather than more feature expansion:

```text
Restore Novita sandbox capacity
→ run and fix the full verification matrix
→ conclude the merge
→ complete Stripe and onboarding
→ prove the full staging lifecycle
→ choose one hosted architecture
→ release
```
