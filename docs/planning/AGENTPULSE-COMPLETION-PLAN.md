# AgentPulse Public v1 Completion Plan

> **For Hermes:** Execute this plan task-by-task. Use isolated implementation branches, test-driven development for behavior changes, and two-stage review (spec compliance, then code/security quality) before each integration.

**Goal:** Converge AgentPulse on one clean `master` repository and deliver a verified, self-serve public v1 from payment through safe host remediation and account lifecycle.

**Architecture:** Preserve the local-first Python agent, one Cloudflare Worker/D1 control plane, one React console, shared OpenAPI/JSON Schema contracts, and the static public site. Add the missing billing, session, enrollment, packaging, deployment, lifecycle, and end-to-end proof without restoring the retired FastAPI/Fly.io backend or any remote-shell capability.

**Tech stack:** Python 3.10–3.13, TypeScript, Cloudflare Workers + D1, React + Vite, Stripe, GitHub Actions, OpenAPI 3.1, JSON Schema.

**Companion state matrix:** `docs/planning/AGENTPULSE-FINISHED-PRODUCT-MATRIX.md`

---

## 1. Operating model: Hermes works until only Owner can proceed

This plan deliberately minimizes Owner's interruptions.

### Hermes work block

For every phase, Hermes will:

1. Inspect the current revision, uncommitted changes, open PRs/issues, and live service state.
2. Create or update tests first where behavior changes.
3. Implement all code, contracts, migrations, workflows, docs, and run-books that do not require account-owner approval or secret entry.
4. Run every local gate that is possible.
5. Open/push a reviewable branch or PR when authorized.
6. Continue through all dependent tasks until the next item genuinely requires Owner.
7. Send one concise hand-off containing:
   - what was completed;
   - evidence and links;
   - exactly one numbered Owner action block;
   - exact non-secret values/commands to use;
   - the success signal Hermes needs to continue.

### Owner gate

Owner is involved only for decisions or actions Hermes cannot safely perform:

- approve irreversible repository cleanup or production promotion;
- choose/confirm commercial plan definitions;
- enter secrets in Stripe, Cloudflare, GitHub, or DNS interfaces without exposing them in chat;
- authorize a real charge/refund/cancellation;
- provide or approve a real clean host for installation;
- make the final public go-live decision.

Owner should never paste passwords, API keys, webhook secrets, recovery codes, or customer personal data into chat. Hermes will verify secret *names/presence and resulting behavior*, not secret values.

### Resume protocol

Owner replies with the gate's stated success signal, such as `Gate 2 complete`. Hermes then verifies the external result and resumes at the next unchecked step without repeating settled questions.

---

## 2. Global rules and release invariants

1. Canonical branch: GitHub `master`; implementation work begins from a clean checkout of that revision.
2. Active source contains only supported or near-finished components.
3. Historical FastAPI, Fly.io, duplicate dashboards, AWS infrastructure, and experimental observability remain outside active source under the historical-retention policy.
4. Cloud policy can narrow but never widen local authority.
5. No arbitrary command endpoint, inbound host control, or browser-to-host command path.
6. Credentials are scoped by class: browser session, account identity, enrollment token, agent credential, Stripe webhook secret, deploy credential.
7. Tenant identity is always derived server-side.
8. API changes begin in `packages/contracts/`, are tested in `control-plane/test/`, then implemented and consumed.
9. Database changes occur only through numbered D1 migrations.
10. Every release claim is tied to fresh CI/live evidence at the exact commit.

---

# Tier 0 — Repository convergence and evidence preservation

## Phase 0: Establish one clean authority

**Outcome:** `master` is the only active product line; no local work is lost; GitHub tracking reflects the consolidated architecture.

### Hermes work block 0A — verify and prepare synchronization

Set the candidate repository path without committing it:

```bash
export AGENTPULSE_REPO="$(git rev-parse --show-toplevel)"
```

1. Before cleanup, ask the Owner to review confidential retention evidence against `ARCHIVES.md`. Do not publish confidential operational evidence. A failed or missing owner confirmation blocks deletion.
2. Record the candidate status without switching branches:
   ```bash
   git -C "$AGENTPULSE_REPO" status --short --branch
   ```
