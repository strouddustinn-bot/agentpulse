#!/usr/bin/env bash
# Public installation remains disabled until a versioned, checksummed artifact
# passes clean-host install, upgrade, and rollback gates.
set -euo pipefail

printf '%s\n' '[AgentPulse] Public installer is not released. See https://agentpulse.ca/install for current release gates.' >&2
exit 1
