#!/usr/bin/env bash
# The checksummed v0.2.0-beta.2 artifact passed clean-host install, upgrade,
# rollback, uninstall, and reinstall acceptance. This public convenience
# installer remains intentionally disabled because onboarding and the paid
# account lifecycle have not started.
#
# If public installation opens after staging and pilot proof, this endpoint will
# require an explicit release version and install only from GitHub Releases
# after SHA-256 verification.
# It will never download mutable files from a branch (for example raw main).
set -euo pipefail

printf '%s\n' '[AgentPulse] Public onboarding is closed; this installer intentionally performs no installation.' >&2
printf '%s\n' '[AgentPulse] v0.2.0-beta.2 passed artifact acceptance. See https://agentpulse.ca/install for the current lifecycle boundary.' >&2
exit 1
