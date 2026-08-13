# Recommendation for Hermes Review: Four-Agent Council

## Recommendation

Adopt a four-agent operating model for high-risk AgentPulse work:

```text
Deepagents: local implementation + verification + handoff
Codex: adversarial code/design review + test-gap discovery
Claude: planning, architecture, documentation, and product-consistency review
Hermes: final decision + commit + push + release
```

Start as a manual process. Do not add automation, CI requirements, scripts, or repository policy until Hermes validates the loop.

## Why add Claude

Claude is useful as a planning and synthesis reviewer, especially when the work needs coherence across product, docs, architecture, and operator-facing guarantees.

Use Claude for:

- architecture and product-boundary review;
- long-form plan review before implementation;
- documentation truth checks against `STATUS.md`, `README.md`, `ARCHITECTURE.md`, and `SECURITY.md`;
- release-note and operator-message clarity;
- spotting inconsistencies between business claims, safety boundaries, and implementation state.

Do not use Claude as a shipper by default. Hermes remains the release authority.

## Role boundaries

### Deepagents

- Implement requested changes locally only.
- Run real verification.
- Produce concise handoffs with files touched, command outputs, risks, and next steps.
- Suggest improvement plays without implementing optional improvements unless asked.

### Codex

- Attack the local diff and implementation assumptions.
- Prioritize correctness, security, edge cases, missing tests, contracts, migrations, sessions, billing, and safety-critical behavior.
- Return structured findings; avoid direct edits unless Hermes requests a patch.

### Claude

- Review plans, architecture, documentation, product language, and release coherence.
- Check whether claims match verified status.
- Identify stale docs, ambiguous operator guidance, or mismatched project boundaries.
- Suggest clearer sequencing and decision gates.
- Avoid direct edits unless Hermes asks Claude to draft text.

### Hermes

- Decide which findings matter.
- Assign follow-up work to Deepagents, Codex, Claude, or himself.
- Own commit, push, release, deployment, and production-gated actions.

## Suggested routing

Use the right reviewer for the risk:

| Work type | Primary reviewer | Secondary reviewer |
|---|---|---|
| Billing/session/security code | Codex | Claude for product/docs claims |
| Agent remediation safety | Codex | Claude for architecture boundary |
| OpenAPI/contracts/migrations | Codex | Claude for operator-facing consistency |
| README/STATUS/docs/pricing/legal | Claude | Codex only if docs imply technical behavior |
| Release readiness | Claude | Codex for diff/test-risk review |
| Workflow/process upgrades | Claude | Codex if scripts or enforcement are proposed |

## Manual protocol

1. Deepagents performs local implementation and verification.
2. Deepagents writes `.deepagents/HANDOFF.md` entry.
3. Hermes chooses review route:
   - Codex for adversarial code/test/security review;
   - Claude for plan/docs/architecture/product coherence;
   - both for release-critical work.
4. Hermes decides what to accept, defer, or send back for changes.
5. Hermes commits, pushes, deploys, or releases if appropriate.

## Codex prompt summary

Ask Codex:

```text
Review this diff adversarially for correctness, security, missing tests, contract/source mismatches, and edge cases. Hermes owns ship decision. Do not invent command results.
```

## Claude prompt summary

Ask Claude:

```text
Review this AgentPulse plan/diff/handoff for architecture coherence, documentation truth, product-boundary consistency, stale claims, and release-readiness clarity. Hermes owns ship decision. Do not invent verification results.
```

## Acceptance criteria

The four-agent council is useful if:

- Hermes gets clearer final decisions, not more noise.
- Codex catches implementation/test/security risks.
- Claude catches plan/docs/status/product-boundary inconsistencies.
- Deepagents stays focused on local execution and verified handoff.
- No agent except Hermes gains default commit/push/release authority.

## Non-goals

- No automatic invocation yet.
- No mandatory CI gate yet.
- No secrets in prompts.
- No production authority for Deepagents, Codex, or Claude.
