---
layout: default
title: "AgentPulse Features — AI Server Monitoring That Fixes Problems Automatically"
description: "Auto-remediation, baseline learning, approval gates, real-time monitoring, and instant alerts. Everything AgentPulse does to keep your Linux servers running — without waking you up at 3 AM."
---

# AgentPulse Features

AgentPulse is a thin Linux monitoring agent with one job that most monitoring tools still refuse to do: **fix problems, not just report them**.

Here's everything it does.

---

## Auto-Remediation

This is the core feature — the reason AgentPulse exists.

When something goes wrong on your server, a traditional monitoring tool sends you an alert. You wake up, SSH in, run the same commands you always run, and go back to bed. AgentPulse skips straight to the "run the commands" part.

### Kill Runaway Processes

That Java app eating 4GB of RAM? Terminated. That Python script spinning at 100% CPU for the last 45 minutes? Gone.

AgentPulse tracks per-process resource consumption and acts when a process exceeds the thresholds you define — or the thresholds it learned from your server's normal behavior. You can set policies per process type: auto-kill, ask first, or alert only.

### Restart Crashed Services

nginx down? Postgres dropped? AgentPulse detects the crash and brings the service back up — in seconds, not minutes after your on-call rotation finally wakes up.

You define which services it should manage. It restarts them, reports what happened, and logs the event. If the service keeps crashing in a loop, it escalates instead of cycling endlessly.

### Free Disk Space

Log rotation silently failed two weeks ago and now your disk is at 94%. Classic.

AgentPulse monitors disk usage per-partition and can clean up based on your rules: rotate old logs, clear stale temp files, prune old application caches. You decide what's fair game. It never deletes things it doesn't have explicit permission to touch.

### Block SSH Brute-Force Attacks

AgentPulse watches auth logs for brute-force patterns — repeated failed SSH login attempts from the same IP — and can block the offending address automatically. Same logic as fail2ban, but integrated into the same agent watching the rest of your server.

No extra daemons to configure. No separate tool to maintain.

---

## Baseline Learning

Alerting on raw thresholds is how you end up with alert fatigue. A CPU spike to 90% at 3 AM is alarming. A CPU spike to 90% every night at 3 AM because your backup job runs — that's normal.

AgentPulse learns the difference.

### What It Learns

Over the first few days after install, AgentPulse builds a picture of your server's normal behavior:

- Which processes run at which times
- Typical CPU, RAM, and disk usage patterns by hour and day of week
- Known cron job spikes and maintenance windows
- Baseline network traffic patterns

Once it has a baseline, it stops alerting you about things you already know about.

### What It Flags

After baseline is established, AgentPulse focuses on **deviations from normal**:

- A service that's never used much RAM suddenly consuming gigabytes
- An API process that's been slowly leaking memory for the last six hours
- A new process that appeared this week and has been running constantly

Pattern-based alerting finds problems that threshold-based alerting misses entirely.

### Manual Overrides

You know your server better than the agent does. If AgentPulse is flagging something you know is expected, you can mark it as known behavior from the dashboard. It learns from your corrections.

---

## Approval Gates

You're not handing a bot unchecked root access to your production server. Approval gates let you decide exactly how much autonomy AgentPulse has — per action type, per service, per threshold.

### Three Modes Per Action

**Auto-fix** — AgentPulse acts immediately, then notifies you afterward.

> Example: "Always clean /tmp when disk usage exceeds 90%."

**Ask first** — AgentPulse sends you an alert and waits for your approval before acting.

> Example: "Nginx is down. Restart it? [Yes / No / Skip and just alert]"

**Alert only** — AgentPulse detects the problem and tells you, but doesn't touch anything.

> Example: "The database process is using abnormally high RAM. I'm not touching it — here's what I see."

### Why This Matters

Different actions carry different risk. Clearing /tmp is safe to automate. Restarting a database mid-transaction is not. Approval gates let you be surgical about autonomy instead of making a blanket "fix everything" or "fix nothing" choice.

You can start conservative — alert only on everything — and gradually move high-confidence, low-risk actions to auto-fix as you build trust in the agent's judgment.

---

## Real-Time Monitoring

AgentPulse runs continuously on your server, collecting metrics every few seconds and shipping them to the dashboard.

### What It Tracks

**CPU** — system-wide usage, per-core breakdown, load average (1m, 5m, 15m), top processes by CPU consumption.

**Memory** — total/used/free RAM, swap usage, per-process memory footprint, memory growth trends over time.

**Disk** — usage per partition, I/O throughput, inodes remaining, growth rate projection ("at this rate, disk fills in ~4 days").

**Processes** — running process list, resource consumption per process, crash detection, zombie process detection.

**Network** — inbound/outbound traffic rates, connection counts, unusual connection patterns.

**Security** — failed SSH login attempts, new listening ports, unexpected cron job changes, privilege escalation events.

### The Dashboard

Metrics feed into a real-time dashboard with current state and historical charts. You can see what's happening now, or look back at the last hour, day, or week to understand what changed and when.

No Grafana setup required. No InfluxDB to maintain. It's just there.

---

## Alerts

When something requires your attention and the agent can't (or isn't allowed to) handle it automatically, you get notified.

### Alert Channels

**Telegram** — instant message to your phone or a team channel. Fast, reliable, free. Works well for solo devs who want low-friction notifications.

**Email** — send alerts to any email address. Works with forwarding rules, filters, and whatever you already use to triage problems.

**Webhooks** — POST to any URL with a JSON payload. Wire it into Slack, Discord, PagerDuty, your own API, or anything else that accepts HTTP. Slack and Discord native integrations are on the roadmap — the webhook covers you today.

### Alert Content

Alerts aren't just "something broke." They include:

- What happened (the specific metric, threshold, and current value)
- Which process or service is involved
- What AgentPulse did (if it acted) or why it didn't
- Severity level
- A link to the relevant dashboard view

No more decoding a cryptic alert message at 3 AM trying to figure out which server is on fire.

### Alert Deduplication

AgentPulse groups related alerts and suppresses duplicates. If disk is at 91% and still climbing, you get one alert — not one every 30 seconds as it ticks upward. It re-alerts when severity changes (e.g., 91% → 95% → 99%) or when the situation resolves.

---

## 60-Second Install

{% include install.html %}

That's it. The installer:

1. Detects your Linux distribution (Ubuntu, Debian, CentOS, RHEL, Amazon Linux, and others)
2. Installs the agent as a systemd service
3. Connects to the AgentPulse platform with your account token
4. Starts monitoring immediately

No config files to edit before first use. No firewall rules to open (the agent initiates outbound connections). No dependencies to install manually. It works on any Linux server — VPS, bare metal, cloud instance, home lab.

The agent footprint is minimal: under 50MB RAM, under 1% CPU in steady state.

---

## How It Works

AgentPulse doesn't just match metrics against thresholds. Every potential remediation goes through a six-stage decision loop before anything runs on your server.

**Remember** — Before reasoning about an anomaly, the agent queries its baseline memory: what's normal CPU, RAM, disk, and process behavior for *this specific server*? A process spiking at 3 AM might be the nightly backup. The agent knows the difference.

**Reason** — Given the anomaly and its baseline context, the agent identifies candidate responses. Disk full: log rotation, temp file cleanup, or alert-only? Runaway process: kill, throttle, or escalate? Multiple options are weighed, not just the first rule that matches.

**Simulate** — Each candidate response is evaluated for consequences before it runs. Would killing this process break a dependent service? Is the process owned by a system account that warrants escalation instead? Lightweight consequence modeling prevents remediation that makes things worse.

**Gate** — Every proposed action is checked against your configured policies before it executes. Auto-fix actions run immediately. Ask-first actions pause for your approval. Alert-only actions stop here and notify you. Nothing runs against your policy.

**Act** — The validated action runs locally on your server — no cloud round-trip required. The agent records the outcome (what ran, what changed, whether it worked) and feeds that back into its memory for the next cycle.

**Share** *(roadmap)* — When AgentPulse runs across a fleet, agents share anonymized patterns. A novel attack signature detected on one server propagates as a defensive rule across all of them. Each agent is sovereign; the intelligence is collective.

The loop closes: act outcomes update the baseline, sharpening what the agent knows about your server. It gets more accurate over time.

Decision logic runs locally; baseline computation runs in the platform so it doesn't eat your server's resources. The agent holds a pre-authorized action set — a compromised platform cannot issue arbitrary commands to your servers.

---

## What It's NOT

AgentPulse is purpose-built for a specific problem. It doesn't try to do everything, and that's intentional.

**Not an APM tool.** AgentPulse doesn't trace request latency, instrument your application code, or correlate slow database queries with API response times. For distributed tracing and application performance monitoring, use Datadog, New Relic, or an OpenTelemetry-compatible tool.

**Not a log management platform.** There's no log aggregation, log search, or log-based alerting. AgentPulse watches system logs for specific security patterns (like SSH brute-force), but it doesn't ingest, index, or search your application logs. For that, use Loki, Papertrail, or a purpose-built log platform.

**Not an uptime checker.** AgentPulse monitors your server from the inside, not the outside. It can tell you a service crashed. It can't tell you whether your site is reachable from Europe. For external uptime monitoring, pair AgentPulse with Uptime Kuma or Better Stack's uptime checker.

**Not a status page tool.** No public status pages, no on-call scheduling, no incident communication workflows. Better Stack and incident.io handle that.

**Not free.** The agent source is open, but the platform is not. There's no self-hosted option. If you need free server monitoring, Netdata and Prometheus+Grafana are solid choices — they just won't fix anything.

**Not an enterprise observability platform.** No SSO, no RBAC, no SOC 2 compliance documentation, no 20-product pricing calculator. AgentPulse is for small teams who want things to work, not enterprise buyers who need a vendor to check boxes.

If you need any of those things, we'll point you toward tools that do them well. AgentPulse does one thing well: **keep your Linux servers running without waking you up to fix them.**

---

## Pricing

Plans start at $29/mo, with auto-remediation included from the Pro tier up. No per-host overages, no per-GB billing, no sales call required. Cancel anytime.

For the full plan breakdown, per-tier feature comparison, and FAQ, see the [pricing page](pricing).

---

## Ready to Stop Firefighting?

AgentPulse installs in 60 seconds and starts protecting your server immediately.

[**Get Started — Try AgentPulse Free →**](https://agentpulse.dustinnstroud.com/signup)

Questions? Email [support@agentpulse.dustinnstroud.com](mailto:support@agentpulse.dustinnstroud.com) or join the [Discord community](https://discord.gg/vCaXFWuc).
