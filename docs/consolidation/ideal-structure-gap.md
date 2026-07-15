> **Imported design evidence from a separate execution environment on 2026-07-15. Commit and test claims must be reverified in this repository. This document is not itself proof that the described source tree exists.**

# Master vs. Ideal Structure

The closest committed version of the earlier ideal layout is the project
skeleton introduced in commit `f8e168a`: one agent, one control plane, one
dashboard, shared contracts, configuration, scripts, observability, and CI.

## Alignment

| Ideal responsibility | Master location | State |
|---|---|---|
| Host runtime | `agent/` | Strong |
| Hosted control plane | `control-plane/` | Strong foundation; billing incomplete |
| Fleet frontend | `dashboard/` | Real contract wired; session auth still beta |
| Shared contracts | `packages/contracts/` | OpenAPI reconciled to the surviving Worker routes |
| Safe configuration | `configs/` | Present |
| Install and smoke tooling | `scripts/` | Present; needs final release artifact proof |
| CI gates | `.github/workflows/` | Consolidated |
| Product/operator docs | `README.md`, `ARCHITECTURE.md`, `STATUS.md`, `docs/` | Source of truth reset |

## Intentional departures

- The generic FastAPI backend was removed. Two hosted authorities are worse than
  one, especially when one exposes tenant-owned reads without account auth.
- The second dashboard and its Python service were removed. Their live local
  metrics are useful product ideas, not a reason to keep a parallel application.
- Generic Docker/Fly deployment files were removed because they targeted the
  retired services and produced a false impression of a deployable full stack.
- Prometheus/Grafana examples were removed until they consume the surviving
  control-plane contract.

## Next build order

1. Complete Stripe subscription transitions and Checkout claim.
2. Replace dashboard bearer entry with a server-side session.
3. Add one end-to-end staging test from checkout through failed-payment denial.
4. Publish signed/checksummed agent artifacts and verify systemd/launchd installs.
5. Only then add new remediations, metrics charts, or deployment targets.
