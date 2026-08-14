# AgentPulse Status

**Status date:** 2026-08-14
**Canonical GitHub branch:** `master`

## Consolidated product

```text
agent/                    dependency-light local monitoring/remediation agent
control-plane/            Cloudflare Worker + D1 hosted authority
dashboard/                single React fleet and incident console
packages/contracts/       canonical OpenAPI, JSON Schema, and fixtures
configs/                  current agent schema and safe policy examples
scripts/                  bootstrap, install, packaging, and contract validation
docs/                     public product, pricing, legal, and support site
```

Historical source retention is governed by `ARCHIVES.md`. Confidential operational evidence is not published; deletion requires an owner-approved retention gate.

## Current source verification

| Area | Result | Evidence |
|---|---|---|
| Local agent behavior | PASS | `python3 agent/tools/run_tests.py`: 213 passed, 0 failed |
| Agent lint | PASS | `ruff check agent/` |
| Agent config contract | PASS | Draft 7 schema and current example validated with format checks |
| Agent packaging | PASS | Exact-commit GitHub packaging matrix passed on Python 3.10–3.13; Windows package/CLI/service lifecycle passed on Windows Server 2025 |
| Worker control plane | PASS | `npm --prefix control-plane test`: 81 tests passed across fleet/agent routes, checkout, claim, browser session/CSRF, portal, full Stripe event set, grace entitlement, webhook fencing, staging harness, Stripe-mode fail-closed behavior, and unknown-price denial |
| Cloudflare staging control plane | PASS (staging lifecycle) | Health live; migrations `0001`–`0003` applied; Worker `f319e12d-e776-4b90-94b2-1e0c57ce5649` from `7aee6b5` (Basil period/invoice fix) with canonical `APP_BASE_URL`; disposable callback torn down after proof |
| Worker dependency audit | PASS | PostCSS fixed at 8.5.23 and Nano ID forced to patched 3.3.18 through narrow overrides; fresh audit reports zero vulnerabilities |
| Shared contracts | PASS | OpenAPI 3.1 meta-schema, enforced cookie-session/CSRF shape, operation-bound response fixtures with URI checks; billing/session routes labeled `implemented` after Phase 3B |
| React dashboard | PASS | 19 browser-auth/account/API tests plus TypeScript and Vite production build; Account page (enrollment token + billing portal), RequireSession gate, cookie+CSRF mutations; Phase 4B mocked Playwright E2E scaffolded (`npm run test:e2e`) |
| Dashboard dependency audit | PASS | React Router 8.3.0 and PostCSS 8.5.23; fresh audit reports zero vulnerabilities |
| Repository hardening | PASS | shell syntax, workflow YAML, credential patterns, tracked dependencies, and retired paths |
| Production readiness controls | PASS (beta 5 source) | 80 production/readiness tests cover provider-state capture, incomplete-bootstrap DNS deferral, post-Pages DNS enforcement, Stripe diagnostics, bounded smoke retries, recovery export preservation, packaging, and rollback controls |
| Secret scanning | PASS on release path design | Release, Security, and production-deploy workflows use the same pinned TruffleHog 3.95.9 verified-finding policy and documented Lob-detector exclusion |

These are verification receipts for the referenced source state, not a claim
that the public production service is launched.

## Deployment reality

Verified state on 2026-08-14 after the failed-closed beta 4 attempts:

