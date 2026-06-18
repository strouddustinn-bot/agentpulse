---
layout: default
title: "How AgentPulse Decides Before It Acts"
description: "A look inside AgentPulse's 6-stage decision loop — how it weighs context, consequences, and your configured policies before taking any action on your server."
---

# How AgentPulse Decides Before It Acts

It's 2:47 AM. Your disk hits 91%. You're asleep.

An alert-only tool wakes you up. A naive auto-remediator might delete something it shouldn't. AgentPulse does neither — it works through a six-stage decision loop before touching anything. Here's what that looks like in practice.

---

## Stage 1: Remember

Before AgentPulse draws any conclusions, it checks its baseline memory for your server. What's normal disk growth look like on a Tuesday night? Is there a backup job that runs at 2 AM and chews through temp space? Has this disk hovered around 89-91% for the past week without incident?

A spike at 2:47 AM might be routine. Or it might not. The agent knows the difference because it has been watching — not just reacting to thresholds.

---

## Stage 2: Reason

Given the anomaly and its context, AgentPulse identifies candidate responses. For a disk filling fast, the options might include: rotate logs, clean up `/tmp`, identify and report the largest recent file additions, or alert-only and let you decide.

This is not a rule engine that fires the first match. Multiple options are weighed against each other, and the agent considers what it knows about your specific setup — which directories are growing, how fast, and whether anything unusual changed recently.

---

## Stage 3: Simulate

Each candidate action gets evaluated for consequences before it runs. Would cleaning `/tmp` interrupt a running job that's actively writing there? Is the process eating disk space something that a system dependency relies on? Could log rotation interfere with a service that keeps file handles open?

This is lightweight consequence modeling, not a full system simulation. But it catches the cases where "obvious fix" makes things worse — which is exactly when you least want your monitoring agent to act without thinking.

---

## Stage 4: Gate

Every proposed action is checked against your configured policies before it executes. You decide in advance how AgentPulse should handle different action types:

- **Auto-fix**: the action runs immediately, no interruption.
- **Ask-first**: the agent pauses and sends you an approval request before proceeding.
- **Alert-only**: the agent stops here, notifies you, and waits.

In our 2:47 AM scenario, maybe you've configured log rotation as auto-fix but process kills as ask-first. The gate enforces that. No action runs against your policy, regardless of how confident the agent is.

---

## Stage 5: Act

The validated action runs locally on your server — no cloud round-trip, no dependency on an external API being reachable at 3 AM. AgentPulse records the full outcome: what ran, what changed, whether the disk usage dropped, and whether the fix held. That record feeds back into the memory layer so future decisions are informed by what actually happened.

If the fix works, you wake up to a summary. If it doesn't, the agent escalates rather than retrying blindly.

---

## Stage 6: Share

This stage is on the roadmap, not yet live. The idea: when AgentPulse runs across a fleet of servers, agents share anonymized patterns with each other. A novel log pattern associated with a compromise on one server can become a detection rule on all of them — without any of your server-specific data leaving your infrastructure.

Each agent remains sovereign. The intelligence is collective.

---

## Why This Matters

Most monitoring scripts work like this: threshold exceeded, action fires. Simple, predictable, and completely blind to context.

The difference with a decision loop is that each stage adds a constraint. Remember catches false positives by anchoring against baseline. Reason surfaces options instead of defaulting to the first match. Simulate filters out fixes that cause collateral damage. Gate ensures the agent never exceeds the authority you gave it. Act records the result so the loop improves over time.

A script that deletes your logs when disk hits 90% will work fine until the night your database is mid-write and the log file it just removed is still open. A decision loop asks whether that's worth checking first.

The goal is not a smarter alerting tool. It is an agent that handles the routine problems — the ones you have already solved once and do not want to solve again at 3 AM — while staying inside the boundaries you set.

---

If you want to see this running on your server, [sign up for early access](https://agentpulse.dustinnstroud.com/signup). Setup takes about five minutes, and you can configure your first policies from a simple YAML file.
