# AgentPulse Status

**Status date:** 2026-07-30
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
| Local agent behavior | PASS | `python3 agent/tools/run_tests.py`: 193 passed, 0 failed |
| Agent lint | PASS | `ruff check agent/` |
| Agent config contract | PASS | Draft 7 schema and current example validated with format checks |
| Agent packaging | PASS | `python3 -m unittest tests.test_packaging -v`: 22 lifecycle, packaging, and development/release gate tests passed |
| Worker control plane | PASS | `npm --prefix control-plane test`: 77 tests passed across fleet/agent routes, checkout, claim, browser session/CSRF, portal, full Stripe event set, grace entitlement, webhook fencing, staging harness, Stripe-mode fail-closed behavior, and unknown-price denial |
| Cloudflare staging control plane | PASS (staging lifecycle) | Health live; migrations `0001`–`0003` applied; Worker `f319e12d-e776-4b90-94b2-1e0c57ce5649` from `7aee6b5` (Basil period/invoice fix) with canonical `APP_BASE_URL`; disposable callback torn down after proof |
| Worker dependency audit | PASS | PostCSS fixed at 8.5.23 through a narrow override; fresh audit reports zero vulnerabilities |
| Shared contracts | PASS | OpenAPI 3.1 meta-schema, enforced cookie-session/CSRF shape, operation-bound response fixtures with URI checks; billing/session routes labeled `implemented` after Phase 3B |
| React dashboard | PASS | 19 browser-auth/account/API tests plus TypeScript and Vite production build; Account page (enrollment token + billing portal), RequireSession gate, cookie+CSRF mutations; Phase 4B mocked Playwright E2E scaffolded (`npm run test:e2e`) |
| Dashboard dependency audit | PASS | React Router 8.3.0 and PostCSS 8.5.23; fresh audit reports zero vulnerabilities |
| Repository hardening | PASS | shell syntax, workflow YAML, credential patterns, tracked dependencies, and retired paths |
| Secret scanning | PASS on release path design | TruffleHog pinned 3.95.9 with `--only-verified` remains fail-closed for verified findings |

These are verification receipts for the referenced source state, not a claim
that the public production service is launched.

## Deployment reality

Probe results on 2026-07-20:

| Surface | Result |
|---|---|
| `https://staging-api.agentpulse.ca/health` | HTTP 200 |
| `https://staging-app.agentpulse.ca/` | HTTP 200 real console shell (`AgentPulse Dashboard`, SPA root + assets); Owner Gate 4 DNS/TLS live |
| `https://agentpulse.ca` | HTTP 200 from the canonical Pages deployment |
| `https://app.agentpulse.ca` | DNS unresolved at last check |
| `https://api.agentpulse.ca/health` | DNS unresolved at last check |
| Public multi-host checkout | Closed; Pro and Business are founding reservations until host-limit revalidation and controlled pilot path |

The repository is therefore a verified implementation baseline with a live
staging health endpoint, not a deployed self-serve production service.

## Packaging reality (Tier 1 complete)

- real `agentpulse` wheel with package modules, console script, systemd unit, launchd plist, example config, and license assets
- isolated packaging tests and CI matrix for Python 3.10–3.13
- install/upgrade/rollback scripts that require explicit versions and SHA-256 verification
- release workflow that builds wheel/sdist + `SHA256SUMS` without requiring production control-plane deploy for agent prereleases
- public `docs/install.sh` remains fail-closed
- published `v0.2.0-beta.2` artifact passed exact clean-host acceptance

Public self-serve installation remains closed until the Tier 2 commercial lifecycle is proven end to end on staging.

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
- remaining before public multi-host checkout: merge Gate 3 branch after fresh CI, broader negative/isolation matrix if not already covered by unit tests, controlled pilot path, production deploy gates.

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

- Owner cleanup: cancel/expire synthetic Stripe **test-mode** subscriptions created during staging proofs (no local `STRIPE_API_KEY`; use Stripe Dashboard test mode). Staging D1 currently has multiple active starter rows from repeated E2E runs.
- production deployment and rollback evidence;
- controlled pilot customers only until public multi-host checkout opens;
- return OAuth/password login remains deferred.
