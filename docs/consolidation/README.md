# AgentPulse Consolidation Evidence

This directory records the AgentPulse consolidation process and its provenance.

The imported reports came from a separate execution environment on 2026-07-15.
Their architecture and disposition recommendations are useful design evidence,
but their claimed commits, branches, test totals, and publication state must be
reverified in this repository. They are not proof that the described source tree
exists here.

## Candidate

- Base ref: `origin/productization/cloudflare-paid-pilot`
- Candidate branch: `agent/consolidate-agentpulse-v2`
- Candidate worktree: `/home/desktopdusty/workspace/worktrees/agentpulse-consolidation`
- Canonical product domain: `agentpulse.ca`
- Hosted API target: `api.agentpulse.ca`
- Browser console target: `app.agentpulse.ca`

## Preserved existing checkout

The existing checkout remains separate at:

`/home/desktopdusty/workspace/repos/agentpulse`

Its four pre-existing modifications were preserved in:

`/home/desktopdusty/workspace/backups/agentpulse-consolidation-20260715/`

The preservation patch and SHA-256 receipt are outside this candidate and must
not be applied to the candidate automatically. The current checkout must remain
untouched while this worktree is consolidated.

## Authority map

```text
agent/                 local observation, policy, remediation, verification
control-plane/         hosted Worker/D1 authentication, tenancy, enrollment,
                       heartbeats, incidents, policy, and billing boundary
dashboard/             read-only browser fleet and incident UI
packages/contracts/    canonical OpenAPI and JSON Schema wire contracts
configs/               safe agent configuration examples and schemas
docs/                  public site and operator documentation
scripts/               install, smoke, validation, and hygiene tooling
```

## Publication boundary

This consolidation does not push, deploy, change the GitHub default branch, or
delete local or remote branches. Those actions require a separate review and
explicit authorization after independent verification.

## Acceptance boundary

The candidate is complete only when the local agent, Worker, dashboard,
contracts, documentation, CI, domain references, and hygiene checks pass from a
clean worktree. Paid-pilot release blockers—including Checkout claim, complete
Stripe subscription transitions, billing portal, production browser sessions,
real staging deployment, and signed release publication—remain outside this
consolidation.
