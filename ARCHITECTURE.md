# AgentPulse Internal Architecture

This document is the canonical internal reference connecting AgentPulse's v1
remediation engine to the Ouroboros pillar framework (from the
[Sovereign-Ouroboros-OS](https://github.com/strouddustinn-bot/Sovereign-Ouroboros-OS)
research project). It is the **north-star architecture**, with an honest,
code-checked status per pillar.

**Rule for this document:** a stage is only marked `SHIPPED` if it exists in the
`agent/agentpulse/` code and is covered by the test suite. Everything else is
`ROADMAP`, even if the Ouroboros research repo prototypes it. Do not mark a
stage shipped because the vision describes it.

Lives alongside `README.md` and `SECURITY.md`. Not a docs-site page.

---

## Implemented loop (v1 agent, as built)

What the shipped agent actually does on every auto-fix, in `agentpulse/ouroboros.py`:

```
[IMAGINE] --> [SIMULATE] --> [VALIDATE] --> [EXECUTE] --> [VERIFY] --> [RECORD]
 expected      dry-run        ethos gate     real fix     re-measure   cycle log
 state                                                        |
                                              escalate to human if not cleared
```

The loop "eats its tail" through **VERIFY**: after acting, the agent re-measures
the same signal and, if the condition did not clear, **escalates to a human
instead of retrying**. There is no automatic re-loop on a failed fix — that is a
deliberate safety property, verified by `tests/test_ouroboros.py`.

The full closed feedback loop (writing outcomes back into a learned baseline) is
ROADMAP, not v1 — see Recall and Expand below.

---

## Pillars: status checked against the code

| # | Ouroboros pillar | AgentPulse role | Status | Real module |
|---|------------------|-----------------|--------|-------------|
| — | Recall (knowledge) | Baseline learning / history | **ROADMAP** | none yet |
| 1 | NeuroSynth (Imagine) | Name the expected end-state | **SHIPPED (minimal)** | `ouroboros._imagine` |
| 2 | ChronoWeave (Simulate) | Dry-run the fix first | **SHIPPED (as dry-run)** | `remediation.execute(dry_run=True)` |
| 3 | EthosCompiler (Validate) | Executable safety gate | **SHIPPED** | `ouroboros.ethos_gate`, `policy`, `remediation` guards |
| 4 | MetaMorph (Execute) | Run the validated fix | **SHIPPED (fixed actions)** | `remediation.disk_cleanup`, `service_restart` |
| — | Verify (the tail) | Re-measure, escalate | **SHIPPED** | `ouroboros.run_cycle` + `runner.make_verify` |
| 5 | MetaMorph (Evolve) | Skill synthesis/composition | **ROADMAP** | none yet |
| 6 | HiveMind (Expand) | Multi-server federation | **ROADMAP** | none yet |

---

## Stages (honest detail)

### Recall — ROADMAP
A learned baseline of a host's normal behavior and incident history. **Not in
v1.** The agent today is stateless about "normal": each cycle measures current
disk/service/memory against operator-set thresholds. The only persisted state is
the ask-first approval queue (`state.py`). RAG / BM25+dense retrieval described
in the research repo is not implemented here.

### 1. Imagine — SHIPPED (minimal)
`ouroboros._imagine()` produces a one-line expected end-state (e.g. "expect disk
on /var to drop below threshold after removing old files"). It is a single
expectation, not a set of ranked candidate strategies. ML-ranked candidates are
ROADMAP; the interface can carry them later without changing callers.

### 2. Simulate — SHIPPED (as dry-run)
Before any real change, `remediation.execute(dry_run=True)` produces the exact
plan — which files would be removed, which service would be restarted — without
touching the system. This is a deterministic dry-run, **not** multi-timeline
counterfactual scoring. Timeline diversity/scoring is ROADMAP.

### 3. Validate — SHIPPED
`ouroboros.ethos_gate()` plus the guards in `policy.py` and `remediation.py`
enforce hard, code-level safety predicates before execution: no system-path
sweeps, no auto process-kill, allowlisted services only, no action without a
successful dry-run. Per-action operator policy (off/alert/ask/auto) is evaluated
in `policy.decide()`. Covered by `test_policy.py`, `test_remediation.py`, and the
4,100-iteration fuzz suite in `test_fuzz.py`.

### 4. Execute — SHIPPED (fixed action set)
`remediation.execute()` runs the validated action from a **fixed** set:
`disk_cleanup` (age-bounded, glob-guarded file removal) and `service_restart`
(allowlisted systemd restart). There is **no** dynamic skill registry, synthesis,
or cosine-similarity composition in v1 — that is the Evolve roadmap item.

### Verify — SHIPPED
After execution, `runner.make_verify()` re-runs the relevant check. If the
condition cleared → `succeeded`. If not → `escalated` (notify a human; do not
retry). This is the safety backbone of autonomous operation and is explicitly
tested.

### 5. Evolve — ROADMAP
On-demand skill synthesis and composition within a bounded registry. **No
production code exists.** When built, the bounded-registry + LRU-eviction cap is
a required safety property.

### 6. Expand — ROADMAP
Multi-server federation (e.g. GF(256) secret-shared pattern sharing across
nodes). **No production code exists.** This is where anonymized, consenting
production telemetry would later feed a shared baseline — the legitimate ML data
path, distinct from the test suite.

---

## Public vocabulary

User-facing copy uses plain words; this doc and code use the loop's stage names.
Keep them consistent with the **shipped** loop:

| Public term (site/copy) | Loop stage | Status |
|-------------------------|-----------|--------|
| (plan) | Imagine | shipped (minimal) |
| Simulate / dry-run | Simulate | shipped |
| Safety gate | Validate | shipped |
| Fix / act | Execute | shipped |
| Verify / escalate | Verify | shipped |
| Learn across servers | Expand | roadmap |
| Remember normal | Recall | roadmap |

Do not describe Recall, Evolve, or Expand as available in user-facing copy until
they ship. Current site copy (README, `docs/index.md`, `docs/install.md`) is
aligned to the shipped loop only.

---

## Roadmap priority

1. **Recall / baseline** — gives the agent a notion of "normal" so detection
   isn't purely threshold-based. Highest product leverage.
2. **Simulate depth** — richer consequence modeling to cut false-positive
   auto-fixes.
3. **Evolve / Expand** — dynamic skills and fleet federation; largest builds,
   sequenced last.

Until those ship, v1 stands on its own as an honest, tested, single-host agent:
fixed actions, hard safety guards, dry-run + verify on every change.
