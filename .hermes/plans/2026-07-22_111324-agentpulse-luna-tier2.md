# AgentPulse Tier 2 Commercial Lifecycle — Luna Implementation Plan

> **For Luna:** Execute this plan task-by-task using strict RED → GREEN → REFACTOR. Work directly in `/home/desktopdusty/workspace/repositories/agentpulse`. Preserve unrelated work, especially untracked `media/`. Commit and push directly to `master` only after the stated gates pass; Dustinn prefers no feature branches or PRs.

**Goal:** Restore a green security baseline, settle AgentPulse’s commercial contract at Owner Gate 2, then implement and locally prove the complete Stripe test-mode lifecycle: checkout → one-time account claim → secure browser session → account/portal → enrollment/heartbeat entitlement enforcement.

**Architecture:** Keep the existing local-first Python agent, Cloudflare Worker/D1 as the only hosted authority, React dashboard as the later Tier 3 consumer, and `packages/contracts/` as the API source of truth. Add browser sessions and billing routes to the Worker without adding FastAPI, Fly.io, arbitrary host commands, or a second backend. Store only hashed opaque credentials/session tokens; derive tenant identity server-side; re-read canonical Stripe objects for claim and portal operations.

**Tech stack:** Cloudflare Workers, D1/SQLite migrations, TypeScript, Vitest Workers pool, Stripe REST API, OpenAPI 3.1, JSON Schema, GitHub Actions.

---

## 0. Cold-boot facts and boundaries

### Verified current state

- Canonical repository: `/home/desktopdusty/workspace/repositories/agentpulse`
- Canonical branch: `master`; current verified HEAD at planning time: `f9d71459a9c2c9fe55117b00053167daa79cf9e2`; synchronized with `origin/master`.
- Untracked `media/` exists and is unrelated: do not add, move, delete, or modify it.
- Tier 1 is complete: published `v0.2.0-beta.2`, 193 agent tests, 20 packaging tests, Novita broad 37/37 and real-systemd 29/29 acceptance.
- Current Worker API has enrollment, heartbeat, policy, fleet, and a partial Stripe webhook.
- Current Stripe webhook only materially handles `invoice.payment_failed`.
- Current browser/account authentication is bearer credentials; secure cookie sessions do not exist.
- Current D1 schema is only `control-plane/migrations/0001_initial.sql`.
- Current OpenAPI exposes seven paths; checkout, claim, account, session logout, and portal routes are absent.
- Current staging D1 ID exists; production D1 remains a placeholder and is out of scope for this plan.
- Public multi-host checkout must remain closed throughout this plan.
- Secrets exist only in external stores or local ignored files. Never print or commit values.

### Live prerequisite failure

GitHub Security run `29929310567` failed because `npm audit --audit-level=high` reports four high-severity development-chain findings involving:

- `sharp <0.35.0`
- `miniflare`
- `wrangler`
- `@cloudflare/vitest-pool-workers`

Current direct dev versions are:

- `@cloudflare/vitest-pool-workers: 0.18.4`
- `wrangler: 4.110.0`
- `vitest: 4.1.10`
- `typescript: 7.0.2`

`npm audit fix --force` proposes breaking downgrades. Do not apply it blindly.

### Permanent constraints

1. Cloud policy can narrow but never widen local authority.
2. Billing failure may disable hosted enrollment/heartbeat access, but it must never disable safe local monitoring/remediation.
3. No arbitrary command route or remote shell.
4. Tenant identity comes from a verified session/agent credential, never request payload tenant IDs.
5. Browser session cookies must be `HttpOnly`, `Secure` outside local test, `SameSite=Lax`, `Path=/`, host-only, short-lived, rotatable, and revocable.
6. State-changing browser routes require CSRF defense and trusted-origin validation.
7. Stripe webhook and claim paths are idempotent and safe under duplicate/out-of-order delivery.
8. Public checkout stays invite/beta gated until staging proof and later owner gates pass.
9. Do not deploy production, charge a card, alter DNS, or request secret values.

---

## Task 1: Restore the green dependency-security baseline

**Objective:** Remove the current high-severity dependency findings without breaking Worker tests, type checking, generated bindings, or runtime compatibility.

**Files:**
- Modify: `control-plane/package.json`
- Modify: `control-plane/package-lock.json`
- Verify: `.github/workflows/security.yml`

### Step 1: Reproduce RED

Run:

```bash
cd /home/desktopdusty/workspace/repositories/agentpulse/control-plane
npm ci
npm audit --audit-level=high
```

