---
layout: default
title: AgentPulse - Server monitoring that can safely fix repeat incidents
description: "AgentPulse is a local-first Linux and macOS agent that detects repeat server incidents, applies only policy-approved fixes, verifies the result, and escalates when a fix does not hold."
---

# Stop waking up to run the same server fix again

AgentPulse watches Linux and macOS hosts for repeat incidents such as disk pressure and crashed services. When you allow it, the agent can apply a narrow first fix locally, verify the result, and escalate instead of retrying blindly.

> **Controlled beta. Alert-only by default.** The first install does not change your host automatically. You decide which checks remain alerts, which require approval, and which safe actions may run on their own.

[Request a controlled pilot](signup#reserve) | [See how it works](features) | [Review the beta release](install)

*Built for founders and small teams running 1–10 hosts on Hetzner, DigitalOcean, Linode, Vultr, AWS Lightsail, small EC2 fleets, or Mac minis.*

## Monitoring tells you something broke. AgentPulse handles the known first move.

A full observability stack can show you every spike, trace, and log line. It still leaves you SSHing into a server at 3 AM to restart the same service or clear the same safe cleanup path.

AgentPulse focuses on a smaller job: detect repeat host incidents and handle only the responses you have approved in advance.

| Incident | What AgentPulse can do | Safety boundary |
| --- | --- | --- |
| Disk pressure | Remove old files from cleanup paths you configured, then re-check disk usage | Refuses system paths, directories, and symlink escapes |
| Crashed service | Restart an allowlisted systemd or launchd service, then verify it is active | Cannot restart a service outside your allowlist |
| Runaway process | Identify the largest memory offender and report it | Never kills processes automatically in v1 |
| Fix did not hold | Record the failed verification and escalate | Does not enter a destructive retry loop |

## Every action has to earn permission

AgentPulse uses the same decision loop whether a fix is automatic or approved by a person:

1. **Observe** the current host condition.
2. **Reason** about a specific, testable outcome.
3. **Simulate** the proposed change.
4. **Gate** it against local policy and hard safety rules.
5. **Act** locally only if every check passes.
6. **Verify** the original condition again.
7. **Record or escalate** the result.

Cloud policy can make the agent more restrictive. It cannot widen the authority configured on the host. If the cloud service is unavailable, local monitoring continues and evidence waits for a later retry.

[Read the full feature and safety breakdown](features)

## Choose how much autonomy each check gets

- **Off:** do not run the check.
- **Alert:** detect and notify, but do not change anything. This is the default.
- **Ask:** prepare the fix and wait for explicit approval.
- **Auto:** run an already allowlisted fix and verify it afterward.

You can promote one low-risk action without giving every check the same authority. Clearing old files from a dedicated cache path and restarting a database do not deserve the same policy.

## What exists today

The current beta includes:

- a dependency-light Python agent for Linux and macOS;
- disk, memory/process, systemd, and launchd checks;
- policy-gated disk cleanup and service restart actions;
- dry-run simulation and post-action verification;
- local audit evidence, redaction, and bounded cloud retry;
- a published prerelease wheel, source archive, and SHA-256 checksums.

The agent behavior is covered by 193 tests, including safety and fuzz cases. Linux clean-host lifecycle acceptance found defects in the published prerelease; the repaired source passes with a local candidate fixture. Public self-serve installation remains closed until the exact replacement prerelease passes the same acceptance run.

## What is not available yet

AgentPulse is not presenting unfinished fleet capacity as a finished product.

- Public self-serve installation is closed until the repaired immutable prerelease passes exact-artifact acceptance.
- The secure customer account and fleet console are not publicly deployed.
- Pro and Business are founding reservations, not live checkout products.
- Native email, Telegram, and Slack delivery are planned; generic webhooks work today.
- AgentPulse has no browser-to-host command channel, arbitrary remote shell, or automatic process killing.

[Check the current installation boundary](install)

## Founding beta plans

| Plan | Founding price | Current path |
| --- | --- | --- |
| Starter | C$29/month CAD | Request a controlled one-server pilot |
| Pro | C$99/month CAD | Reserve pricing for up to 5 servers when fleet access ships |
| Business | C$299/month CAD | Reserve a small-fleet plan; final host limit is confirmed before billing |

Reservations do not charge you. Founding pricing locks when the corresponding service is ready and you choose to activate it.

[Compare plans](pricing) | [Reserve founding access](signup#reserve)

## Good fit

AgentPulse fits best when you:

- run a small number of Linux or macOS hosts;
- already receive alerts but still perform the same manual fixes;
- can name the exact paths and services that are safe to manage;
- want local control and a clear record of every attempted action;
- are willing to start on one non-critical host in alert-only mode.

It is not an APM, log warehouse, uptime checker, on-call scheduler, or general remote administration tool. Pair it with those systems when you need them.

## Spend less time being the remediation layer

Tell us how many hosts you run, what stack they use, and which incident keeps repeating. We will confirm whether the current beta is a fit before anything is installed or billed.

[Request a controlled pilot or reserve founding pricing](signup#reserve)

---

<sub>[Features](features) · [Pricing](pricing) · [Installation status](install) · [Privacy](privacy) · [Terms](terms) · support@agentpulse.ca</sub>
