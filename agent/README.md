# AgentPulse Agent

The thin, dependency-free Python monitoring + remediation daemon.

**Requirements:** Python 3.10+ for local verification. Linux/systemd and
macOS/launchd are intended service targets, but production packaging is not yet
released.

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

---

## Production installation status

Public system installation is not released. The repository contains systemd
and launchd implementation inputs, but the wheel currently packages no Python
modules and no versioned, checksummed install/upgrade/rollback lifecycle has
passed on clean hosts. Do not use the repository's draft installer on a
production host.

Phase 1 will publish exact Linux and macOS commands only after immutable
artifacts and rollback are verified. See `../docs/install.md` and
`../STATUS.md` for the current release boundary.

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

Version-aware uninstall and rollback instructions will ship with the verified
release artifact. Repository development runs do not install a system service.
