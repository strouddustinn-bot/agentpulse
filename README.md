<div align="center">

# 🛡️ AgentPulse

### A self-serve Linux/macOS agent that monitors your hosts and runs the first fix — safely

*Alerts wake you. AgentPulse acts, verifies, and escalates if the fix didn't hold.*

[![Tests](https://github.com/strouddustinn-bot/agentpulse/actions/workflows/test.yml/badge.svg)](https://github.com/strouddustinn-bot/agentpulse/actions/workflows/test.yml)
[![Website](https://img.shields.io/badge/Website-agentpulse.dustinnstroud.com-blue?style=for-the-badge)](https://agentpulse.dustinnstroud.com)
[![Paid Beta](https://img.shields.io/badge/Paid%20Beta-Request%20access-green?style=for-the-badge)](https://agentpulse.dustinnstroud.com/signup)
[![Pricing](https://img.shields.io/badge/From-%2429%2Fmo-orange?style=for-the-badge)](https://agentpulse.dustinnstroud.com/pricing)

</div>

---

## The Problem

Every monitoring tool will happily wake you at 3 AM. Almost none will fix the problem.

1. 🔴 Alert fires — "Disk critical on server-01"
2. 😴 You SSH in, bleary-eyed
3. ⌨️ You run the same three commands you always run
4. 🛏️ Back to bed
5. 🔁 Two weeks later, same alert, same commands

**You're the remediation layer. The point of AgentPulse is to stop being it.**

## What AgentPulse Does (today, for real)

AgentPulse is a thin, **dependency-free Python agent** that runs as a systemd
service on Linux or a launchd daemon on macOS. It watches three classes of repeat incident and, when
you allow it, runs the first safe fix:

- **Disk pressure** → removes old files inside cleanup paths *you* configure (never directories, never symlinks, never system paths).
- **Crashed service** → restarts a systemd service on Linux or launchd service on macOS from *your* allowlist.
- **Memory runaway** → flags the largest offender. (It never kills a process automatically in v1.)

### Safe by default

Every check ships in **alert-only** mode. The agent only *watches* until you
change a check to `ask` (it queues the fix for your approval) or `auto` (it acts
on its own). Nothing is auto-fixed out of the box.

### Every fix runs the verify-or-escalate loop

No blind destructive actions. Each auto-fix goes through a full cycle:

`Reason` (expected end-state) → `Simulate` (dry-run first) → `Gate`
(executable safety predicates) → `Act` → **`Verify`** (re-measure) → `Record`.

If the verify step shows the condition didn't clear, the agent **escalates to a
human instead of retrying** — the loop refuses to spiral.

## What ships today vs. what's roadmap

Shipped today:

- Linux/macOS agent with safe local remediation
- Agent-to-backend check-ins (`/api/agent/checkin`)
- Backend fleet status API (`/api/agents`, recent check-ins)
- License key storage/verification API
- Docker packaging for agent and backend

Still roadmap:

- Browser dashboard / polished multi-server fleet UI
- Stripe billing portal integration
- ML-grade pattern learning (a statistical baseline — per-metric mean/variance with advisory anomaly alerts — ships today in `baseline.py`)
- More remediation actions and native integrations (Slack/Discord webhooks work today via `notify.webhook_url`)

v1 is conservative on purpose: the agent keeps working locally even if the backend is down.

## Guard rails are tested, not promised

The agent ships with a **96-test suite, including a 7,500-iteration fuzz harness**
asserting the safety invariants: never sweep a system path, never delete new
files / directories / symlinks, never auto-kill a process (even when approved),
refuse injection in service names, and fail the safety gate closed on any action
it doesn't explicitly allow. Run it: `cd agent && python3 tools/run_tests.py`.

## Try it locally (no root, no install)

```bash
git clone https://github.com/strouddustinn-bot/agentpulse
cd agentpulse/agent
python3 -m agentpulse run-once --dry-run agentpulse.config.local.json
```

Reads your actual disk/process state, prints what it found, makes zero changes.

See **[agent/README.md](agent/README.md)** for the full local quickstart,
**[agent/CONFIGURATION.md](agent/CONFIGURATION.md)** for all config fields, and
**[backend/README.md](backend/README.md)** for the backend API.

## Install on a host

Linux production installs use systemd:

```bash
curl -fsSL https://agentpulse.dustinnstroud.com/install.sh -o install.sh
less install.sh          # review it first — it runs as root
sudo bash install.sh     # installs the agent in alert-only mode
```

Then edit `/etc/agentpulse/config.json`, run `sudo agentpulse run-once /etc/agentpulse/config.json`
to see what it finds, and promote actions to `ask`/`auto` when you trust them.

macOS production installs use launchd:

```bash
python3 -m pip install agentpulse
sudo agentpulse install-launchd
sudo agentpulse run-once /usr/local/etc/agentpulse/config.json
```

Then edit `/usr/local/etc/agentpulse/config.json` and use launchd labels in `checks.service.services`.

## Pricing (paid beta)

| Plan | Price | Servers | What you get |
|------|-------|---------|-------------|
| **Starter** | $29/mo | 1 | The agent on one server, alerts + approval-gated fixes |
| **Pro Beta** | $99/mo | up to 5 | **Recommended:** all three fix classes, optional onboarding help |
| **Business Beta** | $299/mo | small fleet | Priority support, custom policies |

**Guarantee:** if AgentPulse doesn't catch or reduce one repeat incident in 30 days, the next month is free.

## Who It's For

- Indie SaaS founders running 1–10 Linux/macOS hosts who get paged for the same fixes
- Solo developers on a VPS who can't justify enterprise monitoring pricing
- Small teams tired of being the on-call remediation layer

## Links

- 🌐 **Website:** [agentpulse.dustinnstroud.com](https://agentpulse.dustinnstroud.com)
- 💳 **Pricing:** [/pricing](https://agentpulse.dustinnstroud.com/pricing)
- 🚀 **Request beta access:** [/signup](https://agentpulse.dustinnstroud.com/signup)
- 📧 **Email:** support@agentpulse.dustinnstroud.com

## License

See [LICENSE](LICENSE). This repository contains the AgentPulse website, the
v1 agent (`agent/`), and the backend API (`backend/`). The hosted dashboard UI is in development.

---

<div align="center">

**Stop firefighting. Start sleeping.** 🛡️

[Request paid-beta access →](https://agentpulse.dustinnstroud.com/signup)

</div>
