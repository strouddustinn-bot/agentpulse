---
layout: default
title: "Auto-Remediation for Indie Devs: A Practical Guide"
description: "How to set up automated server healing without enterprise budgets. A practical guide to auto-remediation for solo developers and small teams."
---

# Auto-Remediation for Indie Devs: A Practical Guide

You're a solo developer running 3 VPS boxes. Your monitoring setup is solid — you know within seconds when something goes wrong. But knowing isn't the problem. The problem is that you're the one who has to fix it. Every time.

Auto-remediation isn't a new concept. Enterprise SRE teams have used it for years. But until recently, it wasn't accessible to indie devs. Here's how to think about it, and how to get started.

## What Auto-Remediation Actually Means

At its core, auto-remediation is simple: **when a known problem occurs, automatically apply the known fix.**

The key word is "known." You're not asking AI to debug novel problems (though that's coming). You're automating the fixes you already know work:

- Disk full? → Clean /tmp, rotate logs, remove old backups
- Service crashed? → Restart it
- Process OOM? → Kill it, notify
- Brute force SSH? → Block the IP

These aren't judgment calls. They're rote operations you've done dozens of times.

## The Safety Question: "Isn't Auto-Fix Dangerous?"

It doesn't have to be. Good auto-remediation systems use **approval gates**:

- ✅ **Auto-fix** — "Always clean /tmp when disk > 90%"
- ⚠️ **Ask first** — "Restart nginx? Y/N" (the fix is queued until you approve it with one command)
- 🚨 **Alert only** — "Database process is using too much RAM, but don't touch it"

You decide the policy per action. Start conservative — alert-only for everything — then promote actions to auto-fix as you build trust.

## Setting Up Auto-Remediation with AgentPulse

1. **Request consideration for the post-staging controlled pilot.** The
   checksummed prerelease passed exact-artifact acceptance, but public
   self-serve onboarding remains closed. Do not install on an unapproved
   production host.

2. **Let it learn your baseline** — AgentPulse observes what "normal" looks like; the useful observation window depends on the host workload and has not been standardized as a fixed duration

3. **Configure remediation policies** — For each action type, choose auto-fix / ask-first / alert-only

4. **Monitor the results** — Every remediation action is logged. Review what happened and adjust policies

## What to Auto-Fix First

For an accepted artifact installed after approved onboarding, these are examples of bounded local policies; every automatic action still requires explicit configuration and an allowlisted scope:

| Issue | Fix | Recommended Policy |
|-------|-----|-------------------|
| /tmp or /var/log filling up | Clean eligible old files only in configured paths | Auto only after path allowlisting ✅ |
| nginx/apache crashed | Restart an explicitly configured service | Auto only after service allowlisting ✅ |
| Single process OOM | Kill process | Ask-first ⚠️ (AgentPulse enforces this — it never auto-kills) |
| Disk > 95% | Bounded cleanup inside configured paths | Auto only after path allowlisting ✅ |
| Database process issues | Don't touch | Alert-only 🚨 |
| Brute-force SSH attempts | Block IP | Ask-first ⚠️ (fail2ban today; on the AgentPulse roadmap) |

## Measure Value During the Pilot

AgentPulse does not yet have customer-pilot evidence for time savings or ROI. An invited pilot should record the incidents detected, actions approved, verification results, operator time, and any failures or escalations. Compare those observations with the pre-pilot baseline before making a value claim.

The approved Pro plan is C$99/month CAD for up to five hosts when fleet access ships, but that capacity remains a free founding reservation until staging and controlled-pilot proof pass.

## Getting Started

After staging passes and a pilot is explicitly approved, start with one
non-critical host in alert-only mode using the accepted versioned artifact.
Review enough representative observations to understand the baseline before
promoting any safe fix.

[Request pilot consideration or reserve founding pricing →](https://agentpulse.ca/signup)
