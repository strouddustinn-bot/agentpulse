---
layout: default
title: "AgentPulse features - Policy-gated server remediation"
description: "See how AgentPulse detects disk pressure, crashed services, and runaway processes; simulates approved fixes; verifies outcomes; and keeps local policy in control."
---

# AgentPulse features

AgentPulse is a small Linux and macOS agent for a deliberately narrow job: detect repeat host incidents and handle only the first fixes you have approved.

The current beta starts in alert-only mode. Nothing moves into ask-first or automatic remediation until you change the policy for that specific check.

[Request beta access](signup#reserve) | [See pricing](pricing) | [Review installation status](install)

## Incident checks and responses

### Disk pressure

AgentPulse measures disk usage on configured paths. When a threshold is breached, it can identify old files inside cleanup paths you explicitly allow.

A cleanup action must pass hard checks before it runs:

- the target must remain inside an allowed cleanup root;
- system paths are refused;
- directories are not deleted;
- symlink escapes are refused;
- the agent simulates the candidate deletion first;
- disk usage is measured again after the action.

If usage remains above the threshold, AgentPulse records the failed verification and escalates. It does not keep deleting files in a loop.

### Crashed services

AgentPulse checks configured systemd services on Linux and launchd services on macOS. It can restart a failed service only when that service is on the host's local allowlist.

After the restart, it asks the service manager for the new state. A command returning successfully is not enough; the service must actually become active. Otherwise the incident is escalated.

### Runaway processes

The memory check identifies the largest process when host memory crosses your threshold. It reports the process and the evidence that triggered the alert.

AgentPulse never kills a process automatically in v1. Even if the process check is set to auto, the policy clamps the response to ask-first. Process termination stays a human decision.

### Statistical baseline alerts

Static thresholds catch obvious breaches but miss unusual movement below the line. AgentPulse maintains a running mean and variance for supported host metrics and can flag samples that deviate sharply from the learned baseline.

Baseline alerts are advisory. They never trigger remediation. The method is deterministic, dependency-free, and inspectable; it is not marketed as machine learning.

## The decision loop

Every proposed host change follows the same path.

| Stage | What happens |
| --- | --- |
| Observe | Measure the host and identify a policy breach |
| Reason | State the expected result before changing anything |
| Simulate | Produce the candidate change without applying it |
| Gate | Check the action against policy, allowlists, and safety predicates |
| Act | Apply the validated local action |
| Verify | Measure the original condition again |
| Record or escalate | Keep the evidence or notify a person when the fix did not hold |

Unknown and malformed action types fail closed. Human approval grants consent for a known action; it does not bypass the safety gate.

## Four policy modes

Each check has its own mode.

| Mode | Behavior |
| --- | --- |
| Off | The check does not run |
| Alert | Detect and notify without changing the host |
| Ask | Queue the proposed fix for explicit approval |
| Auto | Run an allowlisted fix immediately, then verify it |

Alert is the default on a fresh setup. A practical rollout keeps everything in alert mode, promotes one predictable action to ask, reviews the evidence, and uses auto only after that policy has earned trust.

## Local control survives cloud failure

The host remains authoritative.

- Local policy sets the maximum authority.
- Cloud policy may narrow that authority but cannot increase it.
- Monitoring and approved local behavior continue during a control-plane outage.
- Outbound evidence is bounded, stored locally, and retried later.
- There is no inbound remote shell or arbitrary command endpoint.

This design keeps a billing, network, or hosted-service outage from turning off safe local monitoring.

## Alerts and evidence

AgentPulse can send JSON to a generic webhook, which works with systems that accept incoming HTTP requests. Alerts also remain available through stdout or journald.

An incident record can include:

- the observed metric and threshold;
- the affected path, service, or process;
- the selected policy mode;
- the simulated action and gate result;
- execution output with sensitive fields redacted;
- the verification result;
- whether AgentPulse resolved or escalated the incident.

Native Telegram, email, and Slack channels are planned. They are not part of the current beta release.

## Supported operating boundary

| Area | Current beta |
| --- | --- |
| Host operating systems | Linux and macOS agent code and service assets |
| Python | 3.10 through 3.13 packaging and CI targets |
| Disk remediation | Old-file cleanup inside explicit safe paths |
| Service remediation | Allowlisted systemd and launchd restart |
| Process response | Detection and human decision only |
| Cloud connection | Outbound heartbeat, policy narrowing, and incident evidence |
| Browser-to-host control | None |
| Public self-serve install | Not open; replacement-release acceptance is pending |

The published `v0.2.0-beta.1` prerelease includes a wheel, source archive, release notes, and SHA-256 checksums. Linux clean-host lifecycle acceptance exposed defects in that release. The repaired source passes install, secure configuration, outage recovery, restart, upgrade, rollback, uninstall, and reinstall with a local candidate fixture; public installation remains closed until the exact replacement prerelease passes the same run.

## What AgentPulse does not replace

AgentPulse does not provide distributed tracing, application profiling, log search, external uptime checks, public status pages, or on-call scheduling.

Use an APM for request traces. Use a log platform for log search. Use an external uptime checker to see your service from another network. AgentPulse sits beside those tools and handles a bounded set of local host incidents they normally leave for a person.

## Planned, not shipped

- secure public account sessions and fleet console deployment;
- self-serve checkout, account claim, enrollment, and billing portal;
- native notification channels;
- time-of-day and weekday-aware baselines;
- additional remediation classes after their safety policies are proven.

Roadmap items do not count as current plan benefits and are not charged as delivered capacity.

## Start with one host and no automatic changes

A controlled pilot begins on one approved non-critical host in alert-only mode. You review what the agent detects before granting any remediation authority.

[Request a controlled pilot](signup#reserve)

---

<sub>[Home](./) · [Pricing](pricing) · [Installation status](install) · [Privacy](privacy) · [Terms](terms) · support@agentpulse.ca</sub>
