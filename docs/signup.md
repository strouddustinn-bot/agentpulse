---
layout: default
title: Request AgentPulse pilot consideration
description: "Request consideration for a controlled one-host AgentPulse pilot or reserve Pro and Business pricing. Requests are free and do not expose server credentials."
---

# Request AgentPulse pilot consideration

AgentPulse is accepting fit requests from founders and small teams who already monitor their servers but still handle the same incidents by hand.

You can request consideration for a controlled Starter pilot on one non-critical host or reserve interest in Pro or Business. Reservations are free. We confirm fit, availability, and billing before anything is installed or charged; sending a request does not mean the pilot is accepted.

<p>
  <a id="reserve"
     class="btn"
     href="mailto:support@agentpulse.ca?subject=AgentPulse%20pilot%20consideration%20request&body=Plan%20interest%3A%20Starter%20pilot%20(C%2429)%20%2F%20Pro%20founding%20(C%2499)%20%2F%20Business%20founding%20(C%24299)%0AHost%20count%3A%20%0AOperating%20system%3A%20%0AHosting%20provider%3A%20%0AStack%20(web%20server%2Fprocess%20manager%2Fdatabase)%3A%20%0ARepeat%20incident%20to%20reduce%3A%20%0APreferred%20start%3A%20reserve%20only%20%2F%20one-host%20pilot%20consideration%0A"
     style="display:inline-block;padding:14px 26px;background:#0b5fff;color:#fff;border-radius:8px;text-decoration:none;font-weight:700;font-size:1.05em;">
     Open the pilot request email
  </a>
</p>

<p style="font-size:0.95em;color:#555;margin-top:-6px;">
  Starter: <strong>C$29/month CAD</strong> for an invited one-host controlled pilot.<br>
  Pro: <strong>C$99/month CAD</strong> for up to five hosts when fleet access ships.<br>
  Business: <strong>C$299/month CAD</strong> for up to 20 hosts, priority support, and guided onboarding when fleet access ships.<br>
  <strong>No charge at reservation.</strong>
</p>

[Review the full plan details](pricing)

## What to include

Reply with enough information to decide whether the controlled pilot matches your problem:

- the plan you are interested in;
- how many hosts you expect to manage;
- Linux distribution or macOS version;
- hosting provider;
- web server, process manager, and database;
- one incident you keep fixing manually;
- whether you want a reservation only or a one-host pilot.

Do not send an IP address, hostname, password, SSH key, API token, recovery code, customer data, or production configuration. Those are not needed to assess fit.

## What happens next

### If you reserve

1. We confirm the requested plan and founding rate.
2. Your reservation records demand but does not activate billing.
3. We contact you when the matching account and fleet capacity is ready.
4. You decide whether to activate after reviewing the service boundary.

### If you request consideration for a Starter pilot

1. We check whether AgentPulse supports the incident you named.
2. We confirm that the proposed host is non-critical and appropriate for beta acceptance.
3. If accepted, we install the exact prerelease artifact approved for that pilot on one approved non-critical host.
4. Installation begins in alert-only mode.
5. You review detected incidents and simulations before granting any remediation authority.

Pilot installation uses the exact approved prerelease artifact and its integrity checks. Do not run an unreviewed installer on a production host; pilots remain controlled and begin on an approved non-critical host.

## Good beta fit

You are likely a fit if:

- you run 1–20 Linux or macOS hosts;
- the same disk, service, or memory incident keeps returning;
- your current monitor pages you but does not handle the first fix;
- you can define the exact cleanup paths or services that may be managed;
- you are comfortable starting with observation only.

## Probably not a fit yet

The planned paid beta will not satisfy teams that need:

- Kubernetes or large enterprise fleet management;
- distributed tracing or application performance monitoring;
- centralized log search;
- external uptime checks and status pages;
- enterprise SSO or role-based access control;
- a browser-based remote shell;
- broad, AI-generated production commands.

AgentPulse intentionally has no arbitrary command channel. Host changes must come from known action types, local allowlists, and explicit policy.

## Current product boundary

Accepted capabilities intended for explicitly approved controlled pilots:

- Linux and macOS agent behavior;
- alert-only startup;
- disk, service, and runaway-process checks;
- policy-gated disk cleanup and service restart;
- simulation, verification, evidence, and escalation;
- a versioned prerelease with checksums.

Public access boundary:

- public self-serve checkout remains closed;
- unrestricted fleet onboarding remains closed;
- pilot installation is controlled and begins on one approved non-critical host;
- broader host scope or billing activation requires the applicable release gate and explicit approval.

## Questions before reserving

Email [support@agentpulse.ca](mailto:support@agentpulse.ca?subject=AgentPulse%20beta%20question). Describe the incident and host type, but leave out credentials and identifying server details.

---

<sub>[Home](./) · [Features](features) · [Pricing](pricing) · [Installation status](install) · [Privacy](privacy) · [Terms](terms) · support@agentpulse.ca</sub>
