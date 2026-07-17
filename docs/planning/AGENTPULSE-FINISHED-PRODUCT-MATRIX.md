# AgentPulse Finished-Product Matrix and Repository Reconciliation

**Assessment timestamp:** 2026-07-16T22:51:17-04:00
**Canonical repository:** the GitHub repository containing this document
**Recommended source of truth:** GitHub `master`; implementation branches from that canonical revision
**Canonical domain:** `agentpulse.ca`

## Executive verdict

AgentPulse is no longer two equivalent copies that merely need a pull or push. It is a set of divergent historical lines:

1. GitHub's default `master` is the canonical product authority; the assessed baseline is `9f68e15`.
2. Phase 0 implementation is isolated on `chore/phase-0-repository-convergence`; it contains the reviewed security policy, truth-aligned documentation, and these planning documents pending GitHub review.
3. The legacy `main` line trails the consolidated architecture by 31 commits and is not the product authority; its remaining distinct changes target retired architecture or stale copy.
4. Superseded FastAPI-backend source is subject to the historical-retention gate. That backend was deliberately retired from `master` and must not return to active product source.
5. Open PR #19 proposes a Fly.io/FastAPI deployment against `main`. Merging it would restore a competing backend and violate the consolidated Worker/D1 architecture.

The correct synchronization strategy is therefore to preserve `master`, review the scoped Phase 0 workflow and documentation changes, archive rather than merge obsolete lines, and close or redirect stale GitHub work.

## Evidence and status legend

| Mark | Meaning |
|---|---|
| ✅ | Complete now, supported by current code plus a fresh local test/build or live endpoint probe |
| 🟡 | Partially implemented, beta/manual, stale documentation, or missing an end-to-end proof |
| ⬜ | Required for the finished product but not implemented or not deployed |
| 🗃️ | Superseded; preserve in the archive, not the active product |

A green check means the item is complete within the stated boundary. File presence or a prose claim alone does not earn a check.

## Repository authority and disposition

| Surface | Evidence-backed state | Decision |
|---|---|---|
| Canonical branch | GitHub default `master` at assessed baseline `9f68e15` | Retain as the only active product authority |
| Phase 0 candidate | Master-targeted branch contains security/release gating, planning, and truth-alignment changes | Review through a PR and require green checks before merge |
| Legacy `main` line | Diverges from and materially trails `master`; remaining changes target retired architecture or stale copy | Freeze and archive; do not merge wholesale into `master` |
| Productization/consolidation history | Useful commits are already ancestors of `master`; superseded runtime variants are archived | Remove stale refs only after owner approval and another archive verification |
| PR #17 | Targets legacy `main` and has no active implementation need | Close or supersede with a master-targeted cleanup only if still needed |
| PR #19 | Adds FastAPI/Fly.io authority that conflicts with Worker/D1; useful domain history is already represented | Close without merge and record architectural supersession |
| Issues #13 and #16 | Enrollment, heartbeat, policy, and fleet routes exist in canonical contracts/Worker tests | Close with evidence links or rewrite as narrower production gaps |
| Historical evidence | Operational retention evidence is intentionally not published | Block cleanup until the owner privately confirms the retention gate |

## What AgentPulse will be when finished

### Product definition

AgentPulse will be a self-serve, local-first server-remediation product for founders and small teams running approximately 1–10 Linux/macOS hosts. A dependency-light local agent observes known incident classes, proposes only allowlisted remediations, simulates and policy-gates them, executes locally, verifies the result, and escalates instead of looping when a fix fails. A single Cloudflare Worker/D1 control plane handles tenant identity, billing entitlement, enrollment, bounded heartbeats, policy narrowing, and fleet evidence. A secure React console gives each tenant visibility into only its own hosts, incidents, subscription, enrollment, and account lifecycle.

It will not be a generic observability stack, arbitrary remote shell, second hosted backend, or autonomous LLM with unconstrained production authority.

### Permanent product invariant

```text
Observe → Reason → Simulate → Gate → Act → Verify → Record or Escalate
```

The local host remains authoritative. Cloud policy may reduce but never increase local authority. Every side effect is allowlisted, attributable, bounded, idempotent where applicable, and followed by a verification result. Control-plane outage does not stop local monitoring/remediation; evidence is spooled and replayed later.

