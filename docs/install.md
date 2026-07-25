---
layout: default
title: Install AgentPulse
---

# Install guide

> **Beta implementation status (2026-07-22):** The checksummed
> `v0.2.0-beta.2` prerelease passed exact-artifact clean-host installation,
> systemd runtime, outage recovery, restart, upgrade, rollback, uninstall, and
> reinstall acceptance on disposable Debian hosts. Public self-serve onboarding
> remains closed while checkout, account claim, secure sessions, billing, and
> enforced plan capacity are completed and proven.

AgentPulse is intended to run as a systemd service on Linux or a launchd daemon
on macOS. Its safe default is **alert-only** mode: it watches and changes
nothing until an operator promotes a bounded action.

## Current developer verification

Contributors can verify packaging and agent behavior without a system install:

```bash
./scripts/bootstrap-dev.sh
make agent-test
make agent-lint
make agent-config-validate
python -m pip install build
python -m unittest tests.test_packaging -v
```

This proves repository packaging behavior. It is not a clean-host installation
receipt.

## Accepted prerelease installation model

Supported production installs will use only immutable GitHub Release artifacts:

1. Choose the explicit accepted version `0.2.0-beta.2`.
2. Download the wheel and `SHA256SUMS` from the release tag.
3. Verify SHA-256.
4. Install with `scripts/install-agent.sh` (or the public endpoint once enabled).
5. Enroll atomically; credential file mode must be `0600`.
6. Smoke-test, then upgrade/rollback drills.

The public `install.sh` endpoint remains fail-closed until self-serve onboarding
is authorized. It will never download mutable files from a branch.

## Operator scripts (implementation path)

These scripts are implementation inputs for authorized lab/prerelease hosts:

- `scripts/install-agent.sh` — versioned release install + checksum + enroll
- `scripts/upgrade-agent.sh` — N→N+1 preserving config/state
- `scripts/rollback-agent.sh` — N+1→N preserving config/state
- `scripts/smoke-test.sh` — version, schema, perms, service, control-plane health
- `docs/runbooks/agent-release-rollback.md` — full runbook

Example lab install after a release artifact exists:

```bash
sudo ./scripts/install-agent.sh \
  --version 0.2.0-beta.2 \
  --api-url https://staging-api.agentpulse.ca
```

The installer prompts privately for the one-time enrollment token. For
unattended automation, provide the token over protected stdin with
`--enrollment-token-stdin`; never place it in command arguments or shell history.

## Recommended rollout

1. **Install** on one non-critical server first.
2. **Watch.** Leave every check in `alert` mode for 24 hours.
3. **See what it finds** using the version-pinned command published with the release.
4. **Promote one safe action** to `ask` (you approve each fix) or `auto`.
5. **Trust, then expand.** Only set `auto` for actions you would run over SSH
   yourself.

## What "auto" actually does

Every auto-fix runs the full decision loop before and after acting:

1. **Simulate** the fix as a dry-run.
2. **Validate** it against hard safety predicates (no system-path sweeps, no
   auto process-kill, allowlisted services only).
3. **Execute** the validated action.
4. **Verify** by re-measuring — and if the condition didn't clear, **escalate to
   you instead of retrying.**

## Want a hand?

Requests are being accepted for post-staging controlled onboarding. Onboarding
begins only after staging passes and an invitation is confirmed. [Request
consideration](signup) with your OS, stack, and the incidents that keep repeating.

## Uninstall and rollback

Use the version-aware scripts and runbook:

- Upgrade: `scripts/upgrade-agent.sh`
- Rollback: `scripts/rollback-agent.sh`
- Uninstall: `scripts/uninstall-agent.sh`
- Runbook: `docs/runbooks/agent-release-rollback.md`

Unassisted production installation remains unsupported until the paid account,
enrollment, and fleet lifecycle passes staging and controlled-pilot proof.
