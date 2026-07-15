---
layout: default
title: "How AgentPulse Decides Before It Acts"
description: "A look inside AgentPulse's six-stage decision loop — how it weighs context, simulates consequences, checks your policies, and verifies every fix before calling anything done."
---

# How AgentPulse Decides Before It Acts

It's 2:47 AM. Your disk hits 91%. You're asleep.

An alert-only tool wakes you up. A naive auto-remediator might delete something it shouldn't — and then confidently report success without checking. AgentPulse does neither. It works through a six-stage decision loop before touching anything, and it doesn't call a fix done until it has re-measured the problem. Here's what that looks like in practice.

---

## Stage 1: Remember

Before AgentPulse draws any conclusions, it consults its statistical baseline for your server. For each metric it tracks, the agent maintains a running picture of normal — has this disk hovered around 89–91% for the past week without incident, or did it jump ten points overnight?

A reading at 2:47 AM might be routine. Or it might not. Baseline anomalies are advisory — they alert you, they never trigger a fix on their own — but they give both you and the agent the context that raw thresholds miss.

---

## Stage 2: Reason

Before acting, the agent states the expected end-state as a testable claim: *"disk usage on `/` should drop below the threshold after removing old files"*, or *"service nginx should report active after restart."*

This sounds small, but it's the foundation of everything downstream. An action without a testable expectation can't be verified — so AgentPulse never runs one.

---

## Stage 3: Simulate

The fix runs as a dry-run first. For a disk cleanup, the agent walks the cleanup paths you configured and captures exactly which files *would* be removed and how much space that *would* free — without deleting anything.

A simulation that fails, or that matches nothing at all, stops the cycle right there. If the dry-run can't demonstrate the fix would do something, the real thing doesn't run.

---

## Stage 4: Gate

The simulated plan is checked twice over.

First, against **your policy**: every check runs as auto-fix, ask-first, or alert-only — your call, per action type. Ask-first queues the fix until you approve it with one command. Alert-only stops here and notifies you.

Second, against **hard rules in code that no config can relax**: never sweep a system path, never delete directories or follow symlinks, only restart allowlisted services, never kill a process automatically, and a fail-closed allowlist — an action type the gate doesn't explicitly recognize is refused, full stop. Even a human-approved action re-runs this gate before executing.

---

## Stage 5: Act

The validated action runs locally on your server — no cloud round-trip, no dependency on an external API being reachable at 3 AM.

---

## Stage 6: Verify

This is the stage most auto-remediation scripts skip, and it's the one that matters most.

After acting, AgentPulse re-measures the original condition. Did disk usage actually drop below the threshold? Is the service actually active now? Three outcomes:

- **Verified** — the condition cleared. You wake up to a summary.
- **Didn't clear** — the fix ran but the problem persists. The agent **escalates to you and stops**. It never blind-retries a destructive action.
- **Nothing changed** — the action ran but was a no-op (nothing matched the cleanup rules, say). That can't have fixed anything, so it's treated as an escalation too — not a false success.

Every cycle — expectation, simulation, gate verdict, execution, verification, outcome — is recorded, so you can always answer "what did the agent do, and why?"

---

## On the Roadmap: Share

When AgentPulse runs across a fleet of servers, we want agents to share anonymized patterns with each other — a failure signature caught on one server becoming a heads-up on all of them, without any server-specific data leaving your infrastructure. That stage isn't live yet; the single-server loop came first.

---

## Why This Matters

Most monitoring scripts work like this: threshold exceeded, action fires, exit 0. Simple, predictable, and completely blind to whether the action worked.

Each stage of the loop adds a constraint. Remember anchors decisions against your server's actual normal. Reason forces a testable expectation. Simulate proves the fix would do something before it does anything. Gate ensures the agent never exceeds the authority you gave it — or the hard limits we refuse to let anyone lift. Verify catches the case every naive script misses: the fix that ran and didn't work.

A script that deletes old logs when disk hits 90% will work fine until the night the disk is full of something else entirely — and the script reports success while your database goes down. A decision loop notices the number didn't move, and wakes you up on purpose.

The goal is not a smarter alerting tool. It is an agent that handles the routine problems — the ones you have already solved once and do not want to solve again at 3 AM — while staying inside the boundaries you set.

---

If you want to see this running on your server, [join the paid beta](https://agentpulse.ca/signup). Setup takes about five minutes, and every policy lives in one readable JSON config file.