### Finished system chart

```text
┌──────────────────────────── Customer / operator ─────────────────────────────┐
│ agentpulse.ca          app.agentpulse.ca             Stripe Customer Portal │
│ product + docs         secure account session        subscription lifecycle  │
└──────────┬──────────────────────┬─────────────────────────────┬───────────────┘
           │                      │                             │ signed events
           ▼                      ▼                             ▼
┌──────────────────────── Cloudflare trust boundary ───────────────────────────┐
│ Static public site + React console                                            │
│                   │ secure HttpOnly session                                   │
│                   ▼                                                           │
│ AgentPulse Worker API ── auth / tenant scope / billing / enrollment / policy │
│                   │                                                           │
│                   ▼                                                           │
│ Cloudflare D1: tenants, subscriptions, sessions, agents, heartbeats,          │
│ incidents, policies, idempotency records, audit metadata, retention state     │
└──────────────────────────────┬────────────────────────────────────────────────┘
                               │ outbound TLS only
               ┌───────────────┼────────────────────┐
               ▼               ▼                    ▼
        ┌────────────┐   ┌────────────┐      ┌────────────┐
        │ Host agent │   │ Host agent │ ...  │ Host agent │
        │ local state│   │ local state│      │ local state│
        │ policy cap │   │ policy cap │      │ policy cap │
        │ allowlists │   │ allowlists │      │ allowlists │
        │ verify loop│   │ verify loop│      │ verify loop│
        └────────────┘   └────────────┘      └────────────┘

No inbound remote shell. No arbitrary command channel. No second API authority.
```

## Finished-product capability matrix

### A. Local agent and remediation engine

| Finished capability | Completion criterion | What exists now | Status |
|---|---|---|---|
| Dependency-light Python agent | Runs on Python 3.10+ without runtime dependencies | Agent package and self-contained runner; fresh run: 170 passed | ✅ |
| Linux host monitoring | Reads disk, memory/process, and systemd service state | Implemented checks and tests | ✅ |
| macOS host monitoring | Reads supported host state and launchd service state | Launchd-aware implementation and tests/assets exist | ✅ |
| Disk-pressure remediation | Deletes only old files under explicitly allowed paths; refuses dangerous paths and symlink escapes | Safety predicates, remediation implementation, fuzz/safety tests | ✅ |
| Service restart remediation | Restarts only configured systemd/launchd services and verifies active state | Implemented and covered by agent suite | ✅ |
| Runaway-process handling | Identifies offender; never automatically kills in v1; requires human approval | Process policy is clamped to ask-first | ✅ |
| Alert-only default | Fresh install cannot mutate hosts until locally promoted | Config/schema and decision loop enforce conservative modes | ✅ |
| Four policy modes | `off < alert < ask < auto` with per-check behavior | Agent policy implementation and tests | ✅ |
| Simulate before act | Every mutation has a dry-run/simulation result | Decision-loop implementation and tests | ✅ |
| Fail-closed safety gate | Unknown/malformed actions cannot execute | Deny/policy/fuzz tests | ✅ |
| Post-action verification | Original condition is re-measured after action | Decision-loop verification implemented | ✅ |
| No autonomous repair spiral | Failed verification escalates once rather than retrying destructively | Decision-loop/retry tests | ✅ |
| Local authority ceiling | Cloud cannot widen configured local permission | Agent + Worker narrowing logic and trust tests | ✅ |
| Offline operation | Monitoring/remediation continues without cloud | Local-first runner/state model implemented | ✅ |
| Evidence spool and replay | Failed outbound delivery is persisted, bounded, locked, retried, and deduplicated | Spool/retry/locking tests pass | ✅ |
| Secret redaction | Credentials and sensitive fields are excluded from logs/evidence | Redaction tests pass | ✅ |
| Local audit trail | Reason, gate, action, verification, and outcome are attributable | Audit implementation/tests pass | ✅ |
| Production-grade install artifact | Versioned, checksummed package installs from an immutable release; no unpinned branch downloads | Wheel builds with package/assets/console script; installers require version + SHA-256 and no longer fetch raw branch files; clean-host proof still pending | 🟡 |
| Safe upgrade and rollback | Signed/checksummed upgrade path preserves config/state and can roll back | upgrade/rollback scripts implemented with checksum + config/state preservation; clean-host proof still pending | 🟡 |
| Real host acceptance matrix | Clean Ubuntu/Debian/RHEL-compatible Linux and macOS installs pass destructive-safe end-to-end tests | Unit/safety coverage is strong; clean-host lifecycle proof is missing | 🟡 |

