<div align="center">

# 🛡️ AgentPulse

### A self-serve Linux agent that monitors your servers and runs the first fix — safely

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
service on one Linux box. It watches three classes of repeat incident and, when
you allow it, runs the first safe fix:

- **Disk pressure** → removes old files inside cleanup paths *you* configure (never directories, never symlinks, never system paths).
- **Crashed service** → restarts a systemd service from *your* allowlist.
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

## What's NOT here yet (honest roadmap)

- Cloud dashboard / multi-server fleet view
- Baseline/ML learning of "normal"
- More remediation actions and integrations (Slack/Discord)
- Hosted control plane

v1 is a single-host agent you install and configure yourself. That's it — and
it's real, tested, and conservative on purpose.

## Guard rails are tested, not promised

The agent ships with a **60-test suite, including a 4,100-iteration fuzz harness**
asserting the safety invariants: never sweep a system path, never delete new
files / directories / symlinks, never auto-kill a process, refuse injection in
service names. Run it: `cd agent && python3 tools/run_tests.py`.

## Try it locally (no root, no install)

```bash
git clone https://github.com/strouddustinn-bot/agentpulse
cd agentpulse/agent
python3 -m agentpulse run-once --dry-run agentpulse.config.local.json
```

Reads your actual disk/process state, prints what it found, makes zero changes.

See **[agent/README.md](agent/README.md)** for the full local quickstart and
**[agent/CONFIGURATION.md](agent/CONFIGURATION.md)** for all config fields.

## Install on a server

```bash
curl -fsSL https://agentpulse.dustinnstroud.com/install.sh -o install.sh
less install.sh          # review it first — it runs as root
sudo bash install.sh     # installs the agent in alert-only mode
```

Then edit `/etc/agentpulse/config.json`, run `sudo agentpulse run-once /etc/agentpulse/config.json`
to see what it finds, and promote actions to `ask`/`auto` when you trust them.

## Pricing (paid beta)

| Plan | Price | Servers | What you get |
|------|-------|---------|-------------|
| **Starter** | $29/mo | 1 | The agent on one server, alerts + approval-gated fixes |
| **Pro Beta** | $99/mo | up to 5 | **Recommended:** all three fix classes, optional onboarding help |
| **Business Beta** | $299/mo | small fleet | Priority support, custom policies |

**Guarantee:** if AgentPulse doesn't catch or reduce one repeat incident in 30 days, the next month is free.

## Who It's For

- Indie SaaS founders running 1–10 Linux servers who get paged for the same fixes
- Solo developers on a VPS who can't justify enterprise monitoring pricing
- Small teams tired of being the on-call remediation layer

## Links

- 🌐 **Website:** [agentpulse.dustinnstroud.com](https://agentpulse.dustinnstroud.com)
- 💳 **Pricing:** [/pricing](https://agentpulse.dustinnstroud.com/pricing)
- 🚀 **Request beta access:** [/signup](https://agentpulse.dustinnstroud.com/signup)
- 📧 **Email:** support@agentpulse.dustinnstroud.com

## License

See [LICENSE](LICENSE). This repository contains the AgentPulse website and the
v1 agent (`agent/`). The hosted dashboard is in development.

---

<div align="center">

**Stop firefighting. Start sleeping.** 🛡️

[Request paid-beta access →](https://agentpulse.dustinnstroud.com/signup)

</div>
