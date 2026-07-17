---
layout: default
title: AgentPulse - AI Server Monitoring That Fixes Incidents
---

# AI server monitoring that fixes repeat incidents before they page you

AgentPulse is a local-first Linux/macOS remediation agent being prepared for
founders and small teams running 1-10 hosts. The source already enforces an
alert-only default and bounded remediation; public packaging and deployment are
still release gates.

> **Controlled beta, alert-only by default.** Every auto-fix runs a
> verify-or-escalate loop — simulate, validate, execute, then **verify** — and
> escalates if the fix does not hold. Public self-serve installation is not yet
> released. [Current installation status →](install)

[Installation status](install) | [See pricing](pricing) | [Request controlled beta access](signup)

*Best for founders running 1–10 Linux/macOS hosts on Hetzner, DigitalOcean, Linode, Vultr, AWS Lightsail, or Mac minis.*

## What the current implementation provides

- **Stop being the remediation layer:** cover disk pressure, crashed services, runaway processes, and other repeat host incidents.
- **Start conservative:** begin alert-only, then promote trusted actions to ask-first or auto-fix.
- **Get setup help:** use paid beta onboarding to protect the first server instead of configuring another dashboard alone.
- **Keep control:** scope every policy by server and action type before anything runs automatically.

## Built for the servers that wake founders up

Most monitoring products stop at alerts. AgentPulse focuses on the repeat incidents that already have obvious first moves: restart the service, clear disk pressure, stop the runaway job, or ask for approval before touching something risky.

| Pain | Standard monitoring | AgentPulse |
| --- | --- | --- |
| Disk fills at 3 AM | Sends an alert | Removes old files inside the cleanup paths you configure, then reports what changed |
| Worker crashes | Tells you it is down | Restarts the systemd/launchd service from your allowlist, then verifies it came back |
| Memory runaway | Shows a spike | Flags the largest offender (never auto-kills in v1) |
| Fix didn't hold | — | Re-checks after acting and escalates to you instead of retrying |

*Controlled beta evaluation starts alert-only. You choose what AgentPulse may auto-fix, and every auto-fix is simulated and verified before and after it runs. Statistical baseline learning is built in (advisory anomaly alerts). Bounded heartbeats and incident evidence can synchronize to the Worker/D1 control plane; fleet-console source exists, but public deployment remains a release gate.*

## Paid beta offer

We are onboarding the first users as a paid beta so the remediation policies can be tuned against real servers instead of fake demos.

| Plan | Price | Best for | Includes |
| --- | --- | --- | --- |
| Starter | C$29/mo CAD | 1 production VPS | Monitoring, alerts, manual remediation approvals |
| **Pro Beta — recommended** | **C$99/mo CAD** | Up to 5 servers | All three fix classes (disk, service, memory), verify-or-escalate remediation, optional onboarding |
| Business Beta | C$299/mo CAD | Small teams | Owner-approved finite server limit, priority setup, custom policies |

[Reserve your Pro Beta slot](signup) — we reply within a few hours during the launch window.

## How onboarding works

1. Request a controlled pilot for one non-critical server; public installation is not released.
2. It starts in alert-only mode — nothing changes automatically.
3. Run `agentpulse run-once` to see the repeat incidents it detects.
4. Promote safe fixes to ask-first, then auto-fix once you trust the policy. Need a hand? Beta access includes optional onboarding help.

You stay in control. AgentPulse does not need unchecked root access to be useful, and every risky action should begin behind an approval gate.

## Built to start safely

AgentPulse is designed to start conservative. Beta onboarding begins in alert-only mode, and risky actions should stay behind ask-first approval until you explicitly promote them. Every remediation policy should be visible, reversible, and scoped to the server where it runs.

## Comparisons

- [AgentPulse vs Netdata](vs-netdata) - Pretty charts vs. auto-remediation
- [AgentPulse vs Better Stack](vs-better-stack) - Monitoring vs. monitoring plus auto-fix
- [AgentPulse vs Datadog](vs-datadog) - Auto-remediation without bill shock
- [AgentPulse vs Uptime Kuma](vs-uptime-kuma) - When free monitoring is not enough
- [AgentPulse vs New Relic](vs-new-relic) - Deep observability vs. built-in remediation

## Ready to stop being the remediation layer?

[Join the paid beta](signup) and we will help you protect the first server.

---

<sub>[Privacy Policy](privacy) · [Terms of Service](terms) · support@agentpulse.ca</sub>