3. Review `.github/workflows/security.yml` and determine why TruffleHog failed before accepting `--only-verified`:
   - inspect job annotations/log artifacts;
   - distinguish a real secret, deleted-history finding, and scanner invocation problem;
   - rotate/revoke any real secret before suppressing a finding;
   - prefer event-aware scanning of the correct commit range over globally ignoring unverified findings.
4. Correct stale factual documentation discovered during assessment:
   - `agent/README.md` test-count claim;
   - any current docs that claim production domains or self-serve installation are live;
   - status date/verification receipts only after fresh verification.
5. Commit only canonical changes on a new branch from `master`:
   - `.github/workflows/security.yml` after security review;
   - `docs/planning/AGENTPULSE-FINISHED-PRODUCT-MATRIX.md`;
   - `docs/planning/AGENTPULSE-COMPLETION-PLAN.md`;
   - any explicitly reviewed truth-alignment edits.
6. Run the local gates:
   ```bash
   cd "$AGENTPULSE_REPO"
   python3 agent/tools/run_tests.py
   python3 scripts/validate-contracts.py
   cd control-plane && npm test && npm run typecheck && npm run types:check
   cd ../dashboard && npm run build
   ```
7. Install/run Ruff in an isolated project environment only if absent; do not modify the system Python:
   ```bash
   cd "$AGENTPULSE_REPO"
   .venv/bin/python -m pip install ruff  # only if this project venv exists and ruff is absent
   .venv/bin/ruff check agent/
   ```
8. Push a master-targeted PR and wait for Tests, Contract Integration, Security, and Pages checks.

### Owner Gate 0 — repository cleanup approval

Hermes will present:

- the synchronization PR;
- the root cause and chosen fix for secret scanning;
- a list of stale PRs/issues/branches proposed for closure/deletion;
- the private historical-retention gate result, without confidential operational details.

Owner chooses one response:

- approve cleanup exactly as proposed; or
- name any branch/PR that must remain active.

No repository ref, source copy, PR, or issue is deleted/closed before this approval.

### Hermes work block 0B — execute approved convergence

After approval:

1. Merge the synchronization PR only with required checks green.
2. Update the candidate's remote refs and default pointer:
   ```bash
   git -C "$AGENTPULSE_REPO" fetch origin --prune
   git -C "$AGENTPULSE_REPO" remote set-head origin -a
   ```
3. Fast-forward only approved clean clones to `origin/master`; preserve all historical source evidence until separately authorized.
4. Close PR #19 as architecturally superseded; retain its useful domain history in the archive/issue comment, not its FastAPI/Fly code.
5. Close or retarget PR #17.
6. Close issues #13 and #16 with links to:
   - `packages/contracts/openapi.yaml`;
   - `control-plane/src/index.ts`;
   - `control-plane/test/control-plane.test.ts`.
7. Delete approved superseded refs only after the Owner reconfirms the private historical-retention gate.
8. Preserve historical source evidence until Owner separately authorizes removal.
9. Verify:
   ```bash
   git ls-remote --symref origin HEAD
   git -C "$AGENTPULSE_REPO" status --short --branch
   gh pr list --state open
   gh issue list --state open
   gh run list --branch master --limit 10
   ```

**Tier 0 release gate:** clean canonical master, green CI/security, correct default pointers, no competing active implementation.

---

# Tier 1 — Make the existing beta installable and operable

## Phase 1: Versioned agent packaging, installation, upgrade, and rollback

**Outcome:** A customer can install a real immutable AgentPulse release on a clean host without downloading mutable files from `main`.

### Hermes work block 1A — package correctly

1. Add packaging tests that build a wheel and assert it contains:
   - `agentpulse` Python package;
   - systemd unit;
   - launchd plist;
   - example config or generated safe default;
   - license and version metadata.
2. Fix root `pyproject.toml`:
   - replace `packages = []` with the real package mapping under `agent/`;
   - define the `agentpulse` console script;
   - include required service/config assets;
   - ensure sdist/wheel scope excludes control-plane/dashboard source unless intentionally distributed.
3. Build in an isolated environment:
   ```bash
   python3 -m venv .venv-build
   .venv-build/bin/pip install build
   .venv-build/bin/python -m build
   .venv-build/bin/python -m zipfile -l dist/*.whl
   ```
