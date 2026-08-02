# Production smoke verification (Tier 4 / Phase 5B)

## Purpose and authority boundary

`scripts/production-smoke.py` is a **read-only, fail-closed post-deploy verifier** for the AgentPulse production console and API. It performs bounded unauthenticated `GET` requests only. It does not use credentials or call checkout, billing, claim, enrollment, migration, deployment, DNS, or provider mutation routes.

A passing smoke run proves only the checks listed below against the URLs fetched in that run. It does not authorize production deployment, open checkout, close rollback evidence, or replace the controlled pilot gate.

## Checks

The command requires an explicit package version and full 40-character source commit SHA, then verifies:

1. `https://app.agentpulse.ca/` and `/account` both return the real built dashboard shell directly over HTTPS with the exact HTML media type: dashboard title, `#root`, hashed JavaScript and CSS assets, and no placeholder marker.
2. `https://app.agentpulse.ca/deployment.json` is strict JSON with an exact identity-only schema: `agentpulse-dashboard`, environment `production`, the expected version/source SHA, `https://api.agentpulse.ca`, and the main JavaScript SHA-256. Additional fields are blockers.
3. The fetched main dashboard asset has a JavaScript media type, its built API-base assignment selects `https://api.agentpulse.ca` without unknown assigned URL literals, and its bytes match the manifest SHA-256.
4. `https://api.agentpulse.ca/health` returns HTTP 200 strict JSON with `ok=true`, service `agentpulse-control-plane`, environment `production`, and the exact expected version.
5. Trusted-origin CORS grants the production app origin with credentials and `Vary: Origin`; fixed untrusted, staging-console, and local-development origins are probed against both health and account and must receive no CORS headers.
6. Unauthenticated `GET /v1/account` fails closed with HTTP 401 and the canonical `unauthorized` JSON error while preserving trusted console CORS.
7. Redirects are not followed. Redirect responses, duplicate HTTP/CORS headers, duplicate JSON keys, non-standard JSON constants, non-JSON media types, oversized bodies, TLS/DNS/timeout failures, and mixed evidence are blockers.

Every request owns its own response body. A failed request cannot reuse or report a prior successful body.

## Run it

After an immutable production deploy candidate exists:

```bash
./scripts/production-smoke.py \
  --expected-version 0.3.0 \
  --expected-source-sha "$(git rev-parse HEAD)"
```

Optional URL overrides exist for controlled tests, but both values must be absolute origin-only HTTPS URLs:

```bash
./scripts/production-smoke.py \
  --expected-version 0.3.0 \
  --expected-source-sha 0123456789abcdef0123456789abcdef01234567 \
  --app-url https://app.agentpulse.ca \
  --api-url https://api.agentpulse.ca
```

Do not use `latest`, a branch name, a short SHA, or a guessed version. Pass the exact `AGENTPULSE_VERSION` and full source commit from the immutable release being verified.

The production console deployment must create `deployment.json` in its publish artifact before Pages deployment:

```json
{
  "service": "agentpulse-dashboard",
  "environment": "production",
  "version": "0.3.0",
  "source_sha": "0123456789abcdef0123456789abcdef01234567",
  "api_base_url": "https://api.agentpulse.ca",
  "main_js_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

This public file contains exactly those six deployment-identity fields—never tokens, account identifiers, customer data, provider IDs, secrets, or additional metadata.

## Verdicts

Success:

```text
PRODUCTION_SMOKE=PASS
[PASS] console_root_shell: real built console shell served
...
No billing, credential, migration, DNS, deployment, or provider mutation was performed.
```

Blocked production DNS or transport:

```text
PRODUCTION_SMOKE=BLOCKED
[BLOCK] console_root_transport: transport failed: URLError
...
```

The command exits zero only when every check passes. Never suppress or downgrade a blocker in the deployment workflow.

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_production_smoke -v
```

The suite covers the full passing contract, package-version/source-SHA inputs, redirect refusal, strict JSON/media parsing, exact manifest schema and asset digest, placeholder/missing-asset shells, selected API-base drift, duplicate/trusted/untrusted CORS, unauthenticated-account fail-open behavior, and response isolation after transport failure.

## Deployment sequence

Run this command only after the protected immutable-ref preflight, migration status/approval, Worker deploy, and production console deploy. The deploy workflow must generate the identity-only `deployment.json` from the immutable workflow ref before publishing the console. Persist the redacted verdict with the immutable release identity, then continue to rollback, D1 backup/restore, observability, and controlled-pilot evidence. Keep public checkout closed throughout Tier 4 and the pilot.
