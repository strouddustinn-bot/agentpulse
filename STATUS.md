# AgentPulse Status

**Status date:** 2026-07-24
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
| Agent packaging | PASS | `python3 tests/test_packaging.py`: 20 lifecycle and packaging tests passed |
| Worker control plane | PASS | 24 Vitest tests, including 10 D1 schema/tenant-boundary tests; fresh replay and true pre-`0002` fail-closed upgrade fixtures pass; TypeScript and Wrangler generated bindings current |
| Cloudflare staging control plane | PARTIAL | Staging health and authenticated API smoke previously passed; new Phase 3A migration `0002` is source-tested but not deployed |
| Worker dependency audit | PASS | PostCSS fixed at 8.5.23 through a narrow override; fresh audit reports zero vulnerabilities |
| Shared contracts | PASS | OpenAPI 3.1 meta-schema, enforced cookie-session/CSRF shape, operation-bound response fixtures with URI checks, 12 paths, 39 local references, 9 JSON schemas, 7 typed fixtures, and 6 negative mutation tests; five Phase 3A routes explicitly labeled contract-only until Phase 3B handlers land |
| React dashboard | PASS | TypeScript and Vite production build |
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
| `https://agentpulse.ca` | HTTP 200 from the canonical Pages deployment |
| `https://app.agentpulse.ca` | DNS unresolved at last check |
| `https://api.agentpulse.ca/health` | DNS unresolved at last check |
| Public multi-host checkout | Closed; Pro and Business are founding reservations until checkout-to-entitlement and host-limit enforcement are proven |

The repository is therefore a verified implementation baseline with a live
staging API, not a deployed self-serve production service.

## Packaging reality (Tier 1 progress)

Implemented in source:

- real `agentpulse` wheel with package modules, console script, systemd unit, launchd plist, example config, and license assets
- isolated packaging tests and CI matrix for Python 3.10–3.13
- install/upgrade/rollback scripts that require explicit versions and SHA-256 verification
- release workflow that builds wheel/sdist + `SHA256SUMS` without requiring production control-plane deploy for agent prereleases
- public `docs/install.sh` remains fail-closed

Still required before public install enablement:

- Tier 1 is complete; the published `v0.2.0-beta.2` artifact passed exact clean-host acceptance
- Public self-serve installation remains closed until Tier 2 commercial lifecycle is proven end to end

Tier 2 Phase 3A now defines the checkout, claim, browser-session, account, and
billing-portal contracts plus additive D1 claim/session/entitlement migrations.
The new routes are contract-only: no public or staging runtime handler is claimed
until Phase 3B implements and verifies them.

## Supported boundary

The agent remains locally authoritative and useful during control-plane outages. It follows:

```text
Observe → Reason → Simulate → Gate → Act → Verify → Record or Escalate
```

Cloud policy can narrow but cannot increase the local authority ceiling. Unknown actions fail closed. The Worker does not expose arbitrary host commands or unrestricted remote shell access. The dashboard is read-only for fleet and incident evidence.

## Paid-beta operations

The repository contains Worker enrollment/heartbeat/fleet APIs, local-agent
source, an accepted exact-release agent artifact, and a read-only console.
Public multi-host checkout is closed because the complete paid onboarding
lifecycle has not yet been proven end to end. Any paid-beta customer must therefore be
handled as a controlled manual pilot until those gates pass.

The following are not represented as finished production capabilities:

- secure browser cookie/session authentication; the current console connection credential is beta-only;
- automatic Stripe checkout-to-account claim;
- self-service billing portal and complete automated subscription lifecycle;
- browser-level dashboard acceptance against staging; the staging dashboard is not deployed;
- production deployment and rollback evidence.

These are explicit release gates for fully self-serve public production, not hidden or duplicate implementations elsewhere in the local source tree.