| Surface | Result |
|---|---|
| `https://staging-api.agentpulse.ca/health` | HTTP 200 |
| `https://staging-app.agentpulse.ca/` | HTTP 200 real console shell (`AgentPulse Dashboard`, SPA root + assets); Owner Gate 4 DNS/TLS live |
| `https://agentpulse.ca` | HTTP 200 from the canonical Pages deployment |
| Production infrastructure | Gate 5 bootstrap remains provisioned: D1 `agentpulse-production`, Pages project `agentpulse-production-app`, production branch `production`, and protected `production` environment exist. Beta 4 attempt 2 preserved a pre-migration D1 export, applied migration `0003_webhook_concurrency_fencing.sql`, and uploaded the production Worker bundle. The custom-domain route update then failed closed with Cloudflare API error 10000 because the deployment token lacked zone-level `Workers Routes: Edit`; that permission is now present for `agentpulse.ca`. |
| `https://app.agentpulse.ca` | Pages custom-domain association is configured, but no production Pages deployment completed; public DNS remained unresolved at beta 4 attempt 3 |
| `https://api.agentpulse.ca/health` | A beta 4 production Worker script was uploaded, but its custom-domain route was not attached; public DNS remained unresolved at beta 4 attempt 3 |
| Public multi-host checkout | Closed; Pro and Business are founding reservations until host-limit revalidation and controlled pilot path |

Beta 4 attempt 3 stopped before any new production mutation. Its live preflight
incorrectly treated the partial Worker upload as completion of the first-deploy
bootstrap even though Pages had never deployed. The beta 5 source candidate
makes the first successful production Pages deployment the durable bootstrap
marker, so a Worker-only partial deployment can be recovered while completed
deployments still require both production domains to resolve.

The repository is a verified beta 5 controlled-pilot candidate with partially
deployed production infrastructure. It is not yet a deployed self-serve
production service, and the public checkout remains closed.

## Packaging reality (Tier 1 complete)

- real `agentpulse` wheel with package modules, console script, systemd unit, launchd plist, example config, and license assets
- isolated packaging tests and CI matrix for Python 3.10–3.13
- install/upgrade/rollback scripts that require explicit versions and SHA-256 verification
- release workflow that builds wheel/sdist + `SHA256SUMS` without requiring production control-plane deploy for agent prereleases
- public `docs/install.sh` remains fail-closed
- published `v0.2.0-beta.2` artifact passed exact clean-host acceptance
- `v0.2.0-beta.3` adds a checksum-pinned native Windows service lifecycle that passed install, running-state, remediation restart, verification, and uninstall on Windows Server 2025

Public self-serve installation remains closed through Tier 4 production proof and the controlled pilot gate.

## Tier 2 Phase 3 status

Phase 3A contracts/migrations and Phase 3B Worker handlers are implemented in
source:

- `POST /v1/billing/checkout`
- `POST /v1/onboarding/claim`
- `GET /v1/account`
- `DELETE /v1/session`
- `POST /v1/billing/portal`
- full Stripe event set with normalized entitlement + 3-day grace
- browser `ap_session` cookie + CSRF for mutations
- enrollment/heartbeat/fleet enforce hosted entitlement without disabling local agent operation

Staging lifecycle proof completed 2026-07-30 (redacted):

- exact tip `7aee6b53b50cd3d3608fc581d189059285d9476e` deployed; temporary callback Worker used while `staging-app` DNS is unresolved, then deleted;
- Stripe test checkout (`livemode=false`, plan=starter) paid and claimed;
- disposable callback receipt: `complete=true`, `passed=true` for claim/replay, account, CSRF denials, portal, enrollment, heartbeat, fleet, logout;
- checkout_sessions gained one `claimed` row; browser session issued then revoked by logout path;
- restored canonical staging `APP_BASE_URL=https://staging-app.agentpulse.ca`; recovery route not retained in source;
- Gate 3 is merged and Tier 3 passed; remaining before public multi-host checkout: Tier 4 production infrastructure/deploy/rollback/operations proof, the controlled pilot path, and the later go-live gate.

## Supported boundary

The agent remains locally authoritative and useful during control-plane outages. It follows:

```text
Observe → Reason → Simulate → Gate → Act → Verify → Record or Escalate
```

Cloud policy can narrow but cannot increase the local authority ceiling. Unknown actions fail closed. The Worker does not expose arbitrary host commands or unrestricted remote shell access. The dashboard is read-only for fleet and incident evidence.

## Paid-beta operations

The repository contains Worker enrollment/heartbeat/fleet APIs, billing/session
handlers, an accepted exact-release agent artifact, and a read-only console.
Public multi-host checkout remains closed until host-limit enforcement is
revalidated on the merged tip and a controlled pilot path is approved. Staging test-mode checkout→claim→session→portal→enrollment→
heartbeat→fleet is now proven with redacted receipts.

- Phase 4A console (source): Account route with subscription status, one-time browser enrollment token mint (cookie+CSRF), Stripe portal launch with host allowlist, RequireSession on fleet routes; no browser bearer storage.
- Phase 4B progress: mocked Playwright console E2E green in CI; staging console deployed to Pages project `agentpulse-staging-app` on production branch `main` and serving at `https://staging-app.agentpulse.ca` with `VITE_API_BASE_URL=https://staging-api.agentpulse.ca`. CORS preflight from staging-app origin accepted with credentials.
- Phase 4B live manual proof (2026-08-01, staging/test-mode): owner Stripe test checkout → claim → browser session → Account (`starter`/`active`/host_limit=1) → enrollment token → host enroll (`desktopdusty-HP-EliteDesk-800-G5-Desktop-Mini`) → heartbeat → Servers Online → Disconnect returned `/connect`. Unauthenticated API still returns 401 session-required. Local redacted receipt: `~/.local/state/agentpulse/phase4b/phase4b-manual-lifecycle-receipt.txt`.
- Phase 4B live automated Playwright (2026-08-01): `npm run test:e2e:staging` (`--project=staging-live`) green — Playwright creates Stripe test-mode Checkout, pays with Visa test card + unique email, auto-claims, opens Account, mints enrollment token, Disconnect → `/connect`, asserts no bearer/claim/enroll material in JS storage. Mocked E2E remains 5/5 green. Script targets `--project=staging-live` (`778187b`+).
- **Tier 3 release gate: PASS (staging)** — staging console resolves + TLS; live + mocked browser E2E green; no production bearer in JS storage (legacy `removeItem` only); no command-dispatch route in dashboard/OpenAPI. Receipt: `~/.local/state/agentpulse/phase4b/tier3-gate-receipt.txt`.

Remaining gates:

- Synthetic Stripe **test-mode** subscription cleanup is reconciled: a read-only staging D1 aggregate on 2026-08-01 returned 7 `canceled` Starter subscriptions and no active rows; no D1 rows were edited.
- Gate 5 bootstrap completed successfully from immutable tag `gate5-infra-20260813`; the production D1 UUID, Pages project/branch, custom-domain association, protected environment, and exact-tag policy are configured. The environment must allowlist beta 5 before that immutable tag can deploy.
- The beta 5 Phase 5A candidate includes read-only Cloudflare provider-state capture, incomplete-bootstrap unresolved-DNS recovery, exact dashboard artifact, bounded post-deploy smoke, failure-safe recovery upload, disposable-D1 restore drill, saved-version Worker/console recovery rehearsal, safe Stripe diagnostics, runbooks, tests, and dedicated CI. The combined production/readiness suites pass 80/80 locally; exact-commit CI remains required.
- `.github/workflows/production-deploy.yml` is the only authorized production mutation path. It is exact-tag-only, reviewer-protected, binds tag/package/source identity, runs the complete agent/contracts/package/Worker/dashboard/security verification set, preserves the D1 export even after a downstream failure, and keeps checkout closed.
- Immutable `v0.2.0-beta.4` remains at `cd3d46eb29699fc5018dd26853deab471b4f1f64`. Its draft release remains unpublished. Recovery now requires beta 5 merge-SHA CI, exact environment allowlisting, a new immutable beta 5 tag, the protected deployment, Worker route and Pages completion, DNS/TLS identity smoke, D1 restore, recovery-rehearsal receipts, and deployment evidence before publication.
- operational alerting and executable data-retention/deletion evidence remain after the controlled deployment proof;
- controlled pilot customers only until public multi-host checkout opens;
- return OAuth/password login remains deferred.
