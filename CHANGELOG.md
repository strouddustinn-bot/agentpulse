# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Beta 4 recovery
- The controlled production workflow now targets immutable `v0.2.0-beta.4` / package `0.2.0b4` after beta 3 exposed a first-deployment DNS deadlock.
- Pre-deploy Cloudflare state is captured through read-only Workers and Pages APIs; unresolved DNS may defer only when both the production Worker and production Pages deployment are proven absent.
- Post-deploy production smoke uses bounded full-gate retries while keeping TLS, source identity, CORS, session denial, asset integrity, and closed checkout mandatory.
- Stripe preflight now distinguishes authentication, permission, missing Price, rate-limit, and provider-availability failures without exposing response bodies or credentials.
- Forced `nanoid` resolution is advanced to patched `3.3.18` in both Node workspaces.

### Added
- Staging commercial lifecycle harness now has fail-closed `prepare`/`prove` phases, private checkout handoff semantics, exact receipt markers, and a disposable callback Worker artifact for absent staging-app DNS.

### Changed
- Checkout responses now include server-derived `checkout_session_id` and `livemode`; staging rejects non-`cs_test_` or live-mode Stripe sessions before persisting capability URLs.
- Phase 3D planning/status/API/runbook claims now require migrations `0002` and hard-fail `0003`, duplicate-subscription preflight, and redacted staging proof before any completion claim.

### Fixed
- Control-plane webhook concurrency tests no longer depend on body-consumption/rendezvous ordering that can hang the Worker test pool.


## [0.2.0b2] — 2026-07-22

### Fixed
- Control-plane heartbeat path now durably spools outage evidence
- Queued check-in evidence is automatically replayed by the runtime
- Enrollment tokens no longer exposed through process arguments (stdin/prompt)
- Installer dry-run failure is now fail-closed
- Smoke-test warnings can no longer be reported with success status
- Upgrade and rollback now fully enforce the requested resulting version
- Non-purge uninstall uses secure `mktemp` backup destination
- Declining purge now stops destructive deletion
- State writes use atomic mode-0600 files
- Python 3.11 `urllib.request.urlopen` timeout call fixed (positional arg)
- Spool is now process-locked, storage-bounded, strict-FIFO with quarantine
- Credential-recovery propagation preserves the current event
- Permanent HTTP responses are quarantined instead of blocking FIFO
- Backend replay budget converges multi-event backlogs to zero

### Changed
- Published `v0.2.0-beta.1` artifact is rejected; this is the replacement prerelease
- Public installation remains closed until exact-artifact clean-host acceptance passes

## [0.2.0b1] — 2026-07-17

### Added
- Real `agentpulse` wheel packaging via hatchling with console script, systemd unit, launchd plist, example config, and license assets
- Packaging integrity suite (`tests/test_packaging.py`) covering wheel contents, metadata, exclusions, and fresh-venv CLI smoke
- CI packaging matrix on Python 3.10–3.13
- Versioned install/upgrade/rollback scripts with SHA-256 verification and config/state preservation
- Release workflow job that builds wheel/sdist and publishes `SHA256SUMS` without requiring production control-plane deploy for agent prereleases
- Operator runbook `docs/runbooks/agent-release-rollback.md`

### Fixed
- Root `pyproject.toml` no longer ships an empty wheel (`packages = []`)
- Installer no longer downloads service files from mutable branch raw URLs

## [0.1.0] — 2026-07-12

### Added
- Agent: Linux systemd service with restart-on-failure and logrotate rotation
- Agent: launchd service definition for macOS production use
- Agent: baseline anomaly detection (Welford online mean/variance, z-score, min-abs-deviation)
- Agent: decision_loop with IMAGINE→SIMULATE→VALIDATE→EXECUTE→VERIFY→RECORD cycle
- Agent: fail-closed policy engine with ceiling enforcement
- Agent: process remediation with dry-run, escalation gating, and history audit log
- Agent: offline queue (bounded spool) with reconnect flush
- Agent: control-plane enrollment and heartbeat transport (hmac-signed, replay-resistant)
- Agent: CLI with install, enroll, start, stop, status, check-in, check, remediate, doctor, config, baseline, update, version, uninstall commands
- Agent: 108-passing test suite including a 7,500-iteration fuzz harness
- Control-plane: Cloudflare Worker + D1 tenant isolation, enrollment, policy narrowing, heartbeat ingestion, incident materialization, fleet reads, and Stripe signature verification
- Dashboard: one read-only React console consuming the authenticated Worker fleet contract
- Contracts: versioned OpenAPI, JSON Schema, and representative fixtures
- CI: GitHub Actions workflows for agent, Worker, dashboard, contract, shell, and security verification
- Security: fail-closed enrollment, HMAC-signed payloads, mode-0600 credential files,
  bounded offline spool, deduplication, and cooldown enforcement

### Fixed
- `httpx2>=2,<3` pinned correctly for Starlette 1.x TestClient compatibility
- Dashboard frontend TypeScript project references restored (tsconfig.json composite)
- `agent/agentpulse/control_plane.py`: corrupted merge artifact (`authorization: ***`) resolved
- `control-plane/package.json`: `types:check` guarded with Node-22 runtime check
- `.github/workflows`: Node version pinned to `22.x`

### Security
- No credentials, API keys, tokens, or connection strings in the repository
- Agent credentials stored in mode-0600 files outside JSON config
- HMAC-SHA256 payload signing on all control-plane communications
- Replay-resistant enrollment tokens with bounded validity windows
- Secret redaction in logs and transmitted payloads
- Tenant isolation enforced at the D1 database layer

[0.1.0]: https://github.com/strouddustinn-bot/agentpulse/releases/tag/v0.1.0
