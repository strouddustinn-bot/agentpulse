# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in AgentPulse, please report it responsibly:

- **Email:** security@agentpulse.ca
- **Do not** open a public GitHub issue for security vulnerabilities

We will acknowledge your report within 24 hours and provide a detailed response within 72 hours.

## Agent packaging and install integrity

- Install only versioned GitHub Release artifacts after SHA-256 verification.
- Never install from mutable branch raw URLs.
- Agent credentials must be stored mode `0600` and never logged.
- Enrollment tokens are one-time and must not remain in world-readable config.
- Public `install.sh` stays fail-closed until clean-host install/upgrade/rollback evidence exists.

See `docs/runbooks/agent-release-rollback.md`.
