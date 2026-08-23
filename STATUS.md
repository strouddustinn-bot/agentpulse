# AgentPulse Status

**Status date:** 2026-08-22  
**Canonical GitHub branch:** `master`  
**Canonical source commit:** `9d128c054ba9c5c6e985610fe725e7b8069f3e1b`  
**Production release tag:** `v0.2.0-beta.8`  
**Runtime/package identity:** `0.2.0b6`

## Current product state

AgentPulse is a local-first server monitoring and bounded-remediation platform.
The local agent remains authoritative for host actions. Cloud policy can narrow,
but cannot increase, the local authority ceiling.

```text
Observe → Reason → Simulate → Gate → Act → Verify → Record or Escalate
```

Unknown actions fail closed. Remediation remains allowlisted, simulated,
policy-gated, verified, and recorded. The dashboard presents evidence and does
not expose arbitrary remote commands or unrestricted remote shell access.

## Canonical repository layout

```text
agent/                    dependency-light local monitoring/remediation agent
control-plane/            Cloudflare Worker + D1 hosted authority
dashboard/                React fleet, incident, account, and enrollment console
packages/contracts/       canonical OpenAPI, JSON Schema, and fixtures
configs/                  agent schema and safe policy examples
scripts/                  verification, packaging, deployment, and recovery tooling
docs/                     product, pricing, legal, support, and runbooks
```

Historical source retention is governed by `ARCHIVES.md`. Confidential
operational evidence is not published; deletion requires an owner-approved
retention gate.

## Verified source state

The beta.8 source was reviewed in PR #42 and merged to `master` at
`9d128c054ba9c5c6e985610fe725e7b8069f3e1b`.

Applicable PR checks passed before merge:

- Production Readiness, including the production recovery regression;
- full Tests matrix, including Python 3.10–3.13 agent/package coverage;
- Windows package, CLI, and service lifecycle;
- contracts and migration validation;
- Worker tests, type checks, and generated type checks;
- dashboard tests, production build, and mocked Playwright E2E;
- dependency audits, verified-secret scanning, and repository hardening.

The `v0.2.0-beta.8` tag resolves exactly to the reviewed merge commit. Package
and production API identity intentionally remain `0.2.0b6`: beta.8 changes the
release/recovery workflow only and does not change the application payload.

## Production deployment reality

**Bounded Starter production activation: VERIFIED.**

Protected production workflow:

- workflow: `.github/workflows/production-deploy.yml`;
- run: `32607273507`;
- immutable release: `v0.2.0-beta.8`;
- source SHA: `9d128c054ba9c5c6e985610fe725e7b8069f3e1b`;
- package/API version: `0.2.0b6`;
- protected `production` environment approval required and received;
- both `Verify immutable release candidate` and `Deploy controlled pilot`
  completed successfully.

The protected workflow demonstrated, in order:

1. immutable tag/source/package binding and verified-secret scan;
2. agent, contracts, packaging, Worker, dashboard, and hardening verification;
3. exact dashboard artifact preservation;
4. production provider-state capture;
5. live fail-closed preflight with DNS and Stripe live-price verification;
6. pre-migration D1 export plus local parse/restore test;
7. production migration check (`No migrations to apply` on beta.8);
8. production Worker deployment;
9. exact production dashboard artifact deployment;
10. external production smoke against the real console and API;
11. Starter-only checkout boundary verification without creating a live Stripe
    Checkout Session or D1 checkout row;
12. disposable D1 creation, import of the production backup, verification,
    deletion, and cleanup verification;
13. saved-version Worker recovery rehearsal at 100% traffic;
14. immutable console artifact recovery rehearsal;
15. a second external production smoke after the recovery rehearsal;
16. redacted deployment evidence and the initial D1 recovery export upload.

### External production smoke evidence

The workflow's external runner verified:

- `https://app.agentpulse.ca` serves the real built console shell;
- account and deployment routes serve the expected console;
- deployment manifest source identity matches the exact beta.8 source SHA;
- the main JavaScript artifact matches its recorded SHA-256;
- the console binds only the production API origin expected by the artifact;
- `https://api.agentpulse.ca/health` responds with the expected production
  identity (`0.2.0b6`);
