---
layout: default
title: AgentPulse Install Guide
---

# Install guide

AgentPulse is in paid beta. Start with one Linux server in alert-only mode, then promote safe actions to ask-first or auto-fix after review.

```bash
curl -fsSL https://agentpulse.dustinnstroud.com/install.sh | bash
```

## Recommended beta rollout

1. Install on one non-critical server first.
2. Run alert-only mode for 24 hours.
3. Review detected services, disk paths, and recurring processes.
4. Enable ask-first remediation for safe actions.
5. Enable auto-fix only for actions you would run manually without hesitation.

## Need access?

If the installer is not available for your account yet, [join the paid beta](signup) and include your server OS, stack, and desired remediation policies.
