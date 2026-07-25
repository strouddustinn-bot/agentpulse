---
layout: default
title: AgentPulse Privacy Policy
---

# Privacy Policy

**Last updated: July 25, 2026**

This Privacy Policy explains how AgentPulse ("AgentPulse", "we", "us") handles
information in connection with the AgentPulse website
(agentpulse.ca) and the AgentPulse agent software (the
"Service"). AgentPulse is operated from Ontario, Canada.

> This is a starting template provided in good faith, not legal advice. Please
> review it (or have a lawyer review it) before relying on it for your business.

## Who we are

AgentPulse is a beta Linux/macOS monitoring and remediation product operated by
Dustinn Stroud. Contact: **support@agentpulse.ca**.

## Information we collect

**Account and billing information.** Public checkout and paid activation are
currently closed, so a reservation or pilot-consideration request does not send
payment data to AgentPulse or authorize a charge. If an invited paid beta is
activated after staging, payment will be processed by **Stripe**. We will not see
or store the full card number; Stripe may provide limited subscription details
such as name, email, billing country, status, and card brand/last four digits.
Stripe's handling is governed by [Stripe's Privacy Policy](https://stripe.com/privacy).

**Information you send us.** If you email us or submit a beta request, we keep
the details you provide (name, company, server environment, and the issues you
describe) to evaluate fit, respond to you, and support any later invited onboarding.

**Website usage.** The website is hosted on GitHub Pages. Standard server logs
(such as IP address and browser type) may be processed by GitHub as part of
serving the site, per [GitHub's Privacy Statement](https://docs.github.com/site-policy/privacy-policies/github-privacy-statement).

## Data handled by the agent software

The AgentPulse agent runs **on your own server** and processes operational data
locally — disk usage, service status, process and memory metrics, and its own
action logs. Public cloud onboarding is not currently available. If an invited
host is activated after staging, the hosted path is designed so that:

- The agent sends bounded heartbeat summaries, incident evidence, agent identity,
  hostname, software version, and policy state needed to operate the fleet
  console. It does not send arbitrary files or provide a remote shell.
- Detailed remediation authority and raw host state remain local. Cloud policy
  may narrow, but cannot increase, the agent's configured local authority.
- Notification text is sent to an external webhook only when you configure that
  endpoint.
- Heartbeat and incident records are retained to provide fleet history and
  support; request deletion by emailing support@agentpulse.ca.

## How we use information

- To operate the website and accepted local agent artifact.
- To evaluate and respond to pilot-consideration and reservation requests.
- If an invited paid beta is later activated, to support onboarding and process
  subscription billing through Stripe.
- To comply with legal obligations.

We do **not** sell your personal information.

## Data retention

If a paid account is activated, we keep account and billing records while it is
active and as required afterward for legal, tax, and accounting purposes. We
keep request information only as needed to respond and administer future pilot
consideration. You may
request deletion of information we hold about you (subject to records we must
retain by law) by emailing us.

## Your rights

Depending on where you live, you may have rights to access, correct, delete, or
port your personal information, or to object to certain processing. To exercise
these, email **support@agentpulse.ca**.

## Security

We use reasonable measures to protect information in our care. If paid
activation opens, Stripe will handle payment-card processing. No method of
transmission or storage is completely secure.

## Children

The Service is not directed to children under 16, and we do not knowingly
collect their information.

## Changes

We may update this policy. Material changes will be reflected by the "Last
updated" date above.

## Contact

Questions about this policy: **support@agentpulse.ca**.
