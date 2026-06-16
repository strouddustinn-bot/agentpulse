---
layout: default
title: "AgentPulse Pricing — Simple, Honest Server Monitoring"
description: "Three straightforward plans for solo devs, indie SaaS founders, and small DevOps teams. No per-GB billing, no sales calls, no surprises. Starts at $29/mo."
---

# Pricing

Three plans. Fixed monthly prices. No surprises.

Pick the tier that matches your server count. Upgrade or cancel any time — no contracts, no exit fees, no "talk to sales."

---

## Plans

| | **Starter** | **Pro** | **Business** |
|---|---|---|---|
| **Price** | $29/mo | $99/mo | $299/mo |
| **Servers** | 1 | 5 | Unlimited |
| **Best for** | Personal projects, single VPS | Small SaaS, indie teams | Agencies, growing infra |

[Get Starter →](https://agentpulse.dustinnstroud.com/signup?plan=starter){: .btn} &nbsp; [Get Pro →](https://agentpulse.dustinnstroud.com/signup?plan=pro){: .btn} &nbsp; [Get Business →](https://agentpulse.dustinnstroud.com/signup?plan=business){: .btn}

---

## What's Included

### Starter — $29/mo · 1 server

Everything you need to stop flying blind on a single box:

- Real-time CPU, memory, disk, and network monitoring
- Alerts via Telegram and email
- Web dashboard with live metrics
- 30-day metric history
- Automated incident log

No auto-remediation on Starter. You get the alert; you decide what to do. If you want the agent to fix things for you, that's Pro.

---

### Pro — $99/mo · 5 servers

The same monitoring, plus the part that makes 3am pages optional:

- Everything in Starter, for up to 5 servers
- **Auto-remediation** — kills runaway processes, restarts crashed services, frees disk space, blocks brute-force SSH attacks
- **Baseline learning** — the agent learns what "normal" looks like for each server and stops paging you for routine spikes
- Webhook integrations (Slack, PagerDuty, Discord, custom endpoints)
- 90-day metric history
- Remediation audit log — see exactly what the agent did and why

$99/mo for 5 servers with auto-remediation included. Comparable Datadog or New Relic setups run $300–500+/month, before log overages.

---

### Business — $299/mo · Unlimited servers

For teams that manage a lot of servers and need programmatic access:

- Everything in Pro, for unlimited servers
- **Full REST API** — query metrics, trigger remediations, pull incident history from your own dashboards or scripts
- **Priority remediation** — your servers jump the queue during high-load processing windows
- **Dedicated support** — direct access, not a support ticket queue
- 1-year metric history
- Team member accounts (up to 10 seats)
- Custom webhook templates

---

## Feature Comparison

| Feature | Starter | Pro | Business |
|---------|:-------:|:---:|:--------:|
| Servers | 1 | 5 | Unlimited |
| CPU / memory / disk / network monitoring | ✅ | ✅ | ✅ |
| Telegram alerts | ✅ | ✅ | ✅ |
| Email alerts | ✅ | ✅ | ✅ |
| Web dashboard | ✅ | ✅ | ✅ |
| Metric history | 30 days | 90 days | 1 year |
| Auto-remediation | ❌ | ✅ | ✅ |
| Kill runaway processes | ❌ | ✅ | ✅ |
| Restart crashed services | ❌ | ✅ | ✅ |
| Free disk space automatically | ❌ | ✅ | ✅ |
| Block brute-force attacks | ❌ | ✅ | ✅ |
| Baseline learning | ❌ | ✅ | ✅ |
| Webhook integrations | ❌ | ✅ | ✅ |
| Remediation audit log | ❌ | ✅ | ✅ |
| REST API access | ❌ | ❌ | ✅ |
| Priority remediation | ❌ | ❌ | ✅ |
| Dedicated support | ❌ | ❌ | ✅ |
| Team seats | 1 | 1 | 10 |

---

## FAQ

**Can I try AgentPulse before paying?**

Yes. There's a 14-day free trial on every plan — full features, no credit card required to start. If you decide it's not for you, just cancel. Nothing gets charged.

**Do you offer annual billing?**

Yes. Pay annually and get two months free (effectively a 17% discount). Annual billing is available on all plans at checkout.

**What counts as a "server"?**

Any Linux host running the AgentPulse agent: bare metal, a VPS, a cloud instance (EC2, DigitalOcean Droplet, Linode, Hetzner, etc.), a container host, or a Raspberry Pi. Docker containers inside a host don't count as separate servers.

**Can I monitor more servers than my plan allows?**

You can add extra servers at $15/server/month on Starter and Pro. On Business, unlimited servers are already included. If you're regularly running more than 5 servers on Pro, Business is the better deal.

**What happens if I hit my server limit?**

The agent keeps running on your existing servers. New agents you install beyond your limit will register but won't send data until you upgrade or add capacity.

**Can I downgrade my plan?**

Yes. Downgrades take effect at the next billing cycle. If you're on Pro and downgrade to Starter with 3 servers registered, you'll need to deregister 2 servers first — we'll walk you through it.

**How does auto-remediation work? Can it break things?**

Auto-remediation actions are conservative by default: it only kills processes consuming an abnormally high share of CPU or memory for a sustained period, restarts services that are in a crashed/failed systemd state, removes log rotation leftovers and temp files to free disk space, and adds iptables rules to block IPs with repeated failed SSH logins.

None of these actions delete application data or modify your application code. Every action is logged with a timestamp, trigger condition, and what was done. You can whitelist processes and services that should never be touched.

**What Linux distros are supported?**

Ubuntu 20.04+, Debian 10+, CentOS/RHEL 8+, Fedora 36+, and Amazon Linux 2. The agent is a single binary — install takes about 60 seconds.

**Is my server data stored on your servers?**

Metric data (CPU, memory, disk I/O, network) is stored on AgentPulse infrastructure for the history period of your plan. We don't store file contents, environment variables, or application data. See the [privacy policy](https://agentpulse.dustinnstroud.com/privacy) for full details.

**What payment methods do you accept?**

Credit and debit cards (Visa, Mastercard, Amex) via Stripe. ACH bank transfer is available on Business annual plans — email us.

**Do you offer refunds?**

If AgentPulse doesn't work for you in the first 30 days, email us and we'll refund the charge. No interrogation required.

---

## Why Not Free?

Fair question. There are solid free tools out there — Netdata, Prometheus + Grafana, Uptime Kuma, Zabbix. We have genuine respect for them.

Here's the honest answer: **self-hosted monitoring tools are free to install and expensive to operate.**

To run a proper Prometheus + Grafana + Alertmanager stack on 5 servers, you need:

- A separate monitoring server (another VPS, ~$10–20/mo)
- Hours of initial setup and configuration
- Ongoing maintenance: upgrades, disk management for time-series data, alert rule tuning
- Alert routing setup (Alertmanager is powerful and genuinely painful to configure)
- Zero auto-remediation (you write your own runbooks and hope you're awake)

By the time you've done all that, you've spent 20+ hours you could have billed at your hourly rate. You've also built something you have to maintain forever.

AgentPulse exists for developers who would rather ship their product than operate monitoring infrastructure. The agent installs in 60 seconds. You're getting alerts in 2 minutes. Auto-remediation is on by default.

**Free tools give you charts. AgentPulse fixes problems.**

If you want to self-host, those tools are great and we're not going to talk you out of it. But if your time is worth something and you want a server that can mostly take care of itself, $29/month is a reasonable trade.

---

## Not Sure Which Plan?

**Start with Starter** if you have one server and want to see whether AgentPulse actually works before committing to auto-remediation. You can upgrade any time.

**Start with Pro** if you have multiple servers or if you want the auto-remediation to actually do the work. Most solo founders and small teams land here.

**Start with Business** if you're running more than 5 servers, want API access for custom tooling, or need a real human to respond quickly when something goes wrong.

---

[Start your 14-day free trial →](https://agentpulse.dustinnstroud.com/signup)

No credit card required. Installs in 60 seconds.
