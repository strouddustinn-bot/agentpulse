# AgentPulse Status

**Status date:** 2026-07-15
**Candidate branch:** `agent/consolidate-agentpulse-v2`
**Source baseline:** `origin/productization/cloudflare-paid-pilot` at `f2593dbd6201949866c4a35587e4666864c813ac`

## Consolidation status

| Area | Status | Evidence |
|---|---|---|
| Local agent | PASS | `agent/tools/run_tests.py`: 170 passed, 0 failed |
| Worker control plane | PASS | 13 Vitest tests, TypeScript, Wrangler bindings |
| Incident materialization | PASS | Worker test covers idempotency, upsert, tenant isolation |
| Shared contracts | PASS | `scripts/validate-contracts.py` |
| React dashboard | PASS | `cd dashboard && npm run build` |
| Duplicate runtime removal | PASS | FastAPI, duplicate dashboards, Fly/Docker/observability paths removed |
| CI paths | PASS | Workflows point at `agent`, `control-plane`, `dashboard`, and `packages/contracts` |
| Browser authentication | BLOCKED | Beta sessionStorage credential only; secure browser sessions not implemented |
| Paid billing lifecycle | BLOCKED | Checkout claim and billing portal remain outside this consolidation scope |
| Staging deployment | NOT RUN | Requires Cloudflare account configuration and redacted secrets |

## Active architecture

```text
agent/ → control-plane/ (Cloudflare Worker + D1) → dashboard/
             ↑
       packages/contracts/
```

The agent remains locally authoritative and offline-capable. The Worker can narrow policy intent and store evidence but cannot execute arbitrary host commands. The dashboard is read-only and calls only the authenticated `/v1/fleet` route.

## Verification commands

```bash
cd agent && python3 tools/run_tests.py
cd .. && .venv/bin/python scripts/validate-contracts.py
cd control-plane && npm test && npm run typecheck && npm run types:check
cd ../dashboard && npm run build
cd .. && find scripts -type f -name '*.sh' -print0 | xargs -0 -r -n1 bash -n
```

The imported reports in `docs/consolidation/` are historical provenance, not independent proof. The current receipts are recorded in the candidate commit history and must be rerun by CI before publication.

## Release blockers intentionally preserved

- Replace the beta browser credential with secure cookie/session authentication.
- Complete checkout-to-account claim and billing portal lifecycle.
- Deploy staging and exercise enrollment → heartbeat → incident → fleet read with real Cloudflare resources.
- Configure DNS and secrets for `agentpulse.ca`, `app.agentpulse.ca`, and `api.agentpulse.ca`.
- Perform browser-level verification against staging.
