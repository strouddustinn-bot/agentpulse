---
layout: default
title: Server recovery pricing
description: "Monthly pricing for bounded recovery of supported repeat server incidents: C$29 Starter, C$99 Pro, and C$299 Business."
---

# Pricing

Simple monthly pricing by host scope. Choose the smallest plan that fits the infrastructure you operate.

| Plan | Price | Host scope |
| --- | ---: | --- |
| Starter | C$29/month CAD | 1 host |
| Pro | C$99/month CAD | Up to 5 hosts |
| Business | C$299/month CAD | Up to 20 hosts, priority support, guided onboarding |

<div style="display:flex;flex-wrap:wrap;gap:16px;margin:24px 0;">
  <div style="flex:1;min-width:200px;border:1px solid #333;border-radius:10px;padding:18px;">
    <div style="font-weight:700;font-size:1.1em;">Starter</div>
    <div style="font-size:1.6em;font-weight:700;margin:4px 0;">C$29<span style="font-size:0.5em;color:#888;">/month CAD</span></div>
    <div style="color:#999;font-size:0.9em;margin-bottom:12px;">One host.</div>
    <a href="https://agentpulse.ca/signup" style="display:block;text-align:center;padding:11px;background:#0b5fff;color:#fff;border-radius:7px;text-decoration:none;font-weight:600;">Request Starter pilot</a>
  </div>
  <div style="flex:1;min-width:200px;border:2px solid #0b5fff;border-radius:10px;padding:18px;">
    <div style="font-weight:700;font-size:1.1em;">Pro</div>
    <div style="font-size:1.6em;font-weight:700;margin:4px 0;">C$99<span style="font-size:0.5em;color:#888;">/month CAD</span></div>
    <div style="color:#999;font-size:0.9em;margin-bottom:12px;">Up to five hosts.</div>
    <a href="https://agentpulse.ca/signup" style="display:block;text-align:center;padding:11px;background:#0b5fff;color:#fff;border-radius:7px;text-decoration:none;font-weight:700;">Reserve Pro interest</a>
  </div>
  <div style="flex:1;min-width:200px;border:1px solid #333;border-radius:10px;padding:18px;">
    <div style="font-weight:700;font-size:1.1em;">Business</div>
    <div style="font-size:1.6em;font-weight:700;margin:4px 0;">C$299<span style="font-size:0.5em;color:#888;">/month CAD</span></div>
    <div style="color:#999;font-size:0.9em;margin-bottom:12px;">Up to 20 hosts, priority support, guided onboarding.</div>
    <a href="https://agentpulse.ca/signup" style="display:block;text-align:center;padding:11px;background:#1a1a1a;color:#fff;border-radius:7px;text-decoration:none;font-weight:600;">Reserve Business interest</a>
  </div>
</div>

> Pilot requests are currently handled under the product name **AgentPulse**. No charge is made at request time.

## What the product is for

The product is built for recurring host incidents where the first response can be defined in advance and constrained by local policy. Supported behavior includes disk-pressure detection and bounded cleanup, allowlisted service restart and verification, runaway-process detection/reporting, evidence recording, and escalation when verification fails.

It is not a remote shell, an unrestricted command runner, an APM replacement, or a promise to automatically repair arbitrary outages.

## Safety boundary

- host authority remains local;
- cloud policy may reduce permissions but cannot increase the local authority ceiling;
- unknown actions fail closed;
- permitted recovery is simulated, policy-gated, verified, and recorded;
- failed verification escalates instead of entering an uncontrolled retry loop;
- automatic process killing is not part of the current release.

## Questions

If you need to confirm whether a repeat incident fits the current supported boundary before paying, email [support@agentpulse.ca](mailto:support@agentpulse.ca?subject=Server%20recovery%20fit%20question). Do not send credentials, IP addresses, server addresses, tokens, or customer data.
