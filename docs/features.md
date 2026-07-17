---
layout: default
title: "AgentPulse Features — Server Monitoring That Fixes Problems, Safely"
description: "Policy-gated auto-remediation, a verify-or-escalate decision loop, statistical baseline learning, and approval gates. Everything AgentPulse does today to keep your Linux and macOS hosts running — and what's on the roadmap."
---

# AgentPulse Features

AgentPulse is a thin Linux/macOS monitoring agent with one job that most monitoring tools still refuse to do: **fix problems, not just report them**.

Here's everything it does today — and, clearly labeled, what's on the roadmap. We'd rather under-promise than surprise you at 3 AM.

---

## Auto-Remediation

This is the core feature — the reason AgentPulse exists.

When something goes wrong on your server, a traditional monitoring tool sends you an alert. You wake up, SSH in, run the same commands you always run, and go back to bed. AgentPulse skips straight to the "run the commands" part — for the incident classes where a safe first fix exists.

### Free Disk Space

Log rotation silently failed two weeks ago and now your disk is at 94%. Classic.

AgentPulse monitors disk usage per configured path and cleans up based on your rules: it deletes files older than a threshold you set, **only inside cleanup paths you explicitly configure**. It never deletes directories, never follows symlinks, and refuses system paths outright — those guards are code-level invariants, not config.

### Restart Crashed Services

nginx down? A worker died? AgentPulse detects the failed systemd unit on Linux or launchd service on macOS and brings it back up — in seconds, not minutes after your on-call rotation finally wakes up.

You define an allowlist of services it may manage. It restarts them, verifies they actually came back, and reports what happened. If the restart doesn't hold, it escalates to you instead of cycling endlessly.

### Flag Runaway Processes

That Python script eating half your RAM? AgentPulse spots the largest offender when it crosses your memory threshold and tells you exactly which process it is.

**It never kills a process automatically in v1 — even if you set the process check to "auto", the agent clamps it to ask-first.** Killing the wrong process is the one remediation that can make a bad night catastrophically worse, so a human stays in that loop by design. You get the flag, you make the call.

---

## The Verify-or-Escalate Decision Loop

Every fix — automatic or human-approved — runs the same six-stage loop before and after anything touches your server:

**Reason** — the agent states the expected end-state before acting. "Disk usage on `/` should drop below the threshold after removing old files." No action without a testable expectation.

**Simulate** — the fix runs as a dry-run first, and the agent captures exactly what *would* change. A simulation that fails or matches nothing stops the cycle right there.

**Gate** — the simulated plan is checked against hard safety predicates: no system-path sweeps, no process kills, allowlisted services only, and a fail-closed action allowlist — an action type the gate doesn't explicitly recognize is refused, period. Human approval doesn't bypass the gate either.

**Act** — the validated action runs locally on your server. No cloud round-trip, no dependency on an external API being reachable at 3 AM.

**Verify** — the agent re-measures the original condition. Did disk usage actually drop? Is the service actually active? A fix that ran but didn't clear the breach — or that ran and changed nothing — is **escalated to you instead of retried**. The loop refuses to spiral.

**Record** — the full cycle (expectation, simulation, gate verdict, execution, verification, outcome) is captured for analysis, so you can always answer "what did the agent do and why?"

These guarantees aren't promises — they're enforced by a 170-test suite including a 7,500-iteration fuzz harness you can run yourself: `cd agent && python3 tools/run_tests.py`.

---

## Baseline Learning

Alerting on raw thresholds is how you end up with alert fatigue. A disk that has hovered at 89% for a month is not news. A disk that jumped ten points overnight is — even if it hasn't crossed your threshold yet.

AgentPulse learns the difference with **statistical baselines**: for each metric (disk usage per path, host memory), it maintains a running mean and variance of what's normal *for this specific server*, and flags samples that deviate sharply from the learned normal (z-score based, with a warm-up period so it never alerts before it has enough data).

Two honest caveats:

- It's statistics, not machine learning — deterministic, dependency-free, and inspectable. Learned per-hour/per-weekday patterns are on the roadmap.
- Baseline anomalies are **advisory only**. They alert; they never trigger a remediation. Only your explicit threshold policies can do that.

---

## Approval Gates

You're not handing a bot unchecked root access to your production server. Every check runs in one of four modes, and you set each one independently:

**Alert only** *(the default for everything)* — AgentPulse detects the problem and tells you, but doesn't touch anything.

> "Disk / at 91.3% (threshold 90%). I'm not touching it — here's what I see."

**Ask first** — AgentPulse queues the fix and waits for your explicit approval:

