#!/usr/bin/env bash
# Public installation remains disabled until a versioned, checksummed artifact
# passes clean-host install, upgrade, and rollback gates.
#
# When those gates pass, this endpoint will require an explicit release version
# and will install only from GitHub Releases after SHA-256 verification.
# It will never download mutable files from a branch (for example raw main).
set -euo pipefail

printf '%s\n' '[AgentPulse] Public installer is not released. See https://agentpulse.ca/install for current release gates.' >&2
printf '%s\n' '[AgentPulse] Planned flow: versioned GitHub Release wheel + SHA-256 verification (no raw branch downloads).' >&2
exit 1
