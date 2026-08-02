# Production deploy and rollback (Tier 4 / Phase 5A)

## Authority boundary

This runbook defines the fail-closed sequence for the first AgentPulse production Worker and console deployment. It is not deployment authorization. Stop before any provider mutation until Owner Gate 5 has approved the production resources, protected GitHub environment, secret placement, DNS rows, email-routing destination, and deployment approvers.

Keep public checkout closed throughout Tier 4 and the controlled pilot. Never print secret values, Stripe capability URLs, checkout sessions, claim nonces, enrollment tokens, or tenant data into logs or receipts.

## Required immutable inputs

A protected workflow must derive—not accept as unrelated free text—the following values from one approved immutable release tag:

- `RELEASE_REF`: exact tag such as `v0.3.0`;
- `SOURCE_SHA`: full 40-character commit resolved from that tag;
- `VERSION`: package version embedded by that release;
- production Worker name and Pages project/production branch;
- previous healthy Worker version ID and previous immutable console artifact.

Do not deploy from `master`, a short SHA, a mutable branch, a dirty checkout, or a workflow-dispatch version string that is not bound to the checked-out tag.

## Hard prerequisites

All must be true before the protected environment may admit a mutation job:

1. `scripts/production-preflight.py --release-ref "$RELEASE_REF"` exits zero with live checks enabled.
2. `control-plane/wrangler.jsonc` contains the approved production D1 UUID, all three approved live Price IDs, canonical production origins, an explicit matching version, and the `api.agentpulse.ca` custom domain.
3. The GitHub `production` environment has at least one named required reviewer and an exact-tag deployment policy.
4. Cloudflare/Stripe credentials exist only in approved external secret stores. Validate names and bindings without reading or printing values.
5. `app.agentpulse.ca` and `api.agentpulse.ca` resolve publicly; the production Pages project and its production branch are verified.
6. The migration plan, D1 export/restore procedure, and previous Worker/console rollback targets are recorded before mutation.
7. Canonical tests, contracts, type checks, dashboard build, audit, and secret scan pass at `SOURCE_SHA`.

A missing prerequisite is a blocker, never a warning or an invitation to substitute staging resources.

## Pre-mutation receipt

Capture redacted evidence in the protected job before approval:

```bash
set -euo pipefail
git rev-parse HEAD
git rev-parse "${RELEASE_REF}^{commit}"
test -z "$(git status --porcelain -- dashboard)"
./scripts/production-preflight.py --release-ref "$RELEASE_REF"

cd control-plane
npm exec --no -- wrangler d1 migrations list DB --env production --remote
npm exec --no -- wrangler deployments status --env production --json
npm exec --no -- wrangler pages deployment list \
  --project-name "$PRODUCTION_PAGES_PROJECT" \
  --environment production \
  --json
```

The receipt may contain release identity, migration filenames/status, Worker/Pages version IDs, HTTP verdicts, and timestamps. Redact provider account identifiers if they are not already intentionally public. Do not record secret contents or customer rows.

## Explicit approval boundary

The following commands mutate production and must run only after the GitHub `production` environment grants the exact deployment:

1. create a pre-migration D1 export according to the D1 backup/restore runbook;
2. apply approved migrations;
3. deploy the Worker;
4. deploy the exact console artifact;
5. run read-only smoke verification.

Do not combine preflight and mutation into a shell sequence where an earlier failure can be masked. Every semantic step must have its own exit status and receipt.

## Migration and Worker deployment

From the immutable checkout:

```bash
set -euo pipefail
cd control-plane
npm exec --no -- wrangler d1 migrations list DB --env production --remote
npm exec --no -- wrangler d1 migrations apply DB --env production --remote
npm exec --no -- wrangler d1 migrations list DB --env production --remote

npm exec --no -- wrangler deploy --env production \
  --strict \
  --tag "$RELEASE_REF" \
  --message "git=$SOURCE_SHA release=$RELEASE_REF"

npm exec --no -- wrangler deployments status --env production --json
```

The second migration-list command must report no pending migration. Record the new Worker version ID and confirm the deploy message binds it to `SOURCE_SHA`. Do not treat process exit alone as proof of route, TLS, health, or application identity.

## Production console artifact

Build into a fresh directory with the production API origin, then add the exact identity-only manifest:

```bash
set -euo pipefail
export VITE_API_BASE_URL=https://api.agentpulse.ca
npm --prefix dashboard ci
npm --prefix dashboard run build

./scripts/prepare-production-dashboard.py \
  --dist dashboard/dist \
  --version "$VERSION" \
  --source-sha "$SOURCE_SHA"
```