4. Install the wheel into a fresh temporary venv and run:
   ```bash
   agentpulse --help
   agentpulse validate <safe-example-config>
   agentpulse run-once --dry-run <safe-example-config>
   ```
5. Add release checksum generation and verification to `.github/workflows/release.yml`.
6. Change `scripts/install-agent.sh` and published `docs/install.sh` to:
   - require/version a release;
   - download from an immutable GitHub release tag;
   - verify SHA-256 before installation;
   - avoid raw files from `main`;
   - write agent credentials with mode `0600`;
   - never embed an enrollment token in a world-readable process list or log.
7. Make enrollment atomic in the installer: exchange the one-time token, persist the returned agent credential securely, erase the enrollment token, validate config, then start the service.
8. Add `scripts/upgrade-agent.sh` and rollback behavior preserving config/state.
9. Update `scripts/smoke-test.sh` to validate:
   - version;
   - config schema, not only JSON shape;
   - secure ownership/modes;
   - service health;
   - control-plane health/check-in when configured.
10. Update docs:
   - `docs/install.md`;
   - `agent/README.md`;
   - `README.md`;
   - `SECURITY.md`;
   - a new `docs/runbooks/agent-release-rollback.md`.

### Hermes work block 1B — clean-host test automation

1. Add CI tests for wheel installation on Python 3.10–3.13.
2. Add safe container/systemd-compatible Linux installer tests where feasible.
3. Add macOS package/launchd rendering tests without requiring system mutation.
4. Test upgrade N→N+1 and rollback N+1→N with preserved config/state fixtures.
5. Publish a prerelease artifact only after all packaging tests pass.

### Owner Gate 1 — prerelease and real-host authorization

Owner supplies no credentials in chat. Owner only:

1. approves a version number (recommended first candidate: `v0.2.0-beta.1`); and
2. identifies one non-critical Linux VPS and, optionally, one macOS host on which Hermes may guide a real installation.

Hermes then provides one exact reviewed install command. Any `sudo` password is entered locally by Owner, never sent to Hermes.

### Hermes work block 1C — host acceptance

1. Guide/run prerelease install on the approved host.
2. Verify alert-only startup, file permissions, service state, dry-run, heartbeat spool, outage behavior, restart recovery, upgrade, rollback, and uninstall/reinstall.
3. Capture redacted evidence in `docs/runbooks/` or release evidence, never host secrets.
4. Fix all defects and repeat until acceptance passes.

**Status — 2026-07-20:** The published `v0.2.0-beta.1` artifact was rejected
after disposable Debian/systemd acceptance reproduced lifecycle defects. The
repaired source passed the broad and real-systemd lifecycle runners with a
checksummed, unpublished `0.2.0b2` fixture; both sandboxes were destroyed. See
`docs/runbooks/agentpulse-tier1-phase1c-evidence.md`. Public Tier 1 remains open
until the repaired source is published as a replacement immutable prerelease
and that exact artifact repeats the clean-host run.

**Tier 1 release gate:** immutable package + checksum; clean-host install/upgrade/rollback proof; no mutable branch downloads.

---

# Tier 2 — Complete the self-serve account and billing control plane

## Phase 2: Resolve commercial contract before coding irreversible billing behavior

**Outcome:** Pricing, plan limits, entitlement states, and customer lifecycle are one explicit contract.

### Hermes work block 2A — prepare the decision package

Hermes will derive and present a one-page decision table from current pricing and Stripe objects, without reading or storing secret values:

- Starter: C$29/month, 1 host;
- Pro: C$99/month, 5 hosts;
- Business: C$299/month, proposed explicit finite host limit for self-serve enforcement;
- trial behavior, if any;
- cancellation timing;
- failed-payment grace period or immediate fail-closed behavior;
- guarantee/refund operating rule;
- tax/customer-address requirements.

Hermes will recommend the simplest legally and technically coherent v1 defaults and identify what can remain manual.

### Owner Gate 2 — commercial decisions

Owner confirms:

1. final plan names, CAD prices, and numeric host limits;
2. whether checkout is fully public or invite/beta gated;
3. failed-payment/grace-period behavior;
4. whether the current 30-day guarantee wording remains.

