# AgentPulse — Clerk customer and administrator workflows

Status: DESIGN / REVIEW ONLY. Prepared 2026-10-28. No Clerk instance, tenant link, D1 migration, production authentication change, or paid checkout was created by this document.

## Verified existing implementation

- Frontend: dashboard/ is React 19 + Vite, with react-router pages in dashboard/src/App.tsx.
- Backend: control-plane/ is a Cloudflare Worker with D1.
- Current browser login is a one-use paid checkout claim nonce exchanged for a Worker HttpOnly cookie and in-memory CSRF secret, not Clerk. /v1/account and fleet operations depend on the current Worker session. Preserve it during rollout.
- Existing Stripe billing and entitlement_status (active, grace, blocked) in D1 are the authority for product access. The production release record permits Starter checkout only; Pro and Business remain gated.
- Host agents have independent enrollment/heartbeat credentials and a local remediation safety ceiling. User authentication must never grant host command execution.
- Current documented production surfaces: https://app.agentpulse.ca and https://api.agentpulse.ca. Recheck deployment and authorized DNS before rollout.

## Decision

Create one dedicated Clerk application, AgentPulse (dev and production instances), separate from Out Here Framing. Use the current React SDK @clerk/react and @clerk/backend in the Cloudflare Worker (subject to dependency pinning after a real local install). Do not replace the existing Stripe checkout or its signed webhooks with Clerk Billing.

Keep the internal tenant ID as the database/Stripe owner. Associate exactly one Clerk organization to a tenant via a reviewed, one-time binding. Clerk verifies humans; D1 validates tenant ownership and Stripe access. Do not use email or request-supplied tenant_id as an authorization key. Keep agent bearer auth isolated.

## Customer journey — first use

1. Visitor sees public plans and chooses Starter; the existing POST /v1/billing/checkout continues to create the Stripe Checkout Session.
2. After payment, the existing Stripe webhook records/updates tenant + subscription; if this is delayed, show Payment pending and poll a status endpoint, not an assumed success.
3. Customer reaches the Clerk sign-in/sign-up experience, verifies their address, and chooses Create workspace or Join existing workspace.
4. A first-time purchaser completes a one-time checkout claim while authenticated. Worker verifies the claim, the paid checkout record, verified purchaser identity, and an unclaimed tenant; an email mismatch requires a manual, auditable recovery path. Claim consumption and tenant/org link creation must be atomic.
5. The Worker creates/links the organization and stores the tenant/org/user relationship. Idempotent retries return the same workspace; they must never create another tenant or grant one to the wrong person.
6. Customer lands on /servers with an onboarding checklist: activate workspace, install agent, issue short-lived enrollment token, confirm first heartbeat, inspect first result.
7. Customer can open /incidents, /account, /team and Stripe billing portal. Inactive billing still permits /account and payment recovery, not protected host enrollment.

Existing paid customers: keep old cookie/claim path available on a feature-flagged migration screen until verified association. Do not require repeat purchase or invalidate running agents.

## Customer journey — everyday use

Sign in -> select active Clerk Organization -> Worker verifies token + org membership + D1 tenant link -> D1 entitlement check -> tenant-scoped /servers and /incidents -> investigate events (read-only), enroll approved hosts within cap, review account and update payment method. Sign out revokes browser identity; host agents continue under their separate credentials. Users can belong to multiple organizations but see one active tenant at a time.

## Customer-organization administrator journey

1. Verified org owner/admin enters /team.
2. Invites teammate using Clerk invitation flow. New member is pending until the verified invitation is accepted and provisioned to the *same* linked tenant.
3. Assigns a least-privilege role: Viewer, Operator, Billing, or Org Admin. Clerk custom organization permissions and Worker-side D1 allowlists must agree.
4. Can revoke membership and agent enrollment tokens; access stops on next validated request. All membership changes get audit records.
5. Billing personnel may open the existing Stripe portal only for the verified tenant; no one may select a different Stripe customer from URL/query/body.
6. Can inspect fleet status and incidents. No role can bypass agent-side immutable policy ceiling or run arbitrary remote shell commands.

## Platform administrator journey (internal AgentPulse operator)

Access a separate /admin surface only after explicit out-of-band bootstrap to an allowlisted Clerk user ID. A Clerk org:admin role inside *any customer organization* must NEVER confer platform-admin authority.

Admin home -> tenant search (minimized metadata, audited) -> support case -> time-limited approved tenant view -> inspect plan, fleet health, redacted diagnostics and webhook status -> perform narrowly enumerated support action (reconcile subscription state from verified Stripe, revoke compromised session, disable tenant access) -> audit actor, reason, tenant, action and outcome. No arbitrary SQL, live payment creation, surprise refunds, remote command execution or silent cross-tenant impersonation.

## Authorization matrix

| Resource/action | Viewer | Operator | Billing | Org admin | Platform admin |
| --- | --- | --- | --- | --- | --- |
| Tenant fleet and incidents (read) | Yes | Yes | No | Yes | Only audited support scope |
| Enroll/revoke host credentials | No | Yes | No | Yes | No by default |
| Billing portal / subscription metadata | No | No | Yes | Yes | Redacted support metadata only |
| Invite/revoke teammate | No | No | No | Yes | No by default |
| Cross-tenant support diagnostics | No | No | No | No | Only explicit audited grant |
| Remote arbitrary host command | Never | Never | Never | Never | Never |

