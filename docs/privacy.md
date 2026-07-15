---
layout: default
title: AgentPulse Privacy Policy
---

# Privacy Policy

**Last updated: June 18, 2026**

This Privacy Policy explains how AgentPulse ("AgentPulse", "we", "us") handles
information in connection with the AgentPulse website
(agentpulse.ca) and the AgentPulse agent software (the
"Service"). AgentPulse is operated from Ontario, Canada.

> This is a starting template provided in good faith, not legal advice. Please
> review it (or have a lawyer review it) before relying on it for your business.

## Who we are

AgentPulse is a self-serve Linux/macOS monitoring and remediation agent operated by
Dustinn Stroud. Contact: **support@agentpulse.ca**.

## Information we collect

**Account and billing information.** When you subscribe, payment is processed by
**Stripe**. We do not see or store your full card number. Stripe provides us with
limited information needed to manage your subscription (name, email, billing
country, subscription status, and the last four digits / card brand). Stripe's
handling of your payment data is governed by [Stripe's Privacy Policy](https://stripe.com/privacy).

**Information you send us.** If you email us or submit a beta request, we keep
the details you provide (name, company, server environment, and the issues you
describe) to set up and support your account.

**Website usage.** The website is hosted on GitHub Pages. Standard server logs
(such as IP address and browser type) may be processed by GitHub as part of
serving the site, per [GitHub's Privacy Statement](https://docs.github.com/site-policy/privacy-policies/github-privacy-statement).

## Data handled by the agent software

The AgentPulse agent runs **on your own server** and processes operational data
locally — disk usage, service status, process and memory metrics, and its own
action logs. When you enable the cloud control plane:

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

- To provide, operate, and support the Service.
- To process subscriptions and billing through Stripe.
- To respond to your requests and provide onboarding help.
- To comply with legal obligations.

We do **not** sell your personal information.

## Data retention

We keep account and billing records for as long as your subscription is active
and as required afterward for legal, tax, and accounting purposes. You may
request deletion of information we hold about you (subject to records we must
retain by law) by emailing us.

## Your rights

Depending on where you live, you may have rights to access, correct, delete, or
port your personal information, or to object to certain processing. To exercise
these, email **support@agentpulse.ca**.

## Security

We use reasonable measures to protect information in our care and rely on
Stripe (PCI-compliant) for payment processing. No method of transmission or
storage is completely secure.

## Children

The Service is not directed to children under 16, and we do not knowingly
collect their information.

## Changes

We may update this policy. Material changes will be reflected by the "Last
updated" date above.

## Contact

Questions about this policy: **support@agentpulse.ca**.