One response settles all four; Hermes does not ask again unless implementation uncovers a contradiction.

## Phase 3: Stripe lifecycle, account claim, sessions, and portal

**Outcome:** Payment creates an entitlement; the customer securely claims and manages the account without manual database edits.

### Hermes work block 3A — contracts and migrations first

1. Extend `packages/contracts/openapi.yaml` with:
   - `POST /v1/billing/checkout`;
   - `POST /v1/onboarding/claim`;
   - `POST /v1/sessions` or a claim response that sets a session;
   - `DELETE /v1/session`;
   - `GET /v1/account`;
   - `POST /v1/billing/portal`;
   - credential/session revocation endpoints only where needed for v1.
2. Add/update JSON Schemas and fixtures under `packages/contracts/schemas/` and `packages/contracts/fixtures/`.
3. Write failing contract validation tests.
4. Add numbered D1 migration(s) under `control-plane/migrations/` for:
   - checkout claim nonce/state;
   - browser sessions with hashed token, expiry, revocation, and rotation metadata;
   - normalized plan/entitlement status;
   - webhook processing outcome/error fields;
   - retention timestamps where required.
5. Add migration replay/upgrade tests using `control-plane/test/apply-migrations.ts`.

### Hermes work block 3B — test-driven Worker implementation

For each route/event, repeat: failing test → implementation → focused test → full Worker suite.

1. Implement allowlisted Stripe Price ID mapping from environment bindings.
2. Create checkout sessions with trusted success/cancel URLs and a server-generated claim nonce.
3. Verify Checkout Session server-side during claim; allow exactly one successful claim.
4. Issue secure browser session cookies:
   - `HttpOnly`;
   - `Secure` outside local development;
   - `SameSite=Lax` or stricter;
   - narrow path/domain;
   - short expiry plus rotation/revocation;
   - CSRF defense for state-changing browser routes.
5. Process the full required Stripe set idempotently:
   - `checkout.session.completed`;
   - `customer.subscription.created`;
   - `customer.subscription.updated`;
   - `customer.subscription.deleted`;
   - `invoice.paid`;
   - `invoice.payment_failed`.
6. Re-read canonical Stripe state for claim/portal operations rather than trusting webhook payloads alone.
7. Enforce the confirmed entitlement state on enrollment and heartbeat without disabling safe local agent operation.
8. Implement Customer Portal creation.
9. Add stable error codes and never return raw Stripe errors/secrets.
10. Add tests for duplicate events, out-of-order events, replayed claim, expired session, CSRF, inactive subscription, plan limit, and log redaction.
11. Update `control-plane/ARCHITECTURE.md`, `ARCHITECTURE.md`, OpenAPI, and runbooks to match actual surviving routes.

### Hermes work block 3C — stage everything possible without production secrets

1. Create `.dev.vars.example` names only, never values.
2. Update `control-plane/wrangler.jsonc` with non-secret plan bindings and no production placeholders once real resource IDs are known.
3. Add GitHub environment/secrets documentation with exact secret names.
4. Add a staging lifecycle script that uses Stripe test mode and synthetic non-personal customer data.
5. Run all local Worker/contract tests.

### Owner Gate 3 — secret entry and Stripe/Cloudflare account actions

Hermes provides an exact checklist. Owner performs these in account consoles/CLI locally:

1. create/confirm Stripe test Products and recurring CAD Prices matching Gate 2;
2. configure test Customer Portal settings;
3. create the staging webhook endpoint and select exact event types;
4. enter secret values directly into Cloudflare/GitHub secret stores;
5. confirm the staging D1/database/environment bindings.

Owner returns only:

- `Gate 3 complete`;
- non-secret Price IDs, resource IDs, and endpoint URLs if Hermes cannot query them;
- no secret values.

### Hermes work block 3D — staging lifecycle proof

1. Deploy migrations and Worker to staging.
2. Execute Stripe test checkout → claim → session → portal → enrollment → heartbeat → fleet.
3. Test duplicate webhook, token replay, expired claim/session, failed payment denial, paid recovery, and two-tenant isolation.
4. Verify logs contain no credentials or customer-sensitive payloads.
5. Store redacted test evidence and exact deployment revision.
6. Fix/retest until every release gate passes.

**Tier 2 release gate:** complete test-mode commercial lifecycle with no manual DB edits and no browser bearer credential in JavaScript storage.

---

# Tier 3 — Finish and deploy the customer console

## Phase 4: Secure account, enrollment, fleet, incident, and billing UX

**Outcome:** A customer completes the normal lifecycle entirely through `app.agentpulse.ca`.

### Hermes work block 4A — replace beta credential connection

1. Write browser tests before changing behavior. Add an appropriate E2E stack to `dashboard/` (recommended: Playwright) and unit/component tests only where they add distinct value.
2. Remove production dependence on `dashboard/src/auth/credential.ts` and `sessionStorage` bearer keys.
3. Update `dashboard/src/api/client.ts` to use same-site secure cookies and CSRF tokens for state changes.
4. Add routes/pages for:
   - checkout return and account claim;
   - session/login recovery appropriate to v1;
   - account/subscription status;
   - create/copy one-time enrollment token;
   - exact versioned install command;
   - billing portal launch;
   - credential/session logout/revocation.
5. Preserve existing fleet/server/incident pages and read-only host boundary.
6. Implement explicit loading, empty, offline, expired-session, inactive-subscription, plan-limit, and API-error states.
7. Add keyboard navigation, semantic headings/tables, focus handling, contrast checks, and mobile layouts.
8. Update dashboard types from canonical OpenAPI or add a generation check so they cannot drift silently.

### Hermes work block 4B — deployment and E2E

1. Add a staging console deployment workflow targeting `staging-app.agentpulse.ca`.
2. Configure CORS/origin/session-cookie behavior to allow only declared app origins.
3. Run Playwright against staging for:
   - claim/session;
   - enrollment-token creation;
   - fleet and incident views;
   - inactive subscription;
   - logout/session expiry;
   - cross-tenant denial.
4. Add browser E2E as a protected production release gate.

### Owner Gate 4 — DNS/session-domain approval if account access is required

Hermes performs every DNS/API change available through authenticated tooling. If registrar/Cloudflare UI action is unavoidable, Owner receives exact record rows:

- host/name;
- type;
- target;
- proxy mode;
- TTL;
- verification command.

Owner applies only those rows and replies `Gate 4 complete`; Hermes then probes DNS, TLS, cookies, and E2E.

**Tier 3 release gate:** staging console resolves; browser E2E passes; no production bearer token in browser storage; no command-dispatch route.

---

# Tier 4 — Production infrastructure, operations, and safety proof

## Phase 5: Production D1, domains, deploy, rollback, and observability

**Outcome:** Production is reproducibly deployable and recoverable.

### Hermes work block 5A — infrastructure and runbooks

1. Replace `REPLACE_PRODUCTION_D1_ID` only after the production D1 resource exists.
2. Add scripts/workflows for:
   - migration status and preflight;
   - production migration with explicit environment approval;
   - Worker deploy by immutable release/tag;
   - console deploy;
   - API/console/site smoke tests;
   - rollback to previous Worker/console revision;
   - D1 backup/export and tested restore procedure.
3. Add structured, redacted operational logs and alert thresholds for:
   - 5xx rate;
   - webhook failures/backlog;
   - heartbeat ingestion failure;
   - D1 errors;
   - deployment health.
4. Add runbooks under `docs/runbooks/`:
   - production deploy/rollback;
   - D1 backup/restore;
   - Stripe webhook incident;
   - credential compromise/revocation;
   - tenant data export/deletion;
   - customer support escalation.
5. Add retention/deletion migrations/jobs and tests consistent with privacy/terms.
6. Review `docs/privacy.md` and `docs/terms.md` against the actual final data model and subprocessors; flag legal review items rather than inventing legal conclusions.

### Owner Gate 5 — production resources and secret placement

Owner performs only owner-required actions:

1. approve/create production D1 and protected GitHub `production` environment;
2. enter production Stripe/Cloudflare secrets directly in their stores;
3. confirm support/security email routing destination;
4. approve production DNS records;
5. confirm who may approve production deployments.

Hermes then verifies resource IDs, bindings, DNS, TLS, and email-routing behavior without accessing secret contents.

### Hermes work block 5B — production dry run