Expected: nonzero with four high-severity findings through Sharp/Miniflare/Wrangler.

### Step 2: Evaluate minimal compatible remedies

Do not use `npm audit fix --force`. Test these in order, reverting failed candidates:

1. Check whether the newest compatible Cloudflare packages resolve the advisory:
   ```bash
   npm view @cloudflare/vitest-pool-workers versions --json
   npm view wrangler versions --json
   npm view sharp version
   ```
2. Prefer upgrading direct Cloudflare dependencies if a non-vulnerable compatible release exists.
3. If Cloudflare has not yet republished the chain, test a narrow npm override for `sharp >=0.35.0` only if Miniflare/Wrangler accept it and all Worker tests execute normally.
4. If the advisory’s only supported resolution is a downgrade, test the exact audit-proposed pair in an isolated lockfile diff and retain it only if all project gates pass. Record the tradeoff in the commit body.
5. Never suppress the advisory, lower the audit level, omit dev dependencies, or weaken Security CI.

### Step 3: Verify GREEN

Run after each candidate:

```bash
npm ci
npm test
npm run typecheck
npm run types:check
npm audit --audit-level=high
```

Expected: all exit 0; 14 existing Worker tests pass; generated bindings remain current; audit reports zero high/critical findings.

Also run:

```bash
cd ..
npm --prefix dashboard ci
npm --prefix dashboard run build
python3 scripts/validate-contracts.py
git diff --check
```

### Step 4: Commit

```bash
git add control-plane/package.json control-plane/package-lock.json
git commit -m "fix: remediate Worker dependency security findings"
git push origin master
```

Wait for Tests, Contract Integration, Security, CodeQL, and Pages. Security must be green before Task 2 is considered complete.

---

## Task 2: Prepare and stop at Owner Gate 2

**Objective:** Give Dustinn one concise decision block before coding irreversible billing behavior.

**Read:**
- `docs/pricing.md`
- `docs/terms.md`
- `docs/signup.md`
- `control-plane/migrations/0001_initial.sql`
- `control-plane/wrangler.jsonc`

### Recommended commercial contract

Present this as one multiple-choice confirmation, not a sequence of questions:

| Item | Recommended v1 decision | Why |
|---|---|---|
| Starter | C$29/month, 1 host | Already public and technically enforceable |
| Pro | C$99/month, 5 hosts | Already public and technically enforceable |
| Business | C$299/month, 10 hosts | Finite, enforceable, and still clearly a small-fleet beta |
| Checkout posture | Invite-only/test-mode until Tier 2 staging proof; then controlled public Starter only | Avoid selling undelivered multi-host capacity |
| Trial | No free trial | Reduces entitlement states and abuse surface |
| Cancellation | End of current paid period | Matches current Terms |
| Failed payment | Three-day hosted-service grace, then `past_due` blocks cloud enrollment/heartbeat; local agent continues | Customer-friendly while preserving local safety |
| Guarantee | Keep existing first-30-days “next month free” operating promise | Already public; clearer than refunds/proration |
| Tax/address | Collect billing address; enable Stripe Tax only when owner confirms registration obligations | Avoid inventing tax treatment |

Owner response options should be:

1. `Approve recommended Gate 2 contract`
2. `Approve with Business at 15 hosts`
3. `Keep Business manual-only; approve everything else`
4. Custom changes

**Hard stop:** Luna must not begin Tasks 3–8 until Dustinn confirms Gate 2. Task 1 may be completed independently.

---

## Task 3: Add the API contract one vertical slice at a time

**Objective:** Define only the routes needed for the Tier 2 lifecycle before Worker implementation.

**Files:**
- Modify: `packages/contracts/openapi.yaml`
- Modify: `packages/contracts/error-codes.md`
- Create: `packages/contracts/schemas/account.schema.json`
- Create: `packages/contracts/schemas/billing.schema.json`
- Create: `packages/contracts/schemas/session.schema.json`
- Create: `packages/contracts/fixtures/account-response.json`
- Create: `packages/contracts/fixtures/checkout-response.json`
- Create: `packages/contracts/fixtures/claim-response.json`
- Modify: `scripts/validate-contracts.py` only if explicit fixture mapping is required

### Contract routes

Add these exact paths:

1. `POST /v1/billing/checkout`
   - Input: `plan`, `email`, `success_url`, `cancel_url`
   - Plan enum from approved Gate 2 contract.
   - Return: `checkout_url`, `checkout_session_id`, `claim_token`, `expires_at`.
   - `claim_token` is opaque, one-time, and returned only once.