```bash
sudo agentpulse list-pending /etc/agentpulse/config.json
sudo agentpulse approve /etc/agentpulse/config.json <id>
```

Approved actions still run the full decision loop — simulate, gate, verify. Approval is consent, not a safety bypass.

**Auto-fix** — AgentPulse acts immediately, then notifies you with exactly what changed.

**Off** — the check doesn't run at all.

### Why This Matters

Different actions carry different risk. Clearing old files in `/tmp` is safe to automate. Restarting a database mid-transaction is not. Per-check modes let you be surgical about autonomy instead of making a blanket "fix everything" or "fix nothing" choice.

Start conservative — controlled beta evaluations begin in alert-only mode — and promote high-confidence, low-risk actions to ask-first, then auto, as the agent earns your trust.

---

## Alerts

When something requires your attention — a breach, a queued approval, an escalation, a baseline anomaly — you get notified.

### Channels today

**Webhook** — POST to any URL with a JSON payload. This is how you wire AgentPulse into Slack, Discord, PagerDuty, or your own API today: point it at an incoming-webhook URL and you're done. If webhook delivery fails, the agent falls back to logging the alert rather than crashing or going silent.

**stdout / journald** — every alert is always visible in `journalctl -u agentpulse`, no configuration needed.

Native Telegram and email channels are on the roadmap — the webhook covers those flows today via services you already use.

### Alert content

Alerts aren't just "something broke." They include what happened (metric, threshold, current value), which resource is involved, what AgentPulse did or why it didn't act, and — for escalations — an explicit statement that a fix ran and did not hold.

---

## Installation status

Public self-serve installation is a release gate, not a shipped feature. The
current source can be verified from a checkout, but the draft installer depends
on unpublished packaging and has not passed clean-host install, upgrade, and
rollback tests. See the [installation status](install) before operating the
agent outside a development checkout.

---

## Deployment and roadmap gaps

These are planned, not shipped. Nothing below is included in what you buy today:

- **Secure public console deployment** — fleet and incident views exist in source, but secure browser sessions and public deployment are not released.
- **SSH brute-force detection & blocking** — fail2ban-style auth-log watching, integrated into the same agent.
- **Native Telegram / email / Slack channels** — beyond the generic webhook.
- **Learned time-of-day baselines** — "the backup always spikes at 3 AM" as a first-class concept.
- **Fleet intelligence** — agents sharing anonymized patterns across your servers, so a pattern caught on one box hardens all of them.

If any of these is the thing you need *first*, tell us at [support@agentpulse.ca](mailto:support@agentpulse.ca) — beta users steer the order.

---

## What It's NOT

AgentPulse is purpose-built for a specific problem. It doesn't try to do everything, and that's intentional.

**Not an APM tool.** AgentPulse doesn't trace request latency, instrument your application code, or correlate slow database queries with API response times. For distributed tracing and application performance monitoring, use Datadog, New Relic, or an OpenTelemetry-compatible tool.

**Not a log management platform.** There's no log aggregation, log search, or log-based alerting. For that, use Loki, Papertrail, or a purpose-built log platform.

**Not an uptime checker.** AgentPulse monitors your server from the inside, not the outside. It can tell you a service crashed. It can't tell you whether your site is reachable from Europe. For external uptime monitoring, pair AgentPulse with Uptime Kuma or Better Stack's uptime checker.

**Not a status page tool.** No public status pages, no on-call scheduling, no incident communication workflows. Better Stack and incident.io handle that.

**Not free.** The agent source is public so you can audit exactly what runs as root on your server — but AgentPulse is a paid product. If you need free server monitoring, Netdata and Prometheus+Grafana are solid choices — they just won't fix anything.

**Not an enterprise observability platform.** No SSO, no RBAC, no SOC 2 compliance documentation, no 20-product pricing calculator. AgentPulse is for small teams who want things to work, not enterprise buyers who need a vendor to check boxes.

If you need any of those things, we'll point you toward tools that do them well. AgentPulse does one thing well: **keep your Linux/macOS hosts running without waking you up to fix them.**

---

## Pricing

Plans start at an indie-friendly monthly price, with auto-remediation included from the Pro tier up. No per-host overages, no per-GB billing, no sales call required. Cancel anytime.

For the full plan breakdown, per-tier feature comparison, and FAQ, see the [pricing page](pricing).

---

## Ready to Stop Firefighting?

Public installation is not released. Controlled beta evaluation starts on one non-critical host in alert-only mode after the operator reviews the current release gates.

[**Join the paid beta →**](https://agentpulse.ca/signup)

Questions? Email [support@agentpulse.ca](mailto:support@agentpulse.ca).
