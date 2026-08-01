# Staging console deploy + browser E2E (Phase 4B)

## Goal

Prove the post-pay console on `staging-app.agentpulse.ca` against
`staging-api.agentpulse.ca` with cookie sessions, CSRF mutations, enrollment
mint, billing portal handoff, logout, and no browser bearer storage.

## What landed in source (agent-owned)

| Artifact | Purpose |
|---|---|
| `dashboard/e2e/*.mocked.spec.ts` | CI-safe Playwright against mocked Worker contract |
| `dashboard/e2e/*.staging.spec.ts` | Live staging path (needs claim nonce + DNS) |
| `dashboard/playwright.config.ts` | mocked always; staging-live when `AP_E2E_BASE_URL` set |
| `.github/workflows/dashboard-staging.yml` | mocked E2E on dashboard changes; optional Pages deploy |
| `make dashboard-e2e` | local mocked browser suite |

## Owner Gate 4 (required for live browser cookies)

**Status 2026-07-30:** Gate 4 DNS/TLS is live. `staging-app.agentpulse.ca`
resolves to Pages project `agentpulse-staging-app` and serves the real console
shell (not the placeholder). Worker CORS accepts
`Origin: https://staging-app.agentpulse.ca` with credentials.

Historical setup notes retained below for recovery:

Suggested DNS (owner applies exact rows if tooling cannot):

| Name | Type | Target | Proxy | TTL |
|---|---|---|---|---|
| `staging-app` | CNAME | `agentpulse-staging-app.pages.dev` (or CF Pages-assigned target) | Proxied | Auto |

Verification after DNS:

```bash
dig +short staging-app.agentpulse.ca CNAME A AAAA
curl -4 -I --max-time 15 https://staging-app.agentpulse.ca/
# Expect TLS + HTTP 200 from the console shell (not the marketing site).
```

Also confirm staging Worker `APP_BASE_URL=https://staging-app.agentpulse.ca`
(already the wrangler staging default).

## Deploy console (after Gate 4 DNS plan is ready)

1. Ensure GitHub `staging` environment has `CF_API_TOKEN` + `CF_ACCOUNT_ID`
   with Pages write on this account.
2. From GitHub Actions: run **Dashboard Staging** → `deploy=true` on `master`.
3. Or locally (credentials from `~/.config/agentpulse/cloudflare.env`, never chat):

```bash
set -a
# shellcheck disable=SC1090
source "$HOME/.config/agentpulse/cloudflare.env"
set +a
cd dashboard
VITE_API_BASE_URL=https://staging-api.agentpulse.ca npm run build
npx wrangler pages deploy dist --project-name=agentpulse-staging-app
```

## Mocked E2E (no DNS)

```bash
cd dashboard
npm ci
npx playwright install chromium
npm run test:e2e
# or: make dashboard-e2e
```

Coverage:

- anonymous → `/connect`
- claim form + `?claim_nonce=` auto-claim (nonce stripped from URL)
- fleet render
- account enrollment mint (DOM only; storage scrubbed)
- billing portal POST
- disconnect/logout
- inactive entitlement blocks enroll + fleet bounce to account
- invalid claim error
- denied fleet does not show foreign hosts
- no bearer / claim / enroll material in `localStorage` or `sessionStorage`

## Live staging E2E (after DNS + deploy)

Preferred: let Playwright create a Stripe **test-mode** Checkout Session and
pay with the Visa test card inside the browser. The success URL auto-claims;
no nonce is pasted into chat or shell history.

```bash
export AP_E2E_BASE_URL=https://staging-app.agentpulse.ca
export AP_E2E_API_BASE_URL=https://staging-api.agentpulse.ca
cd dashboard
npm run test:e2e:staging
```

Optional override when a fresh unclaimed nonce is already available privately:

```bash
export AP_E2E_CLAIM_NONCE='ap_claim_…'   # single use; do not commit or paste into chat
npm run test:e2e:staging
```

Do not log Checkout URLs, claim nonces, or enrollment tokens.

## Tier 3 release gate checklist

- [x] `staging-app.agentpulse.ca` resolves + TLS
- [x] Console built with `VITE_API_BASE_URL=https://staging-api.agentpulse.ca`
- [x] Mocked Playwright green in CI
- [x] Live Playwright claim/session/enroll/logout green
- [x] No production bearer in JS storage
- [x] No command-dispatch route in dashboard source

## Explicit non-goals here

- Opening public multi-host checkout
- Production `app.agentpulse.ca`
- Email/password or OAuth return login (deferred post–real browser E2E)