2. `POST /v1/onboarding/claim`
   - Input: `checkout_session_id`, `claim_token`.
   - Success sets the secure session cookie.
   - Return non-secret `AccountResponse` plus a CSRF token for subsequent state-changing requests.

3. `GET /v1/account`
   - Auth: browser session cookie.
   - Return tenant email, plan, subscription status, host limit, current host count, current period end, and CSRF token.

4. `DELETE /v1/session`
   - Auth: browser session cookie.
   - Requires trusted Origin and `X-CSRF-Token`.
   - Revokes server-side session and expires cookie.

5. `POST /v1/billing/portal`
   - Auth: browser session cookie.
   - Requires trusted Origin and `X-CSRF-Token`.
   - Return `portal_url` only.

6. Change `POST /v1/enrollment-tokens` and `GET /v1/fleet` to accept browser session auth in addition to legacy AccountBearer during beta migration. Do not remove AccountBearer until Tier 3 dashboard migration is proven.

### RED → GREEN sequence

For each route/schema:

1. Add one failing contract assertion/fixture.
2. Run:
   ```bash
   python3 scripts/validate-contracts.py
   ```
   Expected: FAIL for missing path/schema/reference.
3. Add the minimal OpenAPI/schema definition.
4. Rerun and require PASS.
5. Commit after checkout+claim, then account+session, then portal+dual-auth.

Suggested commits:

```text
feat: define checkout and claim contracts
feat: define secure account session contracts
feat: define billing portal and browser-auth contracts
```

---

## Task 4: Add D1 migration 0002 for claims and sessions

**Objective:** Represent pre-claim state, secure browser sessions, webhook processing outcomes, and the approved grace-period policy without rewriting migration 0001.

**Files:**
- Create: `control-plane/migrations/0002_commercial_lifecycle.sql`
- Modify: `control-plane/test/apply-migrations.ts` if necessary
- Modify: `control-plane/test/control-plane.test.ts`

### Required tables

Create `checkout_claims` rather than mutating the existing completed-claim-shaped `onboarding_claims` table:

```sql
CREATE TABLE checkout_claims (
  checkout_session_id TEXT PRIMARY KEY,
  claim_token_hash TEXT NOT NULL UNIQUE,
  requested_email TEXT NOT NULL COLLATE NOCASE,
  requested_plan TEXT NOT NULL CHECK (requested_plan IN ('starter','pro','business')),
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  claimed_at INTEGER,
  tenant_id TEXT REFERENCES tenants(id) ON DELETE SET NULL,
  account_credential_id TEXT REFERENCES account_credentials(id) ON DELETE SET NULL
);
CREATE INDEX checkout_claims_expiry ON checkout_claims(expires_at, claimed_at);
```

Create `browser_sessions`:

```sql
CREATE TABLE browser_sessions (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  csrf_hash TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  last_used_at INTEGER,
  revoked_at INTEGER
);
CREATE INDEX browser_sessions_tenant_active
  ON browser_sessions(tenant_id, revoked_at, expires_at);
```

Add subscription lifecycle fields compatible with the approved policy:

```sql
ALTER TABLE subscriptions ADD COLUMN cancel_at_period_end INTEGER NOT NULL DEFAULT 0;
ALTER TABLE subscriptions ADD COLUMN grace_expires_at INTEGER;
ALTER TABLE subscriptions ADD COLUMN last_stripe_event_created INTEGER NOT NULL DEFAULT 0;
```

Do not drop or rewrite `onboarding_claims`; preserve migration history.

### TDD

1. Add a test that applies 0001 then 0002 and asserts all new tables/columns.
2. Run `npm test`; expected RED because 0002 is missing.
3. Add 0002.
4. Run `npm test`; expected GREEN.
5. Add a migration replay test proving reinitialization from scratch works.
6. Run `npm test && npm run typecheck`.
7. Commit:
   ```text
   feat: add commercial lifecycle D1 schema
   ```

---

## Task 5: Implement secure session primitives before routes

**Objective:** Create reusable cookie/session/CSRF/origin primitives with direct behavioral tests.

**Files:**
- Create: `control-plane/src/security.ts`
- Create: `control-plane/src/session.ts`
- Modify: `control-plane/src/index.ts`
- Modify: `control-plane/test/control-plane.test.ts`
- Modify: `control-plane/test/test-env.d.ts`

### Required behavior

