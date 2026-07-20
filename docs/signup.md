---
layout: default
title: Request AgentPulse beta access
description: "Request a controlled one-host AgentPulse pilot or reserve Pro and Business founding pricing. Reservations are free and do not expose server credentials."
---

# Request AgentPulse beta access

AgentPulse is onboarding founders and small teams who already monitor their servers but still handle the same incidents by hand.

You can request a controlled Starter pilot for one non-critical host or reserve Pro or Business founding pricing. Reservations are free. We confirm fit, availability, and billing before anything is installed or charged.

<p>
  <a id="reserve"
     class="btn"
     href="mailto:support@agentpulse.ca?subject=AgentPulse%20beta%20access%20request&body=Plan%20interest%3A%20Starter%20pilot%20(C%2429)%20%2F%20Pro%20founding%20(C%2499)%20%2F%20Business%20founding%20(C%24299)%0AHost%20count%3A%20%0AOperating%20system%3A%20%0AHosting%20provider%3A%20%0AStack%20(web%20server%2Fprocess%20manager%2Fdatabase)%3A%20%0ARepeat%20incident%20to%20reduce%3A%20%0APreferred%20start%3A%20reserve%20only%20%2F%20one-host%20pilot%0A"
     style="display:inline-block;padding:14px 26px;background:#0b5fff;color:#fff;border-radius:8px;text-decoration:none;font-weight:700;font-size:1.05em;">
     Open the beta access email
  </a>
</p>

<p style="font-size:0.95em;color:#555;margin-top:-6px;">
  Starter: <strong>C$29/month CAD</strong> for a one-host controlled pilot.<br>
  Pro: <strong>C$99/month CAD</strong> for up to five hosts when fleet access ships.<br>
  Business: <strong>C$299/month CAD</strong> for an agreed small-fleet limit.<br>
  <strong>No charge at reservation.</strong>
</p>

[Review the full plan details](pricing)

## What to include

Reply with enough information to decide whether the current beta matches your problem:

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
4. You decide whether to activate after reviewing the final host limit and service boundary.

### If you request a Starter pilot

1. We check whether AgentPulse supports the incident you named.
2. We confirm that the proposed host is non-critical and appropriate for beta acceptance.
3. The pilot waits until the repaired immutable prerelease passes exact-artifact acceptance.
4. Installation begins in alert-only mode.
5. You review detected incidents and simulations before granting any remediation authority.

The published prerelease is not an invitation to run an unreviewed installer on a production host. Linux lifecycle acceptance exposed defects in that artifact; pilots wait for the repaired replacement release to pass the same exact-artifact run.

## Good beta fit

You are likely a fit if:

- you run 1–10 Linux or macOS hosts;
- the same disk, service, or memory incident keeps returning;
- your current monitor pages you but does not handle the first fix;
- you can define the exact cleanup paths or services that may be managed;
- you are comfortable starting with observation only.

## Probably not a fit yet

The current beta will not satisfy teams that need:

- Kubernetes or large enterprise fleet management;
- distributed tracing or application performance monitoring;
- centralized log search;
- external uptime checks and status pages;
- enterprise SSO or role-based access control;
- a browser-based remote shell;
- broad, AI-generated production commands.

AgentPulse intentionally has no arbitrary command channel. Host changes must come from known action types, local allowlists, and explicit policy.

## Current product boundary

Available in the controlled beta:

- Linux and macOS agent behavior;
- alert-only startup;
- disk, service, and runaway-process checks;
- policy-gated disk cleanup and service restart;
- simulation, verification, evidence, and escalation;
- a versioned prerelease with checksums.

Still behind release gates:

- public self-serve installation;
- secure browser account sessions;
- public fleet and incident console deployment;
- automated checkout, account claim, and billing portal;
- enforced self-serve Pro and Business capacity.

## Questions before reserving

Email [support@agentpulse.ca](mailto:support@agentpulse.ca?subject=AgentPulse%20beta%20question). Describe the incident and host type, but leave out credentials and identifying server details.

---

<sub>[Home](./) · [Features](features) · [Pricing](pricing) · [Installation status](install) · [Privacy](privacy) · [Terms](terms) · support@agentpulse.ca</sub>
