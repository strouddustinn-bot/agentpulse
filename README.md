<div align="center">

# 🛡️ AgentPulse

### AI Server Monitoring That Actually Fixes Things

*Alerts are for humans. Guardians act.*

[![Website](https://img.shields.io/badge/Website-agentpulse.dustinnstroud.com-blue?style=for-the-badge)](https://agentpulse.dustinnstroud.com)
[![Install](https://img.shields.io/badge/Install-curl%20%7C%20bash-green?style=for-the-badge)](https://agentpulse.dustinnstroud.com)
[![Pricing](https://img.shields.io/badge/From-%2429%2Fmo-orange?style=for-the-badge)](https://agentpulse.dustinnstroud.com)

</div>

---

## The Problem

Every monitoring tool on the market will happily wake you up at 3 AM. Almost none of them will fix the problem while you sleep.

You know the pattern:
1. 🔴 Alert fires — "Disk space critical on server-01"
2. 😴 You SSH in, bleary-eyed
3. ⌨️ You run the same three commands you always run
4. 🛏️ You go back to bed
5. 🔁 Two weeks later, same alert, same commands

**You're not the remediation layer. You shouldn't have to be.**

## What AgentPulse Does

AgentPulse is a thin Linux monitoring agent that doesn't just detect problems — **it fixes them**.

### Auto-Remediation
- **Kill runaway processes** — that Java app eating 4GB of RAM? Terminated.
- **Restart crashed services** — nginx down? Back up in seconds.
- **Free disk space** — log rotation failed? Cleaned up based on your rules.
- **Security hardening** — brute-force SSH attempts? Flagged and blocked.

### Baseline Learning
AgentPulse learns your server's normal behavior over time. That cron job that spikes CPU every night at 3 AM? It learns to ignore it. The Gradle daemon that slowly eats all your RAM? It notices.

### Approval Gates
You're not giving a bot unchecked root access. Set policies per action:
- ✅ **Auto-fix** — "Always clean /tmp when disk > 90%"
- ⚠️ **Ask first** — "Restart nginx? Y/N"
- 🚨 **Alert only** — "Database process using too much RAM, don't touch it"

## Quick Start

```bash
curl -fsSL https://agentpulse.dustinnstroud.com/install.sh | bash
```

60 seconds from install to protected. Thin agent, zero config, works on any Linux server.

## How It Compares

| Feature | AgentPulse | Netdata | Better Stack | Uptime Kuma | Datadog |
|---------|-----------|---------|--------------|-------------|---------|
| Real-time monitoring | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Auto-remediation** | **✅** | ❌ | ❌ | ❌ | ⚠️ $$$ |
| Baseline learning | ✅ | ✅ (paid) | ❌ | ❌ | ✅ (paid) |
| Security hardening | ✅ | ❌ | ❌ | ❌ | ✅ (paid) |
| Simple pricing | ✅ | Per-node | Add-ons | Free* | Per-host+per-GB |
| Install time | 60s | 60s | External | Self-host | Hours |
| Sales call required | ❌ | ❌ | ❌ | ❌ | Yes |

*\*Uptime Kuma is free but requires self-hosting and a second server to monitor the first.*

## Pricing

No "contact sales." No per-GB billing that balloons unpredictably. No 14-page pricing calculator.

| Plan | Price | Servers | Key Features |
|------|-------|---------|-------------|
| **Starter** | $29/mo | 1 | Real-time alerts, Telegram/email, dashboard |
| **Pro** | $99/mo | 5 | Auto-remediation, baseline learning, webhooks |
| **Business** | $299/mo | Unlimited | API access, priority remediation, dedicated support |

## Who It's For

- **Solo developers** running VPS boxes who can't justify Datadog pricing
- **Indie SaaS founders** who want to sleep through the night
- **Small DevOps teams** tired of being paged for problems with obvious fixes
- **Self-hosters** who've outgrown Uptime Kuma and Netdata's "just alerting" approach

## Who It's NOT For

- Enterprise teams needing APM/tracing/log correlation → use Datadog
- Teams needing status pages and on-call scheduling → use Better Stack
- Homelabbers who want free monitoring → use Netdata or Uptime Kuma

## Roadmap

- [ ] Custom remediation scripts (write your own fix actions)
- [ ] Kubernetes support (auto-remediation for pods and deployments)
- [ ] Slack/Discord alert integrations
- [ ] Multi-server correlation
- [ ] Status pages
- [ ] Log management

## Links

- 🌐 **Website:** [agentpulse.dustinnstroud.com](https://agentpulse.dustinnstroud.com)
- 📦 **Install:** `curl -fsSL https://agentpulse.dustinnstroud.com/install.sh | bash`
- 💬 **Discord:** [Join our community](https://discord.gg/vCaXFWuc)
- 📧 **Email:** support@agentpulse.dustinnstroud.com

## License

The AgentPulse agent is open source (see [LICENSE](LICENSE)). The cloud platform and dashboard are proprietary SaaS.

---

<div align="center">

**Stop firefighting. Start sleeping.** 🛡️

[Get Started →](https://agentpulse.dustinnstroud.com/signup)

</div>