1. Deploy with live billing disabled or restricted to a private allowlist.
2. Apply/verify D1 migrations.
3. Probe:
   - `https://agentpulse.ca`;
   - `https://app.agentpulse.ca`;
   - `https://api.agentpulse.ca/health`.
4. Run synthetic non-billing account/session/enrollment/fleet smoke paths.
5. Exercise rollback and restore in a controlled way.
6. Record exact commit, Worker revision, D1 migration state, console artifact, and rollback result.

**Tier 4 release gate:** all production domains resolve; production deploy and rollback are proven; secrets remain external; observability and data lifecycle are operational.

---

# Tier 5 — Full commercial proof and go-live

## Phase 6: End-to-end release candidate

**Outcome:** The exact paid-customer lifecycle works at the release commit.

### Hermes work block 6A — automated release candidate gates

Run and require success for:

```bash
python3 agent/tools/run_tests.py
ruff check agent/
python3 scripts/validate-contracts.py
cd control-plane && npm test && npm run typecheck && npm run types:check && npm audit --audit-level=high
cd ../dashboard && npm run build && npm audit --audit-level=high
```

Also require:

- packaging/install/upgrade/rollback tests;
- migration upgrade/replay tests;
- dashboard Playwright suite;
- secret scan;
- two-tenant isolation;
- duplicate/out-of-order Stripe events;
- expired/replayed enrollment and sessions;
- cloud outage/spool/replay;
- failed-payment denial and paid recovery;
- D1 backup/restore and deploy rollback.

### Owner Gate 6 — authorize one controlled live transaction

Owner authorizes a low-risk real checkout using an approved payment method and confirms the expected charge. Hermes must not initiate a real charge without this gate.

### Hermes work block 6B — controlled paid lifecycle

1. Complete real checkout.
2. Claim the account once.
3. Establish secure session.
4. Create one-time enrollment token.
5. Install the immutable agent release on the approved non-critical host.
6. Confirm alert-only startup.
7. Submit heartbeat and view the correct tenant fleet/incidents.
8. Exercise portal access.
9. Exercise a controlled cancellation/refund or test equivalent chosen at Gate 2.
10. Verify entitlement transition and safe local behavior.
11. Confirm no manual D1 edit was required.
12. Redact and store release evidence.

### Owner Gate 7 — public go-live decision

Hermes presents one release dossier:

- exact commit/tag and artifact hashes;
- all CI/security/E2E results;
- staging and production URLs;
- migration/deployment/rollback receipts;
- controlled live-transaction result;
- known limitations;
- monitoring/support readiness;
- a go/no-go recommendation.

Owner chooses `GO` or `NO-GO`.

### Hermes work block 6C — go live or remediate

If `GO`:

1. remove private checkout gating;
2. publish the final release and truthful site/docs;
3. verify all public CTAs and install checksums;
4. monitor the first production window;
5. update `STATUS.md` with exact, current evidence.

If `NO-GO`:

1. keep production private;
2. convert every blocker into a testable issue;
3. fix all Hermes-owned blockers before requesting another decision.

**Tier 5 release gate:** first controlled paid lifecycle passes, Owner approves go-live, and public production remains healthy after promotion.

---

# Tier 6 — Post-launch reliability and product learning

## Phase 7: Operate without widening v1 scope

**Outcome:** AgentPulse becomes dependable and revenue-producing before adding broad features.

### Hermes-owned recurring work

1. Monitor release/CI/security/dependency health.
2. Triage real incidents by class and evidence.
3. Improve only existing bounded remediations before adding new action classes.
4. Maintain contract/client/migration synchronization.
5. Produce weekly metrics without storing customer-sensitive raw data:
   - activated accounts;
   - enrolled/active hosts;
   - successful/failed heartbeats;
   - incidents detected;
   - remediations proposed/executed/verified/escalated;
   - retention/churn/payment failures;
   - support burden.
6. Keep `STATUS.md` factual and timestamped.

### Owner involvement

Owner participates only in:

- customer conversations and commercial exceptions;
- approval of new remediation authority;
- pricing/positioning changes;
- legal/account-owner decisions;
- prioritizing features based on revenue and support evidence.

Do not add generic dashboards, chat agents, arbitrary commands, Kubernetes, a second database/backend, or broad observability until real customer evidence justifies a new architecture decision.