- Cookie name: `__Host-agentpulse_session` in staging/production.
- Local test may use `agentpulse_session` when HTTPS host-only cookie semantics cannot be represented.
- Token: 32 random bytes, URL-safe, stored only as SHA-256.
- Session expiry: 12 hours for v1.
- CSRF token: independent random value, returned in authenticated JSON and stored only as SHA-256.
- State-changing browser calls require:
  - session cookie;
  - `Origin` exactly equal to approved app origin;
  - `X-CSRF-Token` hash matching the session row.
- Read-only `GET /v1/account` does not require CSRF.
- Refresh `last_used_at` without extending absolute expiry.
- Logout revokes the row and expires the cookie.
- Error responses never include tokens, Stripe bodies, or raw exceptions.

### TDD slices

For each behavior: write one failing Vitest case, run the focused test to confirm expected failure, implement minimum code, rerun focused test, then full Worker suite.

Required tests:

1. Claim/session response cookie has HttpOnly, Secure (staging/prod), SameSite=Lax, Path=/, no Domain.
2. Raw session token is absent from D1.
3. Expired session returns 401.
4. Revoked session returns 401.
5. Missing/wrong Origin returns 403 on mutation.
6. Missing/wrong CSRF token returns 403.
7. Valid session+Origin+CSRF succeeds.
8. Logout revokes and clears cookie.
9. Tenant is derived from session row, not request body.

Commit:

```text
feat: add secure browser session primitives
```

---

## Task 6: Implement checkout and one-time claim

**Objective:** Create an allowlisted Stripe Checkout Session and atomically claim a paid/test-mode session exactly once.

**Files:**
- Create: `control-plane/src/stripe.ts`
- Create: `control-plane/src/billing.ts`
- Modify: `control-plane/src/index.ts`
- Modify: `control-plane/test/control-plane.test.ts`
- Modify: `control-plane/test/test-env.d.ts`
- Modify: `control-plane/wrangler.jsonc`
- Modify: `control-plane/.dev.vars.example`

### Environment bindings

Add names only, never values:

- `STRIPE_API_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_STARTER`
- `STRIPE_PRICE_PRO`
- `STRIPE_PRICE_BUSINESS` (only if Business approved for self-serve)
- `APP_ORIGIN`
- `CHECKOUT_SUCCESS_URL`
- `CHECKOUT_CANCEL_URL`

### Checkout rules

- Map approved plan names to exact environment Price IDs; reject unknown or blank mappings.
- Trusted return URLs come from environment/config, not arbitrary request values. If request includes URLs, require exact equality to approved values.
- Generate claim token server-side; store only hash.
- Put only non-secret identifiers in Stripe metadata: claim/session ID and plan. Never put the raw claim token in Stripe metadata.
- Send idempotency key to Stripe derived from the server-generated checkout claim ID.
- Use a small Stripe REST wrapper with bounded timeout and stable internal errors.

### Claim rules

- Hash and look up claim token; require unexpired/unclaimed row.
- Fetch Checkout Session from Stripe using `STRIPE_API_KEY`.
- Require paid/completed state and exact matching session ID, email, Price ID/plan, and claim metadata.
- Fetch canonical Subscription before deriving entitlement.
- Atomically create/upsert tenant and subscription, create account credential only if still needed for beta compatibility, mark claim consumed, create browser session, and write completed `onboarding_claims` evidence.
- A second claim returns stable `claim_already_used` and never creates another credential/session.
- Do not trust webhook arrival order to authorize claim.

### Required tests

1. Unknown plan rejected before Stripe call.
2. Blank/unconfigured Price ID fails closed.
3. Return URL mismatch rejected.
4. Checkout stores only claim-token hash.
5. Stripe error maps to stable sanitized error.
6. Unpaid/incomplete Checkout Session cannot be claimed.
7. Email/plan/Price metadata mismatch cannot be claimed.
8. Expired claim rejected.
9. First valid claim creates one tenant/subscription/session.
10. Replay creates nothing and returns stable conflict.
11. Concurrent claim attempts result in exactly one success.
12. No raw Stripe secret/token appears in logs or response.

Commit each vertical slice:

```text
feat: create allowlisted Stripe checkout sessions
feat: add one-time checkout account claim
```

---

## Task 7: Complete deterministic Stripe webhook lifecycle

**Objective:** Process the required Stripe events idempotently and safely under duplicates and out-of-order delivery.

**Files:**
- Modify: `control-plane/src/stripe.ts`
- Modify: `control-plane/src/billing.ts`
- Modify: `control-plane/src/index.ts`
- Modify: `control-plane/test/control-plane.test.ts`
- Modify: `packages/contracts/error-codes.md`