Custom role keys are proposed, not configured: org:viewer, org:operator, org:billing and org:admin; app permissions include org:fleet:read, org:hosts:enroll, org:billing:manage, org:team:manage. Verify current Clerk dashboard Role Set limitations before configuring.

## Proposed routes, not currently implemented

- Public: /sign-in, /sign-up, /pricing, /checkout-return, /onboarding/claim
- Authenticated: /servers, /servers/:agentId, /incidents, /incidents/:incidentId, /account, /team, /settings
- Internal: /admin, /admin/tenants, /admin/audit
- Worker additions: GET /v1/identity/me; POST /v1/identity/claim; GET /v1/team/members; POST /v1/team/invitations; GET /v1/admin/tenants; GET /v1/admin/audit
- Existing endpoints remain unchanged until migrated and regression-tested: /v1/billing/checkout, /v1/onboarding/claim, /v1/account, /v1/session/csrf, /v1/session, /v1/billing/portal, /v1/browser/enrollment-tokens, /v1/fleet, /v1/agents/*, /v1/stripe/webhook

## Server integration contract

1. React obtains short-lived Clerk session JWT with useAuth().getToken(), in memory; sends Authorization: Bearer <JWT> to the API. Do not write JWT to localStorage/sessionStorage.
2. Worker uses @clerk/backend authenticateRequest() (or documented verifyToken() only for a constrained token input) to verify signature, expiry, issuer, authorized parties and expected token type. Restrict CORS to approved frontend origins. Do not trust unsafely decoded claims.
3. Worker resolves clerk_user_id + active clerk_org_id against stored tenant_clerk_org_links and active tenant_member_links, then authorizes each requested resource by tenant_id plus permission.
4. Stripe webhooks must verify raw signatures and stay the *only* source of subscription entitlement. Frontend Clerk login never grants a paid plan.
5. Machine agents still use their existing separately minted scoped agent credentials; refuse Clerk browser tokens on machine enrollment/heartbeat/policy routes.
6. Use a verified Clerk webhook endpoint with signature verification, replay protection and idempotent membership/user synchronization. Webhooks are asynchronous; a successful first login cannot depend solely on their arrival.
7. The platform-admin allowlist is independent of customer organization roles, controlled server-side, and backed by immutable audit entries.

## Data model proposal

See SCHEMA-PROPOSAL.sql, deliberately stored under docs/auth rather than control-plane/migrations. It introduces tenant-org links, member links, platform-admin grants and audit events. No mutation of existing tenants, subscriptions, agents or their credentials is included. Review migration and rollback impact before moving it into live migrations.

## Delivery sequence and gates

0. Audit: document all existing browser/session flows, active paid tenants, exact API origin and current release checks. Save D1 backup and recovery evidence.
1. Clerk setup: create **AgentPulse** development Clerk app; configure origins and sign-in methods; provide dev publishable key to client build and secret/JWT verification key to Worker secret manager, never Git or chat.
2. Build: SDK/provider/identity UI on a feature branch, proposed D1 migration, Worker auth adapter, Clerk webhooks, role-aware routes, migration linking and tests. Existing flow is still default.
3. Staging: test two distinct tenants, invitations, invalid/expired/wrong-app/wrong-origin tokens, permission downgrade, org switching, subscription grace and blocked, hostile claim replay, webhook retries/out-of-order delivery, failed Stripe payment and one host enrollment.
4. Pilot: turn on Clerk for one explicitly consented test account behind a rollout flag. Validate onboarding, agent liveness, billing and logout in a real browser.
5. Cutover: reviewed migration report + protected deployment approval, backup and tested restore path; retain legacy signed-in fallback during grace window.
6. Rollback: disable Clerk route flag, restore legacy cookie flow without touching Stripe or running host agents. Never roll back database mappings by deleting payment records.

## Required acceptance tests

AP-C01 Clerk sign-in is not enough to access a different tenant's fleet.
AP-C02 No payment entitlement => fleet enrollment blocked even with valid Clerk session.
AP-C03 Viewer cannot enroll hosts or manage billing.
AP-C04 Org admin cannot access /admin; platform admin is explicit and audited.
AP-C05 Stolen/replayed claim cannot attach a second user or org.
AP-C06 Expired/wrong-issuer/wrong-origin/wrong-app JWT rejected.
AP-C07 Stripe lifecycle, host local policy ceiling, legacy sessions unaffected in legacy mode.
AP-C08 Logout, suspended team membership and active-org switching affect next request.
AP-C09 Two billing providers are not accidentally activated; Stripe stays ledger.
AP-C10 Deploy, rollback, Worker and dashboard tests and GitHub Actions gates pass.

## Open launch dependencies

- A separately owned Clerk application and configured dev/production instances.
- Exact production origin and Clerk domain/CSP settings validated against hosted deployment.
- Verified customer-email/Stripe-owner claim linking policy and exception procedure.
- Explicit decision on feature-flag migration and when to retire old browser sessions.
- Production D1 backup and approved migration/test/rollback plan.

References: Clerk React quickstart, React useAuth(), backend authenticateRequest()/verifyToken(), Organizations Roles and Permissions, Webhooks syncing, and cross-origin requests. Docs URLs: https://clerk.com/docs/react/getting-started/quickstart ; https://clerk.com/docs/guides/development/making-requests ; https://clerk.com/docs/reference/backend/verify-token ; https://clerk.com/docs/guides/organizations/control-access/roles-and-permissions ; https://clerk.com/docs/guides/development/webhooks/syncing
