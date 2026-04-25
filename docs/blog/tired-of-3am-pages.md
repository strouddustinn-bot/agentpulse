---
layout: default
title: "I Built AgentPulse Because I Was Tired of 3AM Pages"
description: "The origin story of AgentPulse — why one developer built auto-remediation for the rest of us, and how it went from a personal tool to a product."
---

# I Built AgentPulse Because I Was Tired of 3AM Pages

Last month my VPS ran out of disk space at 2:47 AM. Same log rotation failure. Same /var/log filling up. Same fix I've done a dozen times before.

That's when I decided: if the fix is always the same, why am I the one doing it?

## The Breaking Point

I had monitoring. Good monitoring. Uptime checks, process monitoring, disk alerts — the whole stack. I knew within seconds when something was wrong. The problem wasn't detection. The problem was that I was the remediation layer.

3AM pages for disk space. 4AM pages for a crashed nginx. 6AM pages for an OOM process. Each time, I'd SSH in, run the same three commands, and go back to bed.

After the twelfth time, I started asking: why isn't this automated?

## The Market Gap

I looked at auto-remediation tools. They exist:

- **Resolve.ai** — Used by Coinbase and DataStax. Pricing? "Contact sales."
- **Dynatrace** — $70+/host/month with complex licensing.
- **PagerDuty Runbooks** — Two products, two price tags, enterprise-oriented.

What about the solo dev running 3 VPS boxes? The indie SaaS founder with 5 servers? The small team that can't justify $500/month in monitoring?

They're stuck between:
- **Free tools** (Uptime Kuma, Netdata) — great alerts, no auto-fix
- **Enterprise tools** (Datadog, Dynatrace) — auto-fix exists, but the bill makes you cry

**There was nothing in the middle.** So I built it.

## Building AgentPulse

The first version was simple: a Python agent that monitored my servers and ran shell commands when things went wrong. It worked, but it was messy. No baseline learning, no approval gates, no dashboard.

So I rebuilt it properly:

- **Baseline learning** — the agent learns what "normal" looks like for each server over time
- **Approval gates** — auto-fix, ask-first, or alert-only per action type
- **Real-time dashboard** — see what's happening across all your servers
- **Telegram alerts** — get notified instantly, but only when you actually need to act
- **Security hardening** — brute-force detection, suspicious process flagging

## The Install Experience I Wanted

I hate tools that take an afternoon to configure. AgentPulse installs with one command:

```bash
curl -fsSL https://agentpulse.dustinnstroud.com/install.sh | bash
```

Zero config to start monitoring. The agent discovers your services, starts collecting metrics, and begins learning your baseline within minutes.

## The Pricing I Wanted

No "contact sales." No per-GB billing that balloons unpredictably. No 14-page pricing calculator.

- **Starter** — $29/mo (1 server, real-time alerts, dashboard)
- **Pro** — $99/mo (5 servers, auto-remediation, baseline learning)
- **Business** — $299/mo (unlimited servers, API, dedicated support)

## The Result

I haven't been paged for a fixable issue in weeks. AgentPulse handles disk cleanup, service restarts, and process management automatically. I still get alerts for things that actually need my attention — but those are rare.

If you're running Linux servers and tired of being the remediation layer, give it a try:

```bash
curl -fsSL https://agentpulse.dustinnstroud.com/install.sh | bash
```

[Try AgentPulse →](https://agentpulse.dustinnstroud.com)
