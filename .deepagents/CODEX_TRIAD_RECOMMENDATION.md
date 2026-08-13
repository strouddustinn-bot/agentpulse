# Recommendation for Hermes Review: Add Codex as Adversarial Inference Reviewer

## Recommendation

Adopt a three-agent operating model for high-risk AgentPulse work:

```text
Deepagents: local implementation + verification + handoff
Codex: adversarial code/design review + test-gap discovery
Hermes: final decision + commit + push + release
```

This should start as a process-only workflow. Do not add automation, scripts, CI requirements, or repository policy until Hermes validates the loop manually.

## Why this helps AgentPulse

AgentPulse has safety-critical boundaries:

- local agent authority must not be widened by the cloud;
- unknown actions fail closed;
- no arbitrary command route or remote shell;
- browser sessions need secure cookie, CSRF, origin, rotation, and revocation behavior;
- Stripe webhooks and account claims must be idempotent under replay, duplicates, and out-of-order events;
- contracts should remain the source of truth for Worker behavior.

Codex is useful as an inference-only adversary before Hermes ships: it can attack assumptions, inspect diffs, suggest missing tests, and check conformance without owning the repo or release authority.

## Proposed responsibilities

### Deepagents

- Implement requested changes locally only.
- Run the smallest relevant verification gates, then expanded gates when appropriate.
- Produce a concise handoff with files changed, commands run, exact results, and remaining risks.
- Suggest system-improving plays, but do not implement those suggestions unless asked.

### Codex

- Review Deepagents' local diff and handoff.
- Return findings in priority order:
  - blocker correctness/security issues;
  - missing tests;
  - contract/source mismatches;
  - edge cases;
  - optional design improvements.
- Avoid direct edits unless Hermes explicitly asks Codex to produce a patch.

### Hermes

- Decide which findings matter.
- Apply or request changes.
- Own commit, push, release, deployment, and production-gated actions.

## First use case

Use Codex review before Hermes ships AgentPulse control-plane/session/billing work, especially changes touching:

- `control-plane/src/index.ts`
- `control-plane/test/*billing*`
- `control-plane/test/*session*`
- `control-plane/migrations/*.sql`
- `packages/contracts/openapi.yaml`
- `scripts/validate-contracts.py`
- dashboard browser-session consumers once Tier 3 starts

## Suggested manual protocol

1. Deepagents finishes local work and writes `.deepagents/HANDOFF.md` entry.
2. Hermes or Dustinn starts Codex with the review prompt below.
3. Codex returns structured findings.
4. Hermes decides:
   - accept as-is;
   - ask Deepagents to patch locally;
   - patch himself;
   - defer as tracked risk.
5. Hermes commits/pushes/releases if appropriate.

## Codex review prompt template

```text
You are reviewing AgentPulse, a local-first server-remediation platform.

Repo path: /home/desktopdusty/workspace/repos/agentpulse

Operating model:
- Deepagents implemented and verified locally.
- Codex is an adversarial reviewer only.
- Hermes owns final decision, commit, push, and release.

Product invariants:
- Cloud policy can narrow local authority but never widen it.
- Unknown actions fail closed.
- No arbitrary host command route or remote shell.
- Billing/control-plane failure must not disable safe local monitoring/remediation.
- Browser sessions require secure cookie behavior, CSRF, trusted Origin checks, rotation/revocation, and server-derived tenant identity.
- Stripe webhook and claim flows must be idempotent under duplicate, replayed, and out-of-order events.
- OpenAPI/contracts are source of truth.

Review inputs:
1. git diff
2. Deepagents handoff
3. relevant STATUS.md / AGENTS.md / SECURITY.md sections
4. verification command output

Return:
- Verdict: ship / do not ship / ship with risks
- Blockers
- High-risk issues
- Missing tests
- Contract/source mismatches
- Security concerns
- Suggested follow-up plays for Hermes

Do not invent command results. If something was not verified, say so.
```

## Recommended acceptance criteria for the triad

The triad is working if:

- Hermes gets smaller, clearer review decisions.
- Deepagents avoids owning release authority.
- Codex catches at least one real missing test, invariant risk, or contract mismatch over several reviews.
- Handoffs become good enough that any of the three agents can resume without stale assumptions.

## Non-goals for now

- No mandatory CI gate yet.
- No automatic Codex invocation yet.
- No secret exposure to Codex prompts.
- No production/deployment authority for Codex or Deepagents.
