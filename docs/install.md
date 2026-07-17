---
layout: default
title: Install AgentPulse
---

# Install guide

> **Beta implementation status (2026-07-17):** public self-serve installation
> is not released. The agent source and service definitions exist, but the
> current wheel configuration contains no packages, no immutable checksummed
> release artifact has been published, and clean-host install, upgrade, and
> rollback have not been proven. Do not use the commands below on a production
> host yet.

AgentPulse is intended to run as a systemd service on Linux or a launchd daemon
on macOS. Its safe default is **alert-only** mode: it watches and changes
nothing until an operator promotes a bounded action. Packaging and installer
integrity are Phase 1 release gates.

## Current developer verification

Contributors can verify the agent directly from a repository checkout without
installing it system-wide:

```bash
./scripts/bootstrap-dev.sh
make agent-test
make agent-lint
make agent-config-validate
```

This proves repository behavior only. It is not a clean-host installation
receipt.

## Planned public installation

The supported release flow will provide a versioned artifact, published
SHA-256 checksum, explicit version pin, and rollback instructions. Only after a
clean Linux host and a clean macOS host pass the release matrix will this guide
publish executable system-install commands.

The existing `scripts/install-agent.sh`, systemd unit, and launchd definitions
are implementation inputs, not a supported public installer. They currently
depend on unpublished packaging and must not be distributed as complete.

## Recommended rollout

1. **Install** on one non-critical server first.
2. **Watch.** Leave every check in `alert` mode for 24 hours.
3. **See what it finds** using the version-pinned command published with the release.
4. **Promote one safe action** to `ask` (you approve each fix) or `auto`.
5. **Trust, then expand.** Only set `auto` for actions you would run over SSH
   yourself.

## What "auto" actually does

Every auto-fix runs the full decision loop before and after acting:

1. **Simulate** the fix as a dry-run.
2. **Validate** it against hard safety predicates (no system-path sweeps, no
   auto process-kill, allowlisted services only).
3. **Execute** the validated action.
4. **Verify** by re-measuring — and if the condition didn't clear, **escalate to
   you instead of retrying.**

## Want a hand?

Controlled beta onboarding may be offered manually after the operator reviews
the build and acknowledges the current release gates. [Request beta
access](signup) with your OS, stack, and the incidents that keep repeating.

## Uninstall and rollback

Exact version-aware uninstall and rollback commands will be published and
tested with the release artifact. Until then, installation on production hosts
is unsupported.
