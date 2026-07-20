---
layout: default
title: AgentPulse founding beta pricing
description: "AgentPulse founding beta plans start at C$29 per month. Request a controlled one-server pilot or reserve multi-host founding pricing without being charged today."
---

# Founding beta pricing

AgentPulse is not charging for multi-host capacity before the fleet account, enrollment, and billing path works end to end.

You can request a controlled one-server pilot or reserve founding pricing for a future multi-host plan. A reservation does not charge you.

> **Current boundary:** The local agent and a checksummed prerelease exist. Public self-serve installation and the secure fleet console are still release gates. Every pilot begins on one approved non-critical host in alert-only mode.

## Plans

| Plan | Founding price | Host scope | Available now |
| --- | ---: | --- | --- |
| Starter | C$29/month CAD | 1 host | Request a controlled manual pilot |
| Pro | C$99/month CAD | Up to 5 hosts when fleet access ships | Reserve founding pricing; no charge today |
| Business | C$299/month CAD | Small fleet; finite host limit confirmed before billing | Reserve and discuss fit; no charge today |

Founding pricing locks when the corresponding service is ready and you choose to activate it. We will confirm the plan, host limit, and start date before billing.

<div style="display:flex;flex-wrap:wrap;gap:16px;margin:24px 0;">

  <div style="flex:1;min-width:200px;border:1px solid #ddd;border-radius:10px;padding:18px;">
    <div style="font-weight:700;font-size:1.1em;">Starter</div>
    <div style="font-size:1.6em;font-weight:700;margin:4px 0;">C$29<span style="font-size:0.5em;color:#666;">/month CAD</span></div>
    <div style="color:#666;font-size:0.9em;margin-bottom:12px;">One-host controlled pilot. Alert-only first, with approval-gated fixes available after review.</div>
    <a href="signup#reserve"
       style="display:block;text-align:center;padding:11px;background:#0b5fff;color:#fff;border-radius:7px;text-decoration:none;font-weight:600;">Request a Starter pilot</a>
  </div>

  <div style="flex:1;min-width:200px;border:2px solid #0b5fff;border-radius:10px;padding:18px;position:relative;">
    <div style="position:absolute;top:-11px;left:18px;background:#0b5fff;color:#fff;font-size:0.72em;font-weight:700;padding:2px 8px;border-radius:5px;">FOUNDING</div>
    <div style="font-weight:700;font-size:1.1em;">Pro</div>
    <div style="font-size:1.6em;font-weight:700;margin:4px 0;">C$99<span style="font-size:0.5em;color:#666;">/month CAD</span></div>
    <div style="color:#666;font-size:0.9em;margin-bottom:12px;">Up to five hosts when fleet access ships. Reserve the rate without a charge today.</div>
    <a href="signup#reserve"
       style="display:block;text-align:center;padding:11px;background:#0b5fff;color:#fff;border-radius:7px;text-decoration:none;font-weight:700;">Reserve Pro founding pricing</a>
  </div>

  <div style="flex:1;min-width:200px;border:1px solid #ddd;border-radius:10px;padding:18px;">
    <div style="font-weight:700;font-size:1.1em;">Business</div>
    <div style="font-size:1.6em;font-weight:700;margin:4px 0;">C$299<span style="font-size:0.5em;color:#666;">/month CAD</span></div>
    <div style="color:#666;font-size:0.9em;margin-bottom:12px;">A small fleet, custom policy review, and priority setup after the host limit is agreed.</div>
    <a href="signup#reserve"
       style="display:block;text-align:center;padding:11px;background:#1a1a1a;color:#fff;border-radius:7px;text-decoration:none;font-weight:600;">Reserve Business founding pricing</a>
  </div>

</div>

## What every activated beta plan includes

- alert-only startup;
- per-check off, alert, ask, and auto modes;
- disk pressure and crashed-service detection;
- allowlisted disk cleanup and service restart actions;
- simulation before a host change;
- post-action verification and escalation;
- local audit evidence and generic webhook alerts;
- onboarding help during the controlled beta.

Automatic process killing is not included. AgentPulse identifies a runaway process and leaves the termination decision to a person.

## Why checkout is closed

A payment button is easy. A dependable paid lifecycle is not.

Before public checkout opens, a customer must be able to pay, claim one secure account, receive versioned install instructions, enroll the allowed number of hosts, manage billing, and recover cleanly from failures without a manual database edit.

That path is still being built and tested. Public Pro and Business checkout stays disabled until the capacity behind those plans is real.

## How a Starter pilot works

1. You send the host count, provider, stack, and repeat incident you want to reduce.
2. We confirm that the current checks match the problem.
3. After the clean-host release gate passes, the prerelease is installed on one approved non-critical host.
4. The agent runs in alert-only mode while you review its findings.
5. You may promote a specific low-risk action to ask-first or auto after reviewing the policy and simulation.

No passwords, SSH keys, API tokens, or server addresses belong in the reserve email.

## Founding price lock

When the matching plan becomes available, founding customers can activate at the listed monthly rate. The rate stays locked while the subscription remains active and within the agreed host scope.

The reservation itself is free. We confirm activation and billing before any charge.

## Guarantee after billing starts

If AgentPulse does not catch or reduce at least one repeat operational incident during the first 30 days of paid service, cancel and pay nothing for the following month.

This beta guarantee is an operating promise, not a claim that every outage can be prevented. AgentPulse only acts on supported incident classes and policies you approve.

## Cancellation

Until the self-serve billing portal is released, paid beta customers cancel by emailing [support@agentpulse.ca](mailto:support@agentpulse.ca). We confirm the effective date and any remaining access in writing.

## What counts as a host?

One Linux machine, VPS, or supported Mac running the AgentPulse agent counts as one host. Containers on the same machine do not count separately during the beta.

## Good fit

The current beta is strongest for founders and small teams who run a handful of hosts, already receive alerts, and can name one repeat incident they still fix manually.

If you need application tracing, log aggregation, outside-in uptime checks, Kubernetes fleet management, enterprise SSO, or arbitrary remote commands, AgentPulse is not the right primary tool.

## Reserve or request a pilot

The reserve email asks only for non-sensitive fit information. We will reply before any installation or billing step.

[Reserve founding pricing or request Starter access](signup#reserve)

Prefer email? Write [support@agentpulse.ca](mailto:support@agentpulse.ca?subject=AgentPulse%20founding%20beta).

---

<sub>[Home](./) · [Features](features) · [Installation status](install) · [Privacy](privacy) · [Terms](terms) · support@agentpulse.ca</sub>
