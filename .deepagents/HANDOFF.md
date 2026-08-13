# Deepagents ↔ Hermes Handoff

## Current role

Deepagents should act as a local execution layer for AgentPulse: inspect, implement narrow changes, run real verification, suggest system-improving plays for Hermes to evaluate, and leave concise notes that Hermes or another agent can continue from.

## Local-only default

All Deepagents work is local by default. Deepagents should implement and verify locally, then present the work to Hermes for commit, push, and release. Remote operations require explicit Dustinn approval, including commits, pushes, branch creation, PRs, deployments, DNS, Stripe, Cloudflare mutations, or production-impacting actions.

## Current observed state

- Repo: `/home/desktopdusty/workspace/repos/agentpulse`
- Branch: `master`
- `git status --short --branch` showed existing uncommitted work in `control-plane/`, `packages/contracts/`, `scripts/`, `tests/`, plus untracked `.hermes/` and `media/`.
- Existing Hermes plan: `.hermes/plans/2026-07-22_111324-agentpulse-luna-tier2.md`
- Do not overwrite or stage existing Hermes/user work unless Dustinn explicitly asks.

## Deepagents best-fit lanes

1. Repo hygiene and truth maintenance
   - reconcile stale path references
   - keep `STATUS.md` honest after verified commands
   - identify release gates versus implemented source

2. Verification and adversarial testing
   - reproduce failures
   - add narrow regression tests
   - run exact relevant gates and record outputs

3. Contracts/control-plane/dashboard handoff work
   - preserve OpenAPI as source of truth
   - keep Worker/browser-session/security invariants intact
   - avoid arbitrary host-command or remote-shell patterns

4. Agent safety work
   - read safety docs first
   - preserve simulate → gate → verify behavior
   - never weaken fail-closed policy or fuzz safety expectations

## Open recommendation for Hermes review

- Review `.deepagents/FOUR_AGENT_COUNCIL_RECOMMENDATION.md` for a proposed Deepagents ↔ Codex ↔ Claude ↔ Hermes workflow.
- Summary: Deepagents implements/verifies locally, Codex performs adversarial code/test/security review, Claude performs planning/architecture/docs/product-coherence review, and Hermes owns final decision plus commit/push/release.
- This is a process recommendation only; no automation or repo policy should be implemented unless Hermes chooses to run the play.

## Handoff format

When pausing or finishing non-trivial work, append:

```text
## YYYY-MM-DD — Agent — Task
Outcome:
Files touched:
Verification:
Remaining gates:
Notes for Hermes:
```
