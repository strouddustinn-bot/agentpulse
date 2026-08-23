# Production Synthetic Watch

## Purpose

The Production Synthetic Watch is a zero-secret, read-only external check of the
bounded AgentPulse production surface. It runs from GitHub Actions independently
of Cloudflare's serving path and creates a durable GitHub incident record when
its checks fail.

It does **not** deploy, migrate D1, create a Stripe Checkout Session, enroll an
agent, change billing, or execute host remediation.

## Workflow

- File: `.github/workflows/production-watch.yml`
- Schedule: four times per hour (`7,22,37,52` minutes past the hour)
- Manual trigger: supported through `workflow_dispatch`
- Incident title: `[ops] AgentPulse production synthetic alert`
- Expected production release: `v0.2.0-beta.8`
- Expected deployed source: `9d128c054ba9c5c6e985610fe725e7b8069f3e1b`
- Expected API/package identity: `0.2.0b6`

The expected identity is deliberately fixed to the last recovery-verified
production release. A later production release must update these values through
reviewed source rather than silently following `master`.

## What it checks

The watch reuses `scripts/production-smoke.py` to verify:

- the real production console shell and `/account` route;
- the exact `deployment.json` source/version/API identity;
- the production JavaScript artifact SHA-256;
- the production API health identity;
- trusted credentialed CORS;
- absence of CORS grants for fixed untrusted, staging, and local origins;
- unauthenticated account access failing closed.

It additionally verifies:

- `https://agentpulse.ca/` returns HTTP 200 at the canonical URL and contains the
  current public product marker;
- an invalid `enterprise` plan returns the exact `422 invalid_plan` boundary;
- Pro checkout returns the exact `404 not_found` boundary;
- Business checkout returns the exact `404 not_found` boundary.

The watch **never submits `starter`**. The three checkout probes are selected
specifically because the current Worker rejects them before Stripe session or D1
checkout creation. Their response bodies are validated from temporary files and
are not printed to workflow logs.

## Failure behavior

The synthetic step is allowed to finish its evidence collection before the job
is marked failed. If any check fails:

1. the workflow looks for one open issue with the exact incident title;
2. if none exists, it creates it;
3. if one already exists, it adds a new occurrence comment instead of creating
   duplicates;
4. the issue contains only the check time, expected release/source/version,
   whether the failure was simulated, and the GitHub run URL;
5. the workflow then exits non-zero so GitHub visibly records the failed run.

Do not place HTTP response bodies, credentials, customer identifiers, server
hostnames, Stripe payloads, or Cloudflare tokens into the incident issue.

## Recovery behavior

On a later healthy run, the workflow finds the exact open incident issue, adds a
recovery comment containing the healthy run URL and verified release identity,
and closes the issue as completed. If no incident is open, the healthy run makes
no issue mutation.

A closed incident remains a durable historical record and must not be deleted as
routine housekeeping.

## Operator response

When `[ops] AgentPulse production synthetic alert` opens:

1. Open the linked GitHub Actions run.
2. Identify the first `BLOCK` or failed boundary. Do not infer a provider outage
   from an unrelated local connectivity failure.
3. Compare the observed failure with the last verified production identity in
   `STATUS.md` and the latest protected production deployment evidence.
4. If the API or console identity changed unexpectedly, treat it as source or
   deployment integrity drift and stop public promotion work.
5. If the service is unreachable, inspect provider state and recovery evidence
   before changing DNS, Worker routes, Pages deployments, or D1.
6. If checkout boundaries widened unexpectedly, treat that as a billing safety
   incident. Do not create a real checkout to investigate it.
7. Production mutation must still go through the protected
   `.github/workflows/production-deploy.yml` path and its owner approval gate.

A later green watch will close the GitHub incident automatically, but the root
cause and any corrective work should still be recorded in the relevant issue or
PR.

## Safe alert-path drill

`workflow_dispatch` exposes a `simulate_failure` boolean. When true, the workflow
runs the real read-only checks first and then deliberately marks the synthetic as
failed. Production itself is not altered.

Acceptance drill:

1. manually run `Production Synthetic Watch` with `simulate_failure=true`;
2. verify the workflow turns red and the dedicated incident issue is created or
   updated with `simulated_failure: true`;
3. manually run it again with `simulate_failure=false`, or allow the next
   scheduled healthy run;
4. verify the incident receives a recovery comment and closes.

This drill proves GitHub-side alert recording and recovery tracking without
breaking AgentPulse production.

## What this watch does not prove

This is one Tier 4 observability layer, not the entire observability gate. It does
not by itself prove:

- Cloudflare-native account alert delivery;
- Worker 5xx threshold notification delivery;
- Stripe webhook failed/backlog threshold alerting;
- heartbeat-ingestion or stale-host alerting;
- D1 error-rate alerting;
- the customer-facing status/incident communication path;
- tenant retention/deletion execution.

Those remain separate operational gates. Do not mark Tier 4 complete from this
watch alone.
