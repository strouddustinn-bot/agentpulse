---
layout: default
title: Install AgentPulse
---

# Install guide

AgentPulse is a self-serve, dependency-free agent that runs as a systemd service
on Linux or a launchd daemon on macOS. It installs in **alert-only** mode — it watches and changes
nothing until you say so.

```bash
curl -fsSL https://agentpulse.dustinnstroud.com/install.sh -o install.sh
less install.sh          # review it — it runs as root
sudo bash install.sh
```

Linux requires Python 3.10+ and systemd. The Linux installer writes a default config to
`/etc/agentpulse/config.json`, registers the service, and starts it in
alert-only mode.

## macOS launchd install

Install the Python package, then run the packaged launchd installer:

```bash
python3 -m pip install agentpulse
sudo agentpulse install-launchd
```

The macOS installer writes `/usr/local/etc/agentpulse/config.json`, installs
`/Library/LaunchDaemons/com.agentpulse.agent.plist`, starts it with launchd,
and logs to `/usr/local/var/log/agentpulse/agentpulse.log`.

For service checks on macOS, configure launchd labels such as `com.apple.sshd`
or your own `com.company.service` labels.

## Recommended rollout

1. **Install** on one non-critical server first.
2. **Watch.** Leave every check in `alert` mode for 24 hours.
3. **See what it finds:** `sudo agentpulse run-once /etc/agentpulse/config.json`
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

## Approving ask-first actions

```bash
sudo agentpulse list-pending /etc/agentpulse/config.json
sudo agentpulse approve /etc/agentpulse/config.json <id>
```

## Want a hand?

Beta access includes optional onboarding help for your first server.
[Request beta access](signup) with your OS, stack, and the incidents that keep
repeating.

## Uninstall

```bash
# Linux
sudo systemctl disable --now agentpulse
sudo rm -rf /opt/agentpulse /usr/local/bin/agentpulse /etc/systemd/system/agentpulse.service /etc/agentpulse

# macOS
sudo launchctl bootout system /Library/LaunchDaemons/com.agentpulse.agent.plist
sudo rm -f /Library/LaunchDaemons/com.agentpulse.agent.plist
sudo rm -rf /usr/local/etc/agentpulse /usr/local/var/log/agentpulse
```
