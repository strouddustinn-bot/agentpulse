# Production readiness preflight (Tier 4 / Phase 5A)

## Purpose and authority boundary

`scripts/production-preflight.py` is a **read-only, fail-closed prerequisite** for production deployment work. It performs no Cloudflare, GitHub, DNS, Stripe, D1, migration, billing, secret, or deployment mutation.

A passing preflight does not authorize production deployment. Owner Gate 5 still controls production resource creation, secret placement, DNS approval, email-routing confirmation, and production deployment approvers.

## Checks

The preflight aggregates blockers instead of stopping at the first one:

1. `control-plane/wrangler.jsonc` has a production Worker name, a structurally valid non-placeholder D1 UUID, canonical HTTPS API/app URLs, explicit version, all three plausible non-placeholder external Price IDs, and the `api.agentpulse.ca` custom domain.
2. The requested release reference is immutable and resolves to the exact checked-out commit: a version tag such as `v0.3.0` or a full 40-character commit SHA. Branch names, short SHAs, nonexistent refs, and refs to another local commit fail.
3. GitHub has a `production` environment with at least one named required reviewer and a custom deployment policy allowlisting the exact immutable release tag. Empty/mutable policies fail; protected-branch mode alone does not prove that a full-SHA deployment event is admitted and therefore fails closed.
4. `app.agentpulse.ca` and `api.agentpulse.ca` resolve through a public DNS-over-HTTPS resolver to globally routable IP addresses.
5. The release workflow remains immutable-tag and artifact-only, contains the Phase 5A verifier suite, and rejects production mutation markers before Owner Gate 5. The Phase 5A runbooks retain the migration, rollback, and smoke sequence for the separately reviewed production workflow that may be added only after the gate.

This first checkpoint does not yet prove that structurally valid resource IDs exist in Cloudflare/Stripe, migrations have executed, secret-name compatibility is complete, TLS/application health is proven, immutable Worker/Pages identity is live, smoke tests/rollback/D1 export are executed, or observability is operational. Those remain later Phase 5A/5B checks.

## Run it

From the AgentPulse repository root:

```bash
./scripts/production-preflight.py --release-ref v0.3.0
```

The live GitHub-environment proof is tag-bound. A full commit SHA remains valid for exact source-identity and `--static-only` checks, but protected-branch mode does not by itself prove that the production deployment event is bound to that SHA.

For source-only development checks:

```bash
./scripts/production-preflight.py --release-ref "$(git rev-parse HEAD)" --static-only
```

`--static-only` deliberately labels live checks `SKIPPED_NON_GATING`; it must never be used as production-readiness evidence.

## Expected output

Blocked example:

```text
PRODUCTION_PREFLIGHT=BLOCKED
LIVE_CHECKS=CHECKED
[BLOCK] production_d1_placeholder: ...
```

Passing example:

```text
PRODUCTION_PREFLIGHT=PASS
LIVE_CHECKS=CHECKED
No deployment, migration, DNS, billing, or secret mutation was performed.
```

Do not suppress, downgrade, or convert blocker findings to warnings in a deployment workflow.

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_production_preflight -v
```

The suite covers the current placeholder production configuration, a complete synthetic configuration, shaped fake resource IDs, malformed JSONC structures, immutable-reference shape/existence/current-checkout binding, missing/malformed GitHub environments, timed-out provider checks, named reviewers, exact-tag custom policies, unresolved DNS, and non-public addresses.

## Resume sequence

After this preflight is wired into a protected immutable-ref workflow, continue Phase 5A in dependency order:

1. migration status and redacted preflight;
2. explicit migration approval and apply path;
3. Worker deploy by immutable release;
4. production console deploy;
5. API/console/site smoke tests;
6. Worker/console rollback receipt;
7. D1 export and tested restore procedure;
8. operational alerting and data-lifecycle runbooks.

Keep public checkout closed throughout Tier 4 and the controlled pilot gate.