- trusted production CORS is credentialed;
- untrusted, staging, and local origins receive no CORS grant;
- unauthenticated account access fails closed;
- checkout mode is `starter`;
- an invalid plan returns the expected validation failure;
- Pro and Business checkout routes fail closed with `404 not_found`;
- no billable checkout was created by the smoke probes.

Both the initial post-deploy smoke and the post-recovery-rehearsal smoke passed
on the first attempt.

### Recovery evidence

The beta.8 deployment record reports:

```text
deployment_status=verified
next_action=none
d1_disposable_restore=pass
disposable_d1_deleted=true
worker_saved_version=pass
console_immutable_artifact=pass
production_smoke=pass
```

GitHub Actions evidence retained for the run:

- redacted production deployment evidence: artifact `9484511531`,
  SHA-256 `347b36c1ad2a8312ee7d5d201f342f06779297d2462f577cab544c8c010eb8ec`;
- pre-mutation D1 recovery export: artifact `9484511778`,
  SHA-256 `a4e7e3b40e97e96aa4cb44fd99ea76e4fdd69dd2d69b76f685391d2c848561c6`;
- verified dashboard artifact: artifact `9484469942`,
  SHA-256 `6365e9c7990e3e77e468f5c71949d2ae2a2486046eecbdbc500925ed4fafc2f2`.

Recovery evidence is intentionally retained outside the repository working tree
so downstream failure does not destroy the evidence needed to recover.

## Checkout and launch boundary

Production is **not** an unrestricted public multi-host launch.

Current production billing authority is deliberately bounded:

| Plan | Production state | Host limit |
|---|---|---:|
| Starter | checkout runtime enabled | 1 |
| Pro | checkout blocked; reservation/interest only | 5 when later authorized |
| Business | checkout blocked; reservation/interest only | 20 when later authorized |

The Worker uses `CHECKOUT_MODE=starter`. Unknown Stripe Price identities deny
entitlement. Cloud policy cannot expand local remediation authority.

A real paid Starter purchase has **not** been created merely to prove the
release. Actual payment/demand validation is a separate commercial gate and
must not be confused with the non-billable production smoke probes.

Public multi-host checkout remains closed until the controlled-pilot,
host-limit, operational, and go-live gates are satisfied and explicitly
approved.

## Staging evidence retained

Staging previously demonstrated the end-to-end test-mode lifecycle:

```text
checkout → claim → browser session → account → enrollment token →
host enrollment → heartbeat → fleet visibility → logout/portal controls
```

The browser flow uses cookie sessions and CSRF protection; browser bearer and
claim material are not retained in JavaScript storage. The local agent remains
useful when the hosted control plane is unavailable.

## Release recovery history

- `v0.2.0-beta.6` failed closed before production mutation because the verified
  dashboard artifact contained an unapproved absolute URL origin.
- `v0.2.0-beta.7` corrected that artifact and successfully deployed/live-smoked,
  but its recovery workflow false-failed after a successful disposable D1
  restore because the workflow's own generated redacted evidence file made the
  checkout appear dirty.
- PR #42 fixed that recovery-proof defect without weakening the strict
  working-tree guard. `v0.2.0-beta.8` then completed deployment, disposable D1
  restore/delete, Worker recovery, console recovery, final smoke, and evidence
  preservation successfully.

Beta.6, beta.7, and beta.8 remain immutable release evidence and must not be
moved or reused.

## Supported boundary

The agent remains locally authoritative and useful during control-plane
outages. Modes remain `off`, `alert`, `ask`, and `auto`. Dry-run remains
explicit and testable. Failed verification escalates once; no uncontrolled
retry loop is allowed. No arbitrary remote command execution is part of the
supported product.

## Remaining gates

The protected beta.8 production release and recovery proof are complete. The
next work is operational and commercial validation rather than another release
retry.

Still required before broad public multi-host self-serve launch:

- controlled-pilot operation on approved non-critical hosts;
- validation of the actual alert/notification path under real failure
  conditions;
- production operational monitoring, incident/status communication, and
  customer-contact readiness;
- executable retention/deletion and recovery runbook evidence accessible during
  an outage;
- real Starter demand/payment validation under an explicitly approved
  commercial test;
- host-limit revalidation before any Pro or Business checkout authority is
  enabled;
- explicit go-live approval before broad public launch.

Production mutation remains restricted to the protected
`.github/workflows/production-deploy.yml` path.