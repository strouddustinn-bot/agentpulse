# AgentPulse Internal Architecture

This document is the canonical internal reference connecting AgentPulse's decision engine to the Ouroboros 6-pillar framework. It defines shared vocabulary for engineers, product, and writers, and tracks implementation status per pillar.

Not a docs site page. Lives alongside README.md and SECURITY.md.

---

## Decision Loop

The agent does not execute a linear chain. Each cycle is a closed loop — execution outcomes feed back into Recall, updating the baseline for the next run.

```
  +----------------------------------------------------------+
  |                                                          |
  v                                                          |
[RECALL] --> [IMAGINE] --> [SIMULATE] --> [VALIDATE] --> [EXECUTE/EVOLVE] --> [EXPAND]
                                                                                  |
                                            feedback to RECALL <------------------+
```

Read left to right for a single cycle. The rightmost arrow wrapping back to RECALL is what makes this an ouroboros rather than a pipeline.

---

## Stages

### 1. Recall
**Ouroboros pillar:** `ouroboros/knowledge/`
**AgentPulse component:** Baseline learning engine
**Status:** SHIPPED

Before reasoning begins, the agent queries the hybrid RAG knowledge base (BM25 + dense CharNGram retrieval, fused via Reciprocal Rank Fusion) to retrieve grounding context from ingested documents. In AgentPulse terms, this is the accumulated operational history of a monitored environment: past incidents, remediation outcomes, drift events, and anomaly patterns. Every new task starts with this grounding step, not a blank slate.

---

### 2. Imagine
**Ouroboros pillar:** `ouroboros/neurosynth/`
**AgentPulse component:** Remediation candidate planning
**Status:** SHIPPED (discrete ruleset today; ML-ranked candidates on roadmap)

Takes the current task and recalled context and produces a set of candidate remediation approaches. Today this is driven by a discrete ruleset that enumerates known fix strategies per issue type. The architecture slot is reserved for the full neurosynth model, which synthesizes k distinct prototypes by fusing per-modality latent vectors across multiple conceptual framings (direct, analogical, decompositional). The interface contract between Imagine and Simulate is stable; the underlying generator is swappable.

---

### 3. Simulate
**Ouroboros pillar:** `ouroboros/chronoweave/`
**AgentPulse component:** Consequence modeling
**Status:** IN PROGRESS

For each candidate produced by Imagine, Simulate spawns counterfactual timelines — optimistic, cautious, and reckless projections — scores them by alignment + confidence minus risk penalty, and collapses to the single best proposed action. In AgentPulse terms, this is the layer that answers "if we run this auto-fix, what probably happens next?" before anything touches a production system. The scoring function and timeline collapse logic are under active development.

---

### 4. Validate
**Ouroboros pillar:** `ouroboros/ethos_compiler/`
**AgentPulse component:** Approval gates (auto-fix / ask-first / alert-only)
**Status:** SHIPPED

Compiles natural-language ethical and operational principles into executable Python predicates at boot time, then gates every proposed action before it runs. In AgentPulse terms, this enforces the per-server, per-action-class approval policy configured by the operator. An action that would auto-fix a low-risk disk issue on a dev server may require human confirmation on a production database node — Validate is where that policy is evaluated, not at the UI layer.

---

### 5. Execute / Evolve
**Ouroboros pillar:** `ouroboros/metamorph/`
**AgentPulse component:** Auto-remediation engine + custom skill registry
**Status:** SHIPPED (core engine); ROADMAP (on-demand skill synthesis, skill composition)

Runs the validated action using a registered skill. If no skill matches the required action, the engine synthesizes one on-demand and hot-swaps it into the bounded registry. When two existing skills are sufficiently similar (cosine similarity > 0.35), the engine composes them rather than generating from scratch. In AgentPulse terms, the shipped surface is the auto-remediation engine with a fixed skill library. The Evolve capability — dynamic synthesis and composition — is the primary near-term engineering roadmap item.

---

### 6. Expand
**Ouroboros pillar:** `ouroboros/hivemind/`
**AgentPulse component:** Multi-server federated intelligence
**Status:** ROADMAP

Distributes the completed task and its outcome across sovereign peer nodes using GF(256) XOR secret sharing; results are aggregated as federated consensus. In AgentPulse terms, this enables a fleet of AgentPulse instances — each with its own Recall — to share learned patterns without centralizing raw telemetry. No single node holds the full picture; the federation holds it collectively.

---

## Vocabulary

Public-facing documentation uses simplified names. Internal code and this document use Ouroboros names. The mapping:

| Public term | Ouroboros pillar | Internal module |
|-------------|-----------------|-----------------|
| Remember    | Recall          | `ouroboros/knowledge/` |
| Reason      | Imagine         | `ouroboros/neurosynth/` |
| Simulate    | Simulate        | `ouroboros/chronoweave/` |
| Gate        | Validate        | `ouroboros/ethos_compiler/` |
| Act         | Execute/Evolve  | `ouroboros/metamorph/` |
| Share       | Expand          | `ouroboros/hivemind/` |

When writing user-facing copy, use the public terms. When writing code, ADRs, or internal specs, use the Ouroboros names. Do not use both in the same sentence.

---

## Roadmap Alignment

Three pillars drive the active engineering roadmap:

**Simulate depth (`ouroboros/chronoweave/`)**
The consequence modeling layer is partially implemented. Expanding timeline diversity, improving the scoring function, and validating collapse accuracy against historical incident data are the primary work items. This is the highest-leverage investment: better simulation directly reduces false-positive auto-fixes.

**Expand / hivemind (`ouroboros/hivemind/`)**
Multi-server federated intelligence is the largest architectural addition on the roadmap. It requires finalized node identity, the GF(256) secret-sharing transport, and a consensus aggregation protocol that degrades gracefully when nodes are offline. No production code exists yet.

**Evolve / custom skills (`ouroboros/metamorph/`)**
On-demand skill synthesis and skill composition within the metamorph registry are scoped for the cycle after Simulate stabilizes. The shipped auto-remediation engine uses a static skill library; Evolve replaces that static library with a dynamic, self-extending registry. The bounded registry constraint (hard cap on registered skills, LRU eviction) is a deliberate safety property and must be preserved through the Evolve implementation.

---

## Feedback Loop

Execution outcomes — what ran, what changed, whether the remediation succeeded or was rolled back — are written back into the Recall layer at the end of each cycle. This updates the baseline used by the next Recall query. The loop is closed by design. AgentPulse does not treat each incident as an isolated event; it treats the history of all incidents as the training signal for handling the next one.