---

## 3. File map by phase

| Phase | Primary files/directories |
|---|---|
| 0 Repository convergence | `.github/workflows/*.yml`, `README.md`, `STATUS.md`, `docs/planning/`, archive manifests |
| 1 Packaging/install | `pyproject.toml`, `agent/`, `scripts/install-agent.sh`, `docs/install.sh`, `scripts/smoke-test.sh`, `.github/workflows/release.yml`, `docs/runbooks/` |
| 2–3 Billing/auth | `packages/contracts/openapi.yaml`, `packages/contracts/schemas/`, `packages/contracts/fixtures/`, `control-plane/migrations/`, `control-plane/src/index.ts`, `control-plane/test/`, `control-plane/wrangler.jsonc` |
| 4 Console | `dashboard/src/api/`, `dashboard/src/auth/`, `dashboard/src/pages/`, `dashboard/src/App.tsx`, dashboard test config/specs, console deployment workflow |
| 5 Production ops | `control-plane/wrangler.jsonc`, `.github/workflows/release.yml`, new deploy/smoke workflows, `scripts/`, `docs/runbooks/`, `docs/privacy.md`, `docs/terms.md` |
| 6 Go-live | `STATUS.md`, `CHANGELOG.md`, release evidence, public docs and CTAs |

---

## 4. Verification scorecard

No phase is complete until its row is proven at the exact candidate commit.

| Gate | Required evidence |
|---|---|
| Repository | Clean master, owner-confirmed historical-retention gate, green required checks, stale implementation lines closed/archived |
| Agent | 170+ current tests, lint, package contents, clean-host install, alert-only default, upgrade/rollback |
| Contracts | OpenAPI/schema/fixture validator passes; no undocumented active routes |
| Control plane | Workerd/D1 tests, typecheck, migration replay, Stripe replay/order tests, tenant isolation |
| Console | Build, accessibility checks, browser E2E against staging, secure session cookie verification |
| Security | Secret scan, dependency audits, log redaction, credential/session replay/revocation tests |
| Staging | Checkout/claim/session/enroll/heartbeat/fleet/failed-payment/recovery end to end |
| Production | DNS/TLS/health, deploy, migrations, backup/restore, rollback, controlled live transaction |
| Commercial | Correct plan/limit, portal/cancellation path, support routing, no manual DB edits |

---

## 5. Known risks and controls

| Risk | Control |
|---|---|
| Accidentally merging PR #19 restores a second backend | Close it after Gate 0; make Worker/D1 authority explicit in branch/PR templates |
| Historical source evidence is lost during cleanup | Confidential owner-reviewed retention evidence and explicit approval before deletion |
| Secret-scan suppression hides a real credential | Root-cause finding first; rotate real secrets; approve scan semantics before merge |
| Installer claims work but wheel contains no package | Build/install artifact tests before publishing |
| Enrollment secret leaks through command line/log | One-time short TTL, secure input/temporary file strategy, redaction, mode `0600`, immediate erasure |
| Browser credential theft | HttpOnly secure session, CSRF defense, rotation/revocation, no bearer token in `sessionStorage` |
| Cross-tenant data exposure | Server-derived tenant, tenant-leading queries/indexes, explicit two-tenant adversarial tests |
| Stripe events arrive duplicated/out of order | Event ID idempotency, canonical Stripe re-read, deterministic entitlement transitions |
| Billing outage disables safe local remediation | Local agent remains authoritative/offline; hosted entitlement affects cloud services, not safe local execution |
| Production migration fails | Preflight, backup, protected environment, tested migration and rollback/restore runbook |
| Documentation outruns the product | Status matrix and CI-linked release evidence; no green check from prose alone |
| Owner becomes the implementation bottleneck | Batch all Hermes work before one precise gate; never ask Owner to perform work Hermes can do |

---

## 6. Immediate next action

Merge the accepted repaired source, then stop at **Owner Gate 1** for approval to
publish immutable `v0.2.0-beta.2`. After publication, repeat the broad and
real-systemd clean-host lifecycle against the exact downloadable wheel and
checksums. Tier 1 closes only when that exact release passes. Repository ref
deletion remains separately blocked by the historical-retention gate.
