> **Imported design evidence from a separate execution environment on 2026-07-15. Commit and test claims must be reverified in this repository. This document is not itself proof that the described source tree exists.**

# AgentPulse Source Consolidation Inventory

Date: 2026-07-15

## Scope searched

The accessible local filesystem and connected GitHub installation were searched
for AgentPulse directories, archives, Git repositories, branches, pull
requests, stashes, reflogs, and unreachable Git objects.

Found:

- One local source repository: `strouddustinn-bot/agentpulse`.
- One connected GitHub repository with the same remote.
- No additional AgentPulse source archives, stashes, or unreachable draft commits.
- One uncommitted 29-file draft on top of `productization/cloudflare-paid-pilot`; preserved in local commit `eea9d2d` on `archive/pre-consolidation-20260715`.
- Two non-source product-guide artifacts in another scratch workspace; excluded from code consolidation.

## GitHub branch disposition

| Branch | Finding | Disposition |
|---|---|---|
| `main` | Public site and original agent; behind verified product work | Replace after master verification |
| `productization/cloudflare-paid-pilot` | Superset containing agent trust layer, control plane, both backends, and both dashboards | Primary source pool |
| `claude/github-profile-cleanup-97quky` | Already included | Delete after master publication |
| `claude/review-revision-tr5e0b` | Already included | Delete after master publication |
| `claude/pr9-clean` | Alternate history of merged safety work | Delete after master publication |
| `claude/test-coverage-analysis-2jmku4` | One `.gitignore` housekeeping change | Reapply if still useful; delete branch |
| `claude/ultracode-hoq2iv` | Marketing truth-alignment branch with later divergent/revert history | Mine claims; delete branch |
| `revert-12-claude/ultracode-hoq2iv` | Revert-only branch | Delete after master publication |
| `revert-3-claude/ultracode-hoq2iv` | Already included revert | Delete after master publication |

## Side-by-side implementation comparison

| Candidate | Strengths | Failures / duplication | Decision |
|---|---|---|---|
| `agent/` | 171 green tests; verified safety loop, trust layer, macOS/Linux support | README counts and cloud incident shape were stale | Keep and update |
| `backend/` | Structured FastAPI routes, repositories, migrations, incident lifecycle | Fleet and incident reads lacked tenant authentication; duplicated hosted authority | Remove from master |
| `control-plane/` | Small Worker, D1, tenant-derived auth, enrollment, policy ceiling, billing boundary | Fleet returned only agents; heartbeat incidents were not materialized | Keep; add incident ingestion and fleet incidents |
| `dashboard/frontend/` | Routed fleet/incident UI; smaller bundle; aligned with hosted product | Bound to removed FastAPI shapes; no account authentication | Keep as `dashboard/`; bind to `/v1/fleet` |
| `dashboard/web/` | Live local metrics, SSE, history, approve/deny | Tightly coupled to a second monolithic Python service; larger bundle | Remove from master |
| `dashboard/pulse_server/` | Working single-host UI backend and local billing prototype | Duplicated control plane, database, billing, and API authority | Remove from master |
| `dashboard/backend/`, `dashboard/realtime/`, `dashboard/shared/` | Early scaffolding | Incomplete and superseded | Remove from master |

## Resulting authority map

- Host decisions and remediation: `agent/`.
- Hosted identity, tenancy, fleet, incidents, policy, and billing: `control-plane/`.
- Browser UI: `dashboard/`.
- Schemas and OpenAPI: `packages/contracts/`.

No legacy runtime remains in the master candidate. Recoverability is provided by
the pre-consolidation archive branch until the new default branch is published
and independently verified.