### Required event set

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.paid`
- `invoice.payment_failed`

### Processing model

1. Verify raw-body Stripe signature and five-minute timestamp window before parsing.
2. Insert event ID once; duplicates return success without applying twice.
3. Track `event.created`; ignore an older event when `event.created < subscriptions.last_stripe_event_created`.
4. For subscription/create/update/delete and invoice events, fetch canonical Stripe Subscription when needed rather than trusting partial payloads.
5. Map only allowlisted Price IDs to approved plan+host limit.
6. Unknown Price ID sets `processing_error`, does not grant entitlement, and returns a retryable/safe result according to the chosen Stripe retry policy.
7. `invoice.payment_failed`: set `past_due`, set `grace_expires_at = now + approved duration`.
8. `invoice.paid`: restore canonical active/trialing status and clear grace.
9. Deleted/canceled: retain access only through `current_period_end` if cancellation is end-of-period; otherwise set canceled.
10. Enrollment/heartbeat account checks treat active/trialing as active and past_due as active only until `grace_expires_at`; local agent remains unaffected.
11. Persist sanitized `processing_error`; never store full raw Stripe payloads.

### Required tests

- Every event type maps to the expected entitlement state.
- Duplicate event is no-op.
- Older event cannot overwrite newer state.
- Failed payment starts grace; expiry blocks hosted access.
- Paid recovery clears grace and restores hosted access.
- Unknown Price ID never grants capacity.
- Business capacity equals Gate 2 decision.
- Two tenants cannot affect each other through Stripe identifiers.
- Invalid signatures and oversized bodies fail closed.

Commit:

```text
feat: complete idempotent Stripe subscription lifecycle
```

---

## Task 8: Add account and billing portal routes

**Objective:** Expose the minimum secure account-management API needed by Tier 3.

**Files:**
- Modify: `control-plane/src/index.ts`
- Modify: `control-plane/src/session.ts`
- Modify: `control-plane/src/billing.ts`
- Modify: `control-plane/test/control-plane.test.ts`

### Behavior

- `GET /v1/account`: return only the authenticated tenant’s non-secret account/subscription summary, active host count, host limit, and CSRF token.
- `POST /v1/billing/portal`: session + Origin + CSRF required; create Stripe Customer Portal Session for the authenticated tenant’s stored customer ID; trusted return URL from env only.
- `DELETE /v1/session`: revoke and clear cookie.
- Permit existing enrollment/fleet code to authenticate from browser session or legacy bearer during the migration window.

### Required tests

1. Account response contains no credential hashes, Stripe API data, or other tenant data.
2. Portal cannot select a customer ID from request body.
3. Portal Stripe errors are sanitized.
4. Cross-tenant portal/fleet attempts fail.
5. Legacy AccountBearer still works until Tier 3 removes dashboard dependence.
6. Browser session auth works for account, fleet, and enrollment-token creation.

Commit:

```text
feat: add secure account and billing portal APIs
```

---

## Task 9: Stage everything possible without secrets

**Objective:** Make Tier 2 locally complete and ready for Owner Gate 3 without deploying or exposing credentials.

**Files:**
- Modify: `control-plane/.dev.vars.example`
- Modify: `control-plane/wrangler.jsonc`
- Create: `scripts/staging-commercial-lifecycle.sh`
- Create: `docs/runbooks/staging-commercial-lifecycle.md`
- Modify: `control-plane/ARCHITECTURE.md`
- Modify: `ARCHITECTURE.md`
- Modify: `STATUS.md`
- Modify: `docs/planning/AGENTPULSE-FINISHED-PRODUCT-MATRIX.md`
- Modify: `docs/planning/AGENTPULSE-COMPLETION-PLAN.md` to mark live Tier 1 truth and Tier 2 progress

### Requirements

- Example env files contain names/placeholders only.
- Staging script uses Stripe test mode and synthetic non-personal data.
- Script fails closed on every non-2xx/unexpected response.
- Script never prints cookies, claim tokens, API keys, webhook secrets, or customer PII.
- Script records only redacted route/status evidence.
- Public checkout remains closed in docs.
- Do not claim staging lifecycle passed until Gate 3 secrets/resources are configured and the script actually runs.

### Verification

```bash
bash -n scripts/staging-commercial-lifecycle.sh
python3 scripts/validate-contracts.py
cd control-plane
npm ci
npm test
npm run typecheck
npm run types:check
npm audit --audit-level=high
cd ../dashboard
npm ci
npm run build
cd ..
python3 agent/tools/run_tests.py
python3 tests/test_packaging.py
git diff --check
```

Expected:

- Existing agent: 193 passed.
- Packaging: 20 passed.
- Worker count increases with all new tests passing.
- Contracts pass with expanded path/schema/fixture counts.
- Dashboard production build passes unchanged.
- Zero high/critical npm findings.
- No secrets in staged diff.

Run a focused secret-pattern scan over the exact staged diff, then dispatch two independent read-only reviews:

1. Security/auth/Stripe/tenant-isolation review.
2. Contract/migration/docs/provenance review.

Any real security concern or logic error blocks commit. After any change, rerun verification and review the new exact staged tree.

Final commit:

```text
feat: complete Tier 2 commercial lifecycle foundation
```

Push only after all local gates and reviews pass.

---

## Task 10: Stop at Owner Gate 3

**Objective:** Hand Dustinn one exact secret-placement/resource checklist; do not deploy or ask for secret values.

Luna reports:

- exact master commit;
- dependency Security workflow result;
- Worker/contract/dashboard/agent test receipts;
- D1 migration number;
- all implemented routes;
- known limitations;
- exact non-secret binding names and staging URLs;
- the one required owner action block.

Owner-only actions:

1. Confirm/create Stripe test Products/Prices matching Gate 2.
2. Configure Stripe test Customer Portal.
3. Configure staging webhook with the six exact event types.
4. Enter secret values directly into Cloudflare/GitHub stores.
5. Confirm staging D1 bindings.

Dustinn replies only `Gate 3 complete` plus non-secret IDs/URLs if Luna cannot query them. Never request values for `STRIPE_API_KEY` or `STRIPE_WEBHOOK_SECRET` in chat.

After Gate 3, Luna resumes with Phase 3D staging proof. Tier 3 dashboard work does not begin until the Tier 2 test-mode lifecycle passes with no manual D1 edits.

---

## Files likely to change

```text
control-plane/package.json
control-plane/package-lock.json
control-plane/src/index.ts
control-plane/src/security.ts
control-plane/src/session.ts
control-plane/src/stripe.ts
control-plane/src/billing.ts
control-plane/test/control-plane.test.ts
control-plane/test/test-env.d.ts
control-plane/test/apply-migrations.ts
control-plane/migrations/0002_commercial_lifecycle.sql
control-plane/wrangler.jsonc
control-plane/.dev.vars.example
packages/contracts/openapi.yaml
packages/contracts/error-codes.md
packages/contracts/schemas/account.schema.json
packages/contracts/schemas/billing.schema.json
packages/contracts/schemas/session.schema.json
packages/contracts/fixtures/account-response.json
packages/contracts/fixtures/checkout-response.json
packages/contracts/fixtures/claim-response.json
scripts/staging-commercial-lifecycle.sh
docs/runbooks/staging-commercial-lifecycle.md
control-plane/ARCHITECTURE.md
ARCHITECTURE.md
STATUS.md
docs/planning/AGENTPULSE-FINISHED-PRODUCT-MATRIX.md
docs/planning/AGENTPULSE-COMPLETION-PLAN.md
```

## Do not touch

- `media/` — unrelated untracked user work.
- Retired FastAPI/Fly/main architecture — never restore.
- Production D1 placeholder/resource creation — later owner gate.
- Public checkout buttons — remain closed.
- Dashboard credential/sessionStorage implementation — Tier 3 replaces it after Tier 2 staging proof.
- Agent remediation authority — this scope changes hosted entitlement only.
- Release `v0.2.0-beta.2` artifacts or clean-host receipts — Tier 1 is complete.

## Definition of done for this Luna handoff

This plan is complete only when:

1. Master Security is green with zero high/critical dependency findings.
2. Gate 2 decisions are explicitly approved and encoded consistently.
3. Contracts, migration, Worker routes, sessions, checkout/claim, portal, and six-event Stripe lifecycle are implemented test-first.
4. Browser sessions are server-side, secure-cookie based, CSRF protected, revocable, and tenant derived.
5. Duplicate/out-of-order Stripe events, claim replay, session expiry, payment failure/recovery, and two-tenant attacks are covered.
6. Full local gates pass; exact staged tree receives two independent green reviews.
7. Changes are committed/pushed to `master` with GitHub checks green.
8. Public checkout remains closed.
9. Luna stops at Owner Gate 3 without exposing or requesting secrets.
