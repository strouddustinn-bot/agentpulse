# Staging commercial lifecycle runbook

This runbook prepares Hermes Tier 2 Phase 3D staging proof without recording secrets, capability URLs, claim nonces, cookies, CSRF tokens, enrollment tokens, agent credentials, customer email, or payment data.

## Scope

Prove only the Stripe **test-mode** staging path:

1. `GET /health`
2. `POST /v1/billing/checkout` in `prepare`
3. owner-completed Stripe test Checkout with synthetic data only
4. `POST /v1/onboarding/claim` in `prove`
5. claim replay rejection
6. browser session account read
7. missing/invalid CSRF and untrusted Origin rejection
8. Customer Portal creation without retaining the URL
9. browser enrollment token creation
10. agent enrollment and enrollment-token replay rejection
11. first and duplicate heartbeat
12. exact fleet presence for the synthetic agent
13. logout and post-logout denial

The script does not deploy Worker code, apply migrations, configure Stripe, enter Cloudflare secrets, mutate DNS, touch production, or perform cleanup in Stripe/Cloudflare.

## Owner Gate 3 prerequisites

Owner or Hermes with explicit approval must configure these outside the repo:

- Stripe test recurring Prices matching the approved Gate 2 contract:
  - `STRIPE_PRICE_STARTER`
  - `STRIPE_PRICE_PRO`
  - `STRIPE_PRICE_BUSINESS`
- Stripe test Customer Portal settings
- Stripe staging webhook endpoint for exactly:
  - `checkout.session.completed`
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
  - `invoice.paid`
  - `invoice.payment_failed`
- Cloudflare Worker secret bindings by name only:
  - `STRIPE_API_KEY`
  - `STRIPE_WEBHOOK_SECRET`
- Staging D1 binding with migrations `0001` through hard-fail `0003` already applied and no pending migration before Worker deployment
- Staging API origin: `PUBLIC_BASE_URL=https://staging-api.agentpulse.ca`
- Staging app origin or temporary callback origin for checkout success redirects

Do not paste secret values into chat, logs, docs, Git, shell history, process argv, or environment variables.

## Migration preflight and apply sequence

No manual D1 edits are allowed.

1. Record the exact Worker source/config identity intended for staging.
2. List remote staging migrations before applying anything.
3. Discover all local migrations lexically from `control-plane/migrations/*.sql`.
4. Compare remote applied migrations with local migrations and apply every pending migration in lexical order.
5. Before applying any uniqueness/hard-fail migration, run a redacted duplicate preflight. For `0003`, the required aggregate is tenant groups with more than one subscription row. A nonzero result stops the proof for owner-approved reconciliation; do not delete or edit D1 rows manually to pass the gate.
6. Apply any pending migrations with Wrangler against the staging D1 binding.
7. List migrations again and record before/after state. Require no pending migration remains before deploying Worker code that reads the new columns.
8. If any pending migration fails—including `0003` on a new environment—stop. Record the redacted duplicate preflight receipt, migration failure, and rollback/retry decision needed from Hermes/owner.

## Temporary callback workflow while `staging-app.agentpulse.ca` has no DNS

Because `staging-app.agentpulse.ca` is absent, use a disposable callback Worker rather than asking the owner to paste a redirect URL or claim nonce.

The callback must:

- expose only `/claim` and `/receipt`;
- consume the claim nonce immediately server-to-server and never log, store, return, or display it;
- keep cookies, CSRF tokens, enrollment tokens, agent credentials, customer email, and full Checkout/Portal URLs out of all receipts/logs;
- persist only short-lived redacted booleans/status codes plus plan, entitlement status, and host limit in the edge Cache for at most 900 seconds; cache loss returns an incomplete receipt and fails closed;
- use the browser-session + CSRF route for enrollment;
- be deleted after the proof and the control-plane `APP_BASE_URL` restored to canonical staging config.

Local artifact: `scripts/staging-lifecycle-callback/`. It is not deployed by this repo change.

Callback receipt schema:

```json
{
  "schema_version": 1,
  "complete": true,
  "passed": true,
  "claim": { "status": 200, "ok": true },
  "claim_replay": { "status": 409, "ok": true },
  "account": { "status": 200, "ok": true },
  "csrf_missing": { "status": 403, "ok": true },
  "csrf_invalid": { "status": 403, "ok": true },
  "portal": { "status": 200, "ok": true, "stripe_url": true },
  "browser_enrollment_token": { "status": 201, "ok": true },
  "agent_enrollment": { "status": 201, "ok": true },
  "enrollment_replay": { "status": 409, "ok": true },
  "heartbeat_first": { "status": 202, "ok": true },
  "heartbeat_duplicate": { "status": 200, "ok": true },
  "fleet": { "status": 200, "ok": true, "agent_present": true },
  "logout": { "status": 204, "ok": true },
  "post_logout_denied": { "status": 401, "ok": true },
  "plan": "starter",
  "entitlement": "active",
  "host_limit": 1
}
```

## Local verification before staging proof

```bash
bash -n scripts/staging-commercial-lifecycle.sh
/tmp/agentpulse-phase3d-venv/bin/python scripts/validate-contracts.py
python3 scripts/validate-migrations.py
npm --prefix control-plane test
npm --prefix control-plane run typecheck
npm --prefix control-plane run types:check
npm --prefix dashboard test -- --run --no-color
npm --prefix dashboard run build
git diff --check
npm --prefix control-plane test -- test/staging-lifecycle-callback.test.ts
```

## Running the script

Prepare creates exactly one checkout, verifies exact response shape, requires `checkout_session_id` to be `cs_test_*` and `livemode=false`, writes the full Checkout URL only to a mode-600 operator handoff, emits `INCOMPLETE`, and exits `10` for owner action.

```bash
AP_STAGING_API_BASE=https://staging-api.agentpulse.ca \
AP_STAGING_PLAN=starter \
AP_CHECKOUT_HANDOFF_FILE=/path/to/mode600-handoff-created-by-script \
bash scripts/staging-commercial-lifecycle.sh prepare
```

Show the handoff only through a private local channel. Warn the owner: the link is Stripe test mode only and they must use Stripe test payment details, never a real card.

Prove never creates checkout. It accepts claim material only through a mode-600 file or protected stdin/FD, never argv/env:

```bash
printf '%s' '{"claim_nonce":"local-only-secret"}' > /path/to/claim.json
chmod 600 /path/to/claim.json
AP_STAGING_API_BASE=https://staging-api.agentpulse.ca \
AP_CLAIM_FILE=/path/to/claim.json \
bash scripts/staging-commercial-lifecycle.sh prove
```

A valid completion requires both exit `0` and the final structured marker beginning `AGENTPULSE_STAGING_LIFECYCLE PASS`. Prepare's `INCOMPLETE` marker and exit `10` is not a pass.

## Separate approval-gated procedures

The happy-path callback/script receipt does not prove every Gate 3 negative case. Prove and record these separately with explicit staging/test-mode approval:

- duplicate webhook delivery and retry behavior through the live Stripe endpoint;
- expired claim/session denial;
- failed-payment denial after the configured grace boundary;
- paid recovery after `invoice.paid`;
- two-tenant isolation with two paid synthetic tenants or an approved fixture;
- log-redaction inspection for Worker logs, callback logs, and evidence artifacts.

## Evidence to retain

Record only:

- command path and exit code;
- exact reviewed source/config hash and deployed Worker version;
- before/after D1 migration state;
- duplicate-subscription preflight aggregate receipt;
- route names and HTTP pass/fail status;
- plan, entitlement status, and host limit;
- redacted Stripe object IDs only if needed for support correlation;
- callback cleanup and control-plane `APP_BASE_URL` restore verification.

Do not retain cookies, CSRF tokens, claim nonce, API keys, webhook secrets, full Checkout or Portal URLs, enrollment tokens, agent credentials, customer names, addresses, cards, or emails outside synthetic `example.test` data.

## Cleanup

After proof or abort:

1. Restore the canonical staging `APP_BASE_URL`.
2. Redeploy the control-plane staging Worker only with explicit deployment approval.
3. Delete the disposable callback Worker.
4. Remove local temporary claim/handoff files.
5. Cancel or expire synthetic Stripe test subscriptions through an approved test-mode path.
6. Record cleanup success before any release-readiness claim.

## Stop condition

If any request or migration assertion fails, stop and print only the failing route/status or migration name. Fix source/environment, rerun local verification, then restart the staging proof. Do not claim Tier 2 Phase 3D passed until every local gate, live happy path, separate negative procedure, log-redaction inspection, and cleanup/restore check has passed.
