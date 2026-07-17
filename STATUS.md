# AgentPulse Status

**Status date:** 2026-07-17
**Canonical GitHub branch:** `master`
**Phase 0 implementation branch:** `chore/phase-0-repository-convergence`


## Consolidated product

```text
agent/                    dependency-light local monitoring/remediation agent
control-plane/            Cloudflare Worker + D1 hosted authority
dashboard/                single React fleet and incident console
packages/contracts/       canonical OpenAPI, JSON Schema, and fixtures
configs/                  current agent schema and safe policy examples
scripts/                  bootstrap, install, and contract validation
docs/                     public product, pricing, legal, and support site
```

Historical source retention is governed by `ARCHIVES.md`. Confidential operational evidence is not published; deletion requires an owner-approved retention gate.

## Current source verification

| Area | Result | Evidence |
|---|---|---|
| Local agent behavior | PASS | `python3 agent/tools/run_tests.py`: 170 passed, 0 failed |
| Agent lint | PASS | `ruff check agent/` |
| Agent config contract | PASS | Draft 7 schema and current example validated with format checks |
| Worker control plane | PASS | 14 Vitest tests; TypeScript and Wrangler generated bindings current |
| Cloudflare staging control plane | PASS | D1 migrations current; Worker `d2fe6dd1-17f4-4be4-9096-91ebfb1be405`; custom-domain health and authenticated API smoke passed |
| Worker dependency audit | PASS | no high-severity npm findings |
| Shared contracts | PASS | 7 OpenAPI paths, 19 local references, 9 JSON schemas, 3 fixtures |
| React dashboard | PASS | TypeScript and Vite production build |
| Dashboard dependency audit | PASS | no high-severity npm findings |
| Repository hardening | PASS | shell syntax, workflow YAML, credential patterns, tracked dependencies, and retired paths |
| Secret-scan diagnosis | PASS locally; CI pending | TruffleHog 3.95.9: default scan reproduced exit 183 on synthetic URI credentials; `--only-verified` returned 0 with zero verified secrets |


These are verification receipts for the referenced source state, not a claim
that the public production service is launched. Phase 0 changes must pass fresh
local and GitHub checks before this branch can be merged.

## Deployment reality

Probe results on 2026-07-17:

| Surface | Result |
|---|---|
| `https://staging-api.agentpulse.ca/health` | HTTP 200 |
| `https://agentpulse.ca` | DNS unresolved |
| `https://app.agentpulse.ca` | DNS unresolved |
| `https://api.agentpulse.ca/health` | DNS unresolved |
| Starter, Pro Beta, and Business Stripe Payment Links | HTTP 200; purchase lifecycle not exercised |

The repository is therefore a verified implementation baseline with a live
staging API, not a deployed self-serve production service.

## Supported boundary

The agent remains locally authoritative and useful during control-plane outages. It follows:

```text
Observe → Reason → Simulate → Gate → Act → Verify → Record or Escalate
```

Cloud policy can narrow but cannot increase the local authority ceiling. Unknown actions fail closed. The Worker does not expose arbitrary host commands or unrestricted remote shell access. The dashboard is read-only for fleet and incident evidence.

## Paid-beta operations

The repository contains public Stripe Payment Links, Worker
enrollment/heartbeat/fleet APIs, local-agent source, and a read-only console.
Payment links are reachable, but clean-host installation and the complete paid
onboarding lifecycle have not yet been proven end to end. Any paid-beta
customer must therefore be handled as a controlled manual pilot until those
gates pass.

The following are not represented as finished production capabilities:

- secure browser cookie/session authentication; the current console connection credential is beta-only;
- automatic Stripe checkout-to-account claim;
- self-service billing portal and complete automated subscription lifecycle;
- immutable, checksummed agent packaging plus proven install, upgrade, and rollback;
- browser-level dashboard acceptance against staging; the staging dashboard is not deployed;
- production deployment and rollback evidence.

These are explicit release gates for fully self-serve public production, not hidden or duplicate implementations elsewhere in the local source tree.
