# Runbook: Agent release, upgrade, and rollback

## Purpose

Operate versioned AgentPulse agent packages as immutable release artifacts. Never
install from a mutable branch (`main`/`master` raw files).

## Artifacts

Each GitHub Release for the agent must include:

- `agentpulse-<version>-py3-none-any.whl`
- matching sdist (optional but published)
- `SHA256SUMS`

## Clean-host install (Linux)

```bash
# Replace VERSION and TOKEN. Do not paste secrets into chat logs.
sudo ./scripts/install-agent.sh \
  --version VERSION \
  --enrollment-token TOKEN \
  --api-url https://staging-api.agentpulse.ca
```

What the installer does:

1. Downloads only from `https://github.com/<repo>/releases/download/vVERSION/`.
2. Verifies SHA-256 against `SHA256SUMS`.
3. Installs the wheel.
4. Writes alert-only config under `/etc/agentpulse/config.json` (mode 0640).
5. Installs the packaged systemd unit (not a raw branch file).
6. Exchanges the one-time enrollment token, persists the credential at mode 0600,
   and does not leave the enrollment token in config JSON.
7. Validates config, dry-runs once, starts the service.

## Upgrade (preserve config/state)

```bash
sudo ./scripts/upgrade-agent.sh --version NEWER_VERSION
```

Preserves `/etc/agentpulse` and `/var/lib/agentpulse`. Records the previous
version under `/var/lib/agentpulse/releases/previous-version`.

## Rollback (preserve config/state)

```bash
sudo ./scripts/rollback-agent.sh --version PREVIOUS_VERSION
```

Reinstalls the prior immutable wheel after checksum verification.

## Smoke test

```bash
sudo ./scripts/smoke-test.sh --config /etc/agentpulse/config.json
```

Checks:

- binary and version
- config schema via `agentpulse validate`
- credential mode 0600 when enrolled
- service state
- control-plane `/health` when configured

## Lab-only offline install

```bash
sudo ./scripts/install-agent.sh \
  --version 0.1.0 \
  --wheel ./dist/agentpulse-0.1.0-py3-none-any.whl \
  --checksums ./dist/SHA256SUMS \
  --skip-enroll \
  --skip-start
```

`--skip-checksum` is lab-only and must not be used for production hosts.

## Public endpoint status

`docs/install.sh` (published as the public install URL) remains fail-closed until
clean-host install, upgrade, and rollback are proven on authorized hosts.

## Evidence checklist for a release candidate

- [ ] Packaging tests green on Python 3.10–3.13
- [ ] Wheel contains package, systemd unit, launchd plist, example config, license
- [ ] Fresh-venv `agentpulse --help`, `validate`, `run-once --dry-run` pass
- [ ] Release assets include wheel + SHA256SUMS
- [ ] Clean Linux host install/upgrade/rollback evidence captured (redacted)
- [ ] Optional macOS launchd path evidence captured (redacted)
- [ ] No raw branch downloads remain in installer paths