The helper fails if the shell/assets are missing, a non-production API origin is selected, the immutable identity is malformed, or `deployment.json` already exists. The manifest contains exactly service, environment, version, source SHA, API base, and main-JavaScript SHA-256—no secrets, provider IDs, or tenant data.

Preserve an immutable copy of the completed console directory as the rollback artifact. Deploy it to the verified Pages production branch, not a preview branch:

```bash
set -euo pipefail
cd control-plane
npm exec --no -- wrangler pages deploy ../dashboard/dist \
  --project-name "$PRODUCTION_PAGES_PROJECT" \
  --branch "$PRODUCTION_PAGES_BRANCH" \
  --commit-hash "$SOURCE_SHA" \
  --commit-message "AgentPulse $RELEASE_REF"

npm exec --no -- wrangler pages deployment list \
  --project-name "$PRODUCTION_PAGES_PROJECT" \
  --environment production \
  --json
```

Record the Pages deployment ID and immutable artifact digest. A successful upload does not prove the custom domain serves the new artifact.

## Post-deploy verification

Run the read-only smoke checker against the exact deployed identity:

```bash
set -euo pipefail
./scripts/production-smoke.py \
  --expected-version "$VERSION" \
  --expected-source-sha "$SOURCE_SHA"
```

Require direct HTTPS, strict JSON/media types, the exact Worker/console identity, main-JavaScript digest, production API base, trusted production CORS, rejected staging/local/untrusted CORS, and unauthenticated account `401`. Keep checkout and all billing mutations out of smoke verification.

## Rollback triggers

Rollback immediately if any of these appear after deployment:

- health or identity mismatch;
- console placeholder/stale bundle/wrong API origin;
- trusted CORS failure or untrusted-origin allowance;
- session/account fail-open behavior;
- sustained 5xx, D1 errors, webhook backlog, or heartbeat ingestion regression;
- an immutable receipt cannot reconcile Worker, console, migration, and source identities.

Application rollback does not roll back D1 schema or data. If a migration is not backward-compatible, use the separately reviewed database restore/recovery plan; do not guess reverse SQL during an incident.

## Worker rollback

Select the recorded previous healthy Worker version in the protected production environment. Compare its non-value binding names/types with the current deployment receipt first. **Stop** on any binding drift—especially secret names. Secret values remain unreadable and external, so a binding change requires explicit owner/provider review rather than an automatic rollback.

Do not use `wrangler rollback` in non-interactive CI: Wrangler 4.113.0 can retry it with force after changed-secret detection. Deploy the exact reviewed previous version as a new 100% deployment instead:

```bash
set -euo pipefail
cd control-plane
npm exec --no -- wrangler deployments status --env production --json
npm exec --no -- wrangler versions view "$PREVIOUS_WORKER_VERSION_ID" --env production --json
npm exec --no -- wrangler versions deploy "$PREVIOUS_WORKER_VERSION_ID@100%" \
  --env production \
  --message "rollback from=$SOURCE_SHA to=$PREVIOUS_SOURCE_SHA" \
  --yes
npm exec --no -- wrangler deployments status --env production --json
```

This creates a new active deployment of the selected saved version; it does not revert D1 data or deleted/changed bindings. Record Worker health and identity after this step, but defer the exact full production smoke until the console is also rolled back to the matching previous identity.

## Console rollback

Pages rollback is a redeployment of the preserved previous immutable console directory to the verified production branch. Never rebuild the old commit during the incident when a frozen artifact exists.

```bash
set -euo pipefail
cd control-plane
npm exec --no -- wrangler pages deploy "$PREVIOUS_CONSOLE_DIR" \
  --project-name "$PRODUCTION_PAGES_PROJECT" \
  --branch "$PRODUCTION_PAGES_BRANCH" \
  --commit-hash "$PREVIOUS_SOURCE_SHA" \
  --commit-message "rollback to $PREVIOUS_RELEASE_REF"

npm exec --no -- wrangler pages deployment list \
  --project-name "$PRODUCTION_PAGES_PROJECT" \
  --environment production \
  --json
```

Run production smoke with the previous exact version/source. Confirm the custom domain, `/account` SPA route, `deployment.json`, main bundle digest, API health, CORS, and unauthenticated account boundary.

## Completion receipt

Tier 4 deploy/rollback evidence must name:

- approved release tag, full commit, and package version;
- production migration state before/after;
- pre-migration D1 export identity and restore-drill receipt;
- new and previous Worker version IDs;
- new and previous Pages deployment/artifact identities;
- production smoke result after deploy and after rollback;
- observability/alert results and any incident timestamps;
- confirmation that secrets remained external and public checkout remained closed.

A runbook, successful deploy command, or green smoke run alone does not close Tier 4. The release gate requires live production DNS, deploy and rollback proof, external secrets, operational observability, and data-lifecycle evidence.