### B. Cloud control plane and data

| Finished capability | Completion criterion | What exists now | Status |
|---|---|---|---|
| Single hosted authority | Worker/D1 is the only active hosted backend | Consolidated master removed FastAPI/Fly/Docker alternatives | ✅ |
| Health endpoint | Reports service, version, and environment | Local tests pass; staging endpoint returned HTTP 200 | ✅ |
| Tenant-safe account credentials | Only hashed credentials stored; tenant derived server-side | Implemented in Worker/D1 and tested | ✅ |
| One-time enrollment | Expiring token is atomically consumed; agent credential returned once | Implemented and tested | ✅ |
| Per-agent authentication | Unique hashed agent credential gates heartbeat/policy routes | Implemented and tested | ✅ |
| Plan server limits | Enrollment refuses agents above subscription limit | D1/Worker path implemented and tested | ✅ |
| Bounded heartbeat ingestion | 64 KiB body cap, bounded incidents/strings, stable validation errors | Implemented and tested | ✅ |
| Heartbeat idempotency | Duplicate idempotency key is acknowledged without duplicate effects | Implemented and tested | ✅ |
| Incident materialization | Heartbeat incidents upsert by tenant/agent/fingerprint | Implemented; 14 Worker tests pass | ✅ |
| Tenant-scoped fleet read | Account can read only its own hosts/incidents | Implemented and tested | ✅ |
| Monotonic policy narrowing | Hosted policy cannot exceed agent local ceiling | Implemented and tested | ✅ |
| Stripe signature/replay protection | Raw-body HMAC, timestamp window, event ID idempotency | Signature and event-recording code exists | ✅ |
| Complete subscription ingestion | Checkout, create/update/delete, invoice paid/failed all update one deterministic entitlement model | Current handler materially acts only on `invoice.payment_failed` | 🟡 |
| Self-serve checkout creation | API creates checkout only for allowlisted Price IDs and trusted return URLs | Described in design but route absent from active OpenAPI/Worker | ⬜ |
| Checkout-to-account claim | Completed checkout can be claimed once for a secure account | Described in design but route absent | ⬜ |
| Billing portal | Authenticated tenant can open Stripe Customer Portal | Described in design but route absent | ⬜ |
| Credential rotation/revocation | Account and agent credentials can be revoked/rotated without DB surgery | Schema has revocation fields; complete API/UX and proof are absent | 🟡 |
| Session authentication | Browser uses short-lived secure HttpOnly/SameSite session rather than a bearer key in JavaScript storage | Not implemented | ⬜ |
| Retention/deletion lifecycle | Documented and tested tenant deletion, evidence retention, and privacy-request procedure | Not implemented/documented as an executable runbook | ⬜ |
| Production D1 | Real ID, migrations, backups/recovery, and rollback are verified | Production ID is `REPLACE_PRODUCTION_D1_ID` | ⬜ |
| Staging control plane | D1 migration and Worker custom-domain health work | `staging-api.agentpulse.ca/health` returned HTTP 200 | ✅ |
| Production control plane | `api.agentpulse.ca` resolves, health passes, and rollback evidence exists | Domain did not resolve during probe | ⬜ |

### C. Customer console

| Finished capability | Completion criterion | What exists now | Status |
|---|---|---|---|
| One React console | No duplicate dashboard or second API client | Single `dashboard/` retained | ✅ |
| Fleet inventory | Authenticated tenant sees host state and last-seen data | Pages/client exist; production build passes | ✅ |
| Server detail | Host-specific state and incidents render from fleet contract | Route/page exist; production build passes | ✅ |
| Incident list/detail | Recent incidents can be inspected by status/severity/details | Routes/pages exist; production build passes | ✅ |
| Read-only safety boundary | Console cannot dispatch arbitrary host commands | No command/remediation endpoint exists | ✅ |
| Production browser authentication | Login/session/logout are CSRF-safe and credentials are inaccessible to JavaScript | Current beta credential is held in `sessionStorage` | ⬜ |
| Self-serve enrollment UX | Customer creates one-time token and receives exact install command | No finished secure session/enrollment screen proof | ⬜ |
| Subscription/account UX | Plan, status, billing portal, cancellation, and failed-payment state are visible | Not implemented | ⬜ |
| Accessible responsive UX | Keyboard, screen-reader, mobile, loading/error/empty states pass acceptance tests | Build passes; no browser/accessibility test suite exists | 🟡 |
| Staging deployment | `staging-app.agentpulse.ca` resolves and browser E2E passes against staging API | Domain did not resolve during probe | ⬜ |
| Production deployment | `app.agentpulse.ca` resolves and E2E passes | Domain did not resolve during probe | ⬜ |

### D. Website, commercial lifecycle, and support

| Finished capability | Completion criterion | What exists now | Status |
|---|---|---|---|
| Canonical public brand/domain | Public copy, metadata, install links, and email use `agentpulse.ca` | Master source is aligned to `agentpulse.ca` | ✅ |
| Public website | `agentpulse.ca` resolves and serves current truthful content | Source and Pages workflow exist; apex did not resolve during probe | 🟡 |
| Truth-aligned product copy | Shipped vs roadmap capabilities and safety limits are explicit | Phase 0 audit removes unsupported deployment, packaging, setup-time, console, and unlimited-capacity claims | ✅ |
| CAD beta pricing | Starter C$29, Pro C$99, Business C$299 are stated consistently as founding prices | Public CTAs are founding reserves; live Stripe buy buttons removed until fleet/provisioning is real | 🟡 |
| Automated entitlement | Successful payment creates/activates the right tenant/limit without manual DB work | Paid beta still requires manual confirmation; no public charge path for undeliverable fleet | ⬜ |
| Failed-payment enforcement | Failed/past-due account loses enrollment/heartbeat rights safely | Worker denies inactive status; only partial webhook lifecycle exists | 🟡 |
| Cancellation/refund/guarantee operations | Customer and operator paths are documented and tested | Email/manual beta policy only | 🟡 |
| Support email | `support@agentpulse.ca` receives and can be operationally managed | Apex MX added (Cloudflare Email Routing hosts); owner must enable routing rule + destination mailbox | 🟡 |
| Security contact | `security@agentpulse.ca` and disclosure process work | Documentation exists; live routing was not verified | 🟡 |
| Legal/privacy alignment | Terms/privacy match actual data, billing, retention, and subprocessors | Documents exist; must be reviewed after final data lifecycle | 🟡 |

### E. Contracts, quality, security, release, and operations

| Finished capability | Completion criterion | What exists now | Status |
|---|---|---|---|
| Canonical API contract | Every active endpoint is in OpenAPI and Worker tests; no phantom routes | 7 paths, 19 refs, 9 schemas, 3 fixtures validate | ✅ |
| Agent test suite | Safety/behavior suite passes on supported Python versions | Fresh local result: 170 passed; GitHub Tests succeeded at master head | ✅ |
| Worker tests/type safety | Workerd/D1 tests, TypeScript, generated bindings all pass | Fresh: 14 tests; typecheck and bindings pass | ✅ |
| Dashboard build | TypeScript and Vite production build pass | Fresh build succeeded | ✅ |
| Dashboard behavioral E2E | Browser tests cover auth, fleet, incidents, failure/empty states | No browser test suite | ⬜ |
| Security dependency audits | Python invariant and npm high-severity audits pass | Latest master dependency-audit job passed | ✅ |
| Repository hardening | Shell syntax, no tracked dependencies, credential-pattern gate | Latest master hardening job passed | ✅ |
| Secret scanning | GitHub Security workflow is green with an approved scanning policy and directly gates releases | Root cause reproduced; verified-only scan passed with zero verified secrets; release verification now includes the same pinned scan; GitHub rerun pending | 🟡 |
| CI branch authority | Required checks target only canonical branch and PRs into it | Master workflows exist, but stale main PRs/branches remain | 🟡 |
| Versioned agent release | Wheel/sdist contain the runnable agent; checksums and release notes are published | Wheel/sdist packaging + SHA256SUMS release job implemented; prerelease tag and clean-host proof still pending | 🟡 |
| Reproducible deployment | Staging/production migrations and deploys run through protected environments | Worker deploy job exists; production bindings and proof missing | 🟡 |
| Rollback and disaster recovery | D1 backup/restore, Worker rollback, agent rollback, and incident runbooks are exercised | Not proven | ⬜ |
| Observability without credential leakage | Structured Worker/agent health, deploy markers, and alerts exist | Worker observability enabled; complete operational alerting absent | 🟡 |
| Two-tenant isolation proof | Automated E2E attempts cross-tenant access and fails | Unit/Worker isolation paths exist; staging E2E release gate remains | 🟡 |
| Full commercial lifecycle proof | Checkout → claim/session → enrollment → heartbeat → console → failed-payment denial → recovery passes | Not yet possible end to end | ⬜ |
| Historical retention gate | Owner privately confirms recoverability, integrity, durability, and source disposition before deletion | Gate 0 approval pending; operational evidence is intentionally not public | 🟡 |

## Current verification receipts

| Check | Fresh result |
|---|---|
| Agent suite | `170 passed, 0 failed` |
| Agent lint | PASS: project Ruff 0.15.21 reports all checks passed |
| Agent config validation | PASS: example and local configurations validate against Draft 7 schema with format checks |
| Shared contracts | PASS: 7 paths, 19 local refs, 9 schemas, 3 fixtures |
| Worker tests | PASS: 14 tests |
| Worker TypeScript/bindings | PASS |
| Dashboard production build | PASS: 1,531 modules transformed |
| Master GitHub Tests | SUCCESS at `9f68e15` |
| Master GitHub Pages | SUCCESS at `9f68e15`, though canonical DNS did not resolve during the probe |
| Master GitHub Security | FAILURE only in Secret scanning; dependency audit and hardening passed |
| Staging API | HTTP 200 with expected AgentPulse health JSON |
| Public/production domains | `agentpulse.ca`, `app.agentpulse.ca`, and `api.agentpulse.ca` did not resolve during the probe |


## Authoritative retain/migrate/archive decisions

| Responsibility | Authority | Decision |
|---|---|---|
| Local host behavior | `agent/` | Retain and harden |
| Hosted API/control plane | `control-plane/` Worker + D1 | Retain; implement missing self-service lifecycle here |
| Web console | `dashboard/` React app | Retain one console; add secure sessions and self-service flows |
| API/schema ownership | `packages/contracts/` | Retain as contract source of truth |
| Public site/docs | `docs/` | Retain; keep claims synchronized with release gates |
| Generic FastAPI backend | Preserved historical evidence only | Do not restore to active product |
| Fly.io deployment | PR #19 historical evidence only | Do not merge; Worker is the hosted authority |
| Old dashboard services | Archive only | Do not restore |
| AWS/Fargate/Terraform path | Archive/history only | Do not restore |
| Prometheus/Grafana stack | Archive only | Do not restore for v1 |
| LLM-driven host command authority | Nowhere | Explicitly out of scope |

## Definition of finished

AgentPulse is finished for public self-serve v1 only when all of the following are true:

1. One canonical `master` branch is clean locally and on GitHub; stale PRs/issues/branches are reconciled.
2. A customer can pay through an allowlisted checkout, claim exactly one account, and receive a secure browser session.
3. The customer can create a one-time enrollment token and install a versioned, checksummed agent on a clean supported host.
4. The host starts alert-only, survives cloud outage, submits idempotent evidence, receives only policy that is no broader than its local ceiling, and performs only allowlisted verified remediation.
5. The customer sees only their own fleet/incidents, can manage billing and credentials, and cannot send arbitrary host commands.
6. Failed payment, duplicate webhook, token replay, credential revocation, tenant-isolation attack, restart recovery, upgrade, rollback, and deletion/retention paths are tested.
7. `agentpulse.ca`, `app.agentpulse.ca`, and `api.agentpulse.ca` resolve in production; staging equivalents pass before promotion.
8. CI, security scans, release packaging, migrations, deploy, browser E2E, smoke tests, and rollback gates are green at the exact release commit.
9. The first real paid-customer lifecycle is completed with evidence and no manual database edits.

The separate execution plan in `docs/planning/AGENTPULSE-COMPLETION-PLAN.md` converts these gaps into ordered Hermes work blocks and owner-only gates.
