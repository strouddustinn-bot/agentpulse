# AgentPulse Agent

The thin, dependency-free Python monitoring + remediation daemon.

**Requirements:** Python 3.8+ · Linux (systemd for production; not required for local testing)

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
PASSED: 66   FAILED: 0
```

66 tests including a 4,100-iteration fuzz harness asserting safety invariants.
No pytest required — the runner is self-contained.

---

## Install as a systemd service (production)

```bash
curl -fsSL https://agentpulse.dustinnstroud.com/install.sh -o install.sh
less install.sh          # review it — it runs as root
sudo bash install.sh
```

This installs the agent in **alert-only mode** — it watches but changes nothing until
you explicitly promote a check to `ask` (approval required) or `auto` (acts on its own).

After install:
```bash
# See what the agent finds right now
sudo agentpulse run-once /etc/agentpulse/config.json

# Start the daemon
sudo systemctl start agentpulse
sudo journalctl -u agentpulse -f

# Approve a queued action (if mode = "ask")
sudo agentpulse list-pending /etc/agentpulse/config.json
sudo agentpulse approve /etc/agentpulse/config.json <id>
```

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

## Uninstall

```bash
sudo systemctl disable --now agentpulse
sudo rm -rf /opt/agentpulse /usr/local/bin/agentpulse /etc/systemd/system/agentpulse.service
```
