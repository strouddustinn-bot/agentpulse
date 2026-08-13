# AgentPulse Agent Operating Guide

This repository is safe for multi-agent local work when agents preserve each other's changes and keep public/production actions behind explicit owner approval.

## Canonical paths

- Repository: `/home/desktopdusty/workspace/repos/agentpulse`
- Canonical branch: `master`
- Hermes plans: `.hermes/plans/`
- Deepagents handoffs: `.deepagents/`
- Historical source: `/home/desktopdusty/workspace/repos/agentpulse-archives`

Older notes may mention `/home/desktopdusty/workspace/repositories/agentpulse`; treat `/home/desktopdusty/workspace/repos/agentpulse` as the current canonical path unless Dustinn says otherwise.

## Product boundary

AgentPulse is local-first server remediation:

```text
Observe → Reason → Simulate → Gate → Act → Verify → Record or Escalate
```

Hard invariants:

- Cloud policy can narrow local authority but never widen it.
- Unknown actions fail closed.
- No arbitrary command route or remote shell.
- Hosted billing or control-plane failure must not disable safe local monitoring/remediation.
- Remediation changes require reading `agent/README.md`, `SECURITY.md`, and `ARCHITECTURE.md` first.

## Coordination with Hermes and other agents

- Before editing, run `git status --short --branch` and inspect relevant `.hermes/plans/` and `.deepagents/` notes.
- Treat existing uncommitted changes as owner or agent work. Do not overwrite, revert, reformat, stage, or move them unless explicitly asked.
- Prefer narrow edits to the requested files. Avoid drive-by refactors.
- Read and search the whole repository as needed. Use normal local development
  tools—shell, Git reads/diffs, Python/Node, package managers, tests, builds,
  linters, LSPs, MCPs, and disposable temp/cache artifacts. A write lease limits
  persistent edits, not context or verification.
- If work spans agents, leave a concise handoff in `.deepagents/HANDOFF.md` or the relevant `.hermes/plans/` file with:
  - objective
  - files touched
  - commands run and exact result
  - blockers or remaining gates
- Hermes coordinates integration and independently verifies completion. dcode,
  Codex, and Claude may implement or review as assigned; an agent that
  implemented a change cannot be its independent reviewer.
- Deepagents should proactively suggest system improvements and may implement
  them when they are inside the active objective/write lease.
- Do not create branches, pull requests, commits, pushes, deployments, DNS
  changes, Stripe actions, or production-impacting changes without explicit
  task authority. This gate must not block local implementation or tests.
- If Dustinn explicitly overrides the Hermes handoff workflow and asks Deepagents to ship, use the current branch and direct push; never rewrite history without explicit approval.

## Verification commands

Use the smallest relevant gate first, then expand before completion.

```bash
make agent-test
make agent-lint
make packaging-test
make contracts-validate
make cp-test
make cp-typecheck
make dashboard-build
```

Common direct commands:

```bash
python3 agent/tools/run_tests.py
ruff check agent/
python3 scripts/validate-contracts.py
npm --prefix control-plane test
npm --prefix control-plane run typecheck
npm --prefix control-plane run types:check
npm --prefix dashboard run build
```

## Secrets and external systems

- Never print, store, or commit secrets.
- `.env`, `.dev.vars`, keys, certificates, and credential files are local-only.
- Production surfaces and billing are gated; verify current reality in `STATUS.md` before making availability claims.
