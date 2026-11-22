# AgentPulse — repository instructions

## Purpose and boundaries
AgentPulse is a local-first server observation and bounded remediation platform. The local agent, not the cloud or dashboard, is authoritative for host actions. See `README.md`, `ARCHITECTURE.md`, `SECURITY.md`, and `STATUS.md` before material changes. Treat deployment claims as evidence-dependent; verify against current runs rather than repeating dated status.

## Source map
- `agent/`: local observation, proposal, policy enforcement, verification, evidence
- `control-plane/`: Cloudflare Worker and D1
- `dashboard/`: React/Vite customer console; must not become an unrestricted remote shell
- `packages/contracts/`: OpenAPI, JSON Schema, fixtures
- `configs/`, `scripts/`, `docs/`: policies, validation and operational documentation

## Non-negotiable safety constraints
- Preserve the `Observe -> Reason -> Simulate -> Gate -> Act -> Verify -> Record or Escalate` boundary.
- Unknown actions fail closed. Cloud policy may restrict but never raise local authority.
- No arbitrary host-command channel, remote shell, automatic unbounded retry, or bypass of local policy.
- Preserve owner approval for production, deployments, payment, security permissions, and destructive actions.
- Never commit credentials or confidential operational evidence; preserve archive and retention gates.

## Development and verification
Documented prerequisites: Python 3.10+ and Node.js 22.12+. From the repository root, `./scripts/bootstrap-dev.sh` prepares development dependencies. Relevant documented checks:
- `make agent-test`
- `make contracts-validate`
- `make cp-test`
- `make cp-typecheck`
- `make dashboard-build`
For targeted changes, run affected checks and report exact results; use `README.md` for lower-level commands. Do not interpret a passing unit test as production deployment verification.

## Working rules
Inspect existing interfaces and state before editing. Keep backend, agent, contracts, and dashboard compatible. Distinguish local development, staging, production, and external activation. Update these instructions when architecture or commands change. Never certify the entire product as ready based solely on source changes.
