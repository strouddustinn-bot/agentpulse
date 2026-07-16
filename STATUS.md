# AgentPulse Status

**Status date:** 2026-07-15
**Master branch:** `master/consolidated`
**Master worktree:** `/home/desktopdusty/workspace/worktrees/agentpulse-master`
**Archive repository:** `/home/desktopdusty/workspace/repos/agentpulse-archives`

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

Superseded source, exact dirty patches, recovery evidence, and a complete Git bundle are stored in the separate archive repository. See `ARCHIVES.md`.

## Local verification

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
| Archive integrity | PASS | checksums, tar snapshots, and complete Git bundle verified |

## Supported boundary

The agent remains locally authoritative and useful during control-plane outages. It follows:

```text
Observe → Reason → Simulate → Gate → Act → Verify → Record or Escalate
```

Cloud policy can narrow but cannot increase the local authority ceiling. Unknown actions fail closed. The Worker does not expose arbitrary host commands or unrestricted remote shell access. The dashboard is read-only for fleet and incident evidence.

## Paid-beta operations

The repository supports the current manually onboarded paid-beta model: public Stripe Payment Links, manual account confirmation, local agent installation, Worker enrollment/heartbeat/fleet APIs, and a read-only console.

The following are not represented as finished production capabilities:

- secure browser cookie/session authentication; the current console connection credential is beta-only;
- automatic Stripe checkout-to-account claim;
- self-service billing portal and complete automated subscription lifecycle;
- browser-level dashboard acceptance against staging; the staging dashboard is not deployed;
- production deployment and rollback evidence.

These are explicit release gates for fully self-serve public production, not hidden or duplicate implementations elsewhere in the local source tree.
