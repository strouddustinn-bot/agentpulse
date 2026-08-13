# CLAUDE.md

**Read `AGENTS.md` first — it is the authoritative operating guide for this
repository.** This file exists only so Claude Code picks that up automatically;
it deliberately does not restate the contents, to avoid the two drifting apart.

`AGENTS.md` covers: canonical paths, the product boundary and its hard
invariants (cloud policy can narrow local authority but never widen it; unknown
actions fail closed; no arbitrary command route), multi-agent coordination
rules, verification commands, and secret handling.

## Claude Code's role here

Claude Code is a general coding agent. The active assignment determines whether
it implements, debugs, tests, documents, or performs an independent coherence
review. Reviews are read-only against the judged artifact; implementation tasks
may edit their assigned scope and use the full local toolchain.

- Hermes coordinates integration and independently verifies completion.
- Claude must not independently review work it implemented.
- Before any approved edit: `git status --short --branch`, then inspect
  `.hermes/plans/` and `.deepagents/` for in-flight work. Never overwrite,
  revert, reformat, or stage someone else's uncommitted changes.
- Broad repository reading, shell, Git inspection/diff, tests, builds, package
  managers, LSPs, MCPs, and disposable temp/cache artifacts are normal local
  capabilities. Only consequential external effects require an explicit gate.

## Verification

Smallest relevant gate first, then expand:

```bash
make agent-test          # local Python agent
make agent-lint
make cp-test             # Cloudflare Worker control-plane
make cp-typecheck
make contracts-validate
make dashboard-build
```

Layout: Python agent (`agent/`), TypeScript Cloudflare Worker control-plane
(`control-plane/`, wrangler + vitest), React dashboard (`dashboard/`), shared
contracts (`packages/contracts/`). Verify current production/billing reality in
`STATUS.md` before making any availability claim.
