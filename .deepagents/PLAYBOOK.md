# AgentPulse Deepagents Playbook

## Start every session

1. Read `AGENTS.md`, `STATUS.md`, and any active `.hermes/plans/*` relevant to the task.
2. Run:

```bash
git -C "/home/desktopdusty/workspace/repos/agentpulse" status --short --branch
git -C "/home/desktopdusty/workspace/repos/agentpulse" worktree list --porcelain
```

3. Identify whether changes are already in progress by Dustinn, Hermes, or another agent.

## Pick highest-impact work

Prioritize in this order unless Dustinn names a task:

1. Failing verification gates blocking release.
2. Security or safety invariant regressions.
3. Staging lifecycle proof blockers listed in `STATUS.md`.
4. Contract/source mismatches.
5. Documentation truth gaps that could mislead operators or customers.

## Work rules

- Local-only unless explicitly approved.
- Hand completed work to Hermes for commit, push, and release by default.
- Smallest coherent diff.
- No unrelated formatting.
- No dependency changes unless required and verified.
- No production/cloud/billing mutation without explicit gate approval.
- Keep Hermes useful by leaving exact command outputs and next steps.

## Completion report

Report:

- outcome
- files changed
- verification performed with real results
- remaining risks or gates
