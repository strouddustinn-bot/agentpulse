# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Backend: FastAPI app with health, readiness, version, and ingestion endpoints
- Backend: SQLite store with agent inventory, check-in log, and incident tables
- Backend: enrollment token validation, agent credential management, HMAC verification
- Dashboard: React 19 + TypeScript frontend with server inventory and incident views
- Dashboard: backend Flask API with billing integration and Stripe webhooks
- Control-plane: Cloudflare Worker with D1 database and email routing
- CI: GitHub Actions workflow for lint, typecheck, and test across all components
- Observability: Prometheus metrics endpoint, Grafana dashboard JSON, alert rules
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
