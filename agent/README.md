# AgentPulse Agent

The thin, dependency-free Python monitoring + remediation daemon.

**Requirements:** Python 3.10+ for local verification. Linux/systemd and
macOS/launchd are intended service targets. The repository now builds a real
`agentpulse` wheel with packaged service assets; public production installation
remains gated on clean-host install/upgrade/rollback proof.

---

## Try it locally (no root, no install)

```bash
git clone https://github.com/strouddustinn-bot/agentpulse
cd agentpulse/agent

# Run one monitoring cycle — reads your real disk/process state, makes no changes
python3 -m agentpulse run-once --dry-run agentpulse.config.local.json
```

Expected output:
```
observations=3 breaches=0 actions=0 queued=0 alerts=0 anomalies=0 escalations=0 blocked=0 errors=0
```

If any check would have breached (e.g. disk >90%), you'll see `breaches=1 alerts=1`.
No files are touched, no services restarted — `--dry-run` is read-only.

### Validate a config

```bash
python3 -m agentpulse validate agentpulse.config.local.json
# OK: config is valid
```

### Run the full test suite

```bash
python3 tools/run_tests.py
```

Output:
```
============================================================
PASSED: 170   FAILED: 0
```

170 tests including a 7,500-iteration fuzz harness asserting safety invariants.
No pytest required — the runner is self-contained.

### Build and exercise the wheel (from repo root)

```bash
python3 -m pip install build
python3 -m build
python3 -m unittest tests.test_packaging -v
```

The packaging suite builds an isolated wheel, asserts package/service assets and
metadata, then installs into a fresh venv and runs `agentpulse --help`,
`validate`, and `run-once --dry-run`.

---

## Production installation status

Public system installation is not released. Packaging now produces a wheel that
includes:

- the `agentpulse` Python package and console script
- systemd unit and launchd plist assets
- example config and license metadata

Installers require an explicit release version and SHA-256 verification, and no
longer fetch raw files from a branch. Clean-host install, upgrade, and rollback
must still pass on an authorized host before public enablement. See
`../docs/install.md`, `../docs/runbooks/agent-release-rollback.md`, and
`../STATUS.md`.

---

## How the agent works

Every auto-fix runs the **verify-or-escalate loop** — no blind destructive actions:

```
Reason → Simulate (dry-run) → Gate (safety predicates) → Act → Verify → Record
```

If `Verify` shows the condition didn't clear, the agent **escalates to a human**
instead of retrying. The loop refuses to spiral.

See [ARCHITECTURE.md](../ARCHITECTURE.md) for the full design.
See [CONFIGURATION.md](CONFIGURATION.md) for all config fields.

---

## Uninstall and rollback

- Upgrade: `../scripts/upgrade-agent.sh`
- Rollback: `../scripts/rollback-agent.sh`
- Uninstall: `../scripts/uninstall-agent.sh`
- Runbook: `../docs/runbooks/agent-release-rollback.md`
