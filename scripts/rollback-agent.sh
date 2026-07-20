#!/usr/bin/env bash
# rollback-agent.sh — Roll AgentPulse back to a previous immutable release.
#
# Usage:
#   sudo ./scripts/rollback-agent.sh --version 0.2.0-beta.1
#
# Preserves /etc/agentpulse config and /var/lib/agentpulse state. Reinstalls the
# requested release wheel after SHA-256 verification.

set -euo pipefail

REPO="${AGENTPULSE_REPO:-strouddustinn-bot/agentpulse}"
VERSION="${AGENTPULSE_VERSION:-}"
WHEEL_PATH=""
CHECKSUMS_PATH=""
SKIP_CHECKSUM=false
PYTHON_CMD="${PYTHON_CMD:-python3}"
CONFIG_FILE="/etc/agentpulse/config.json"
STATE_DIR="/var/lib/agentpulse"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[1;33m'; BLU='\033[0;34m'; RST='\033[0m'
info()    { echo -e "${BLU}[INFO]${RST} $*"; }
success() { echo -e "${GRN}[OK]${RST}   $*"; }
error()   { echo -e "${RED}[ERR]${RST}  $*"; }
die()     { error "$@"; exit 1; }

usage() {
  cat <<'HELP'
Usage: rollback-agent.sh --version <ver> [options]

Reinstalls a previous immutable release. Config and state directories are
preserved.

Options:
  --version <ver>       Target previous version without leading v
  --repo <owner/name>   GitHub repository
  --wheel <path>        Local wheel
  --checksums <path>    Local SHA256SUMS
  --skip-checksum       Lab only
  --python <cmd>        Python interpreter
  -h, --help            Show help
HELP
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --version) VERSION="$2"; shift 2 ;;
      --repo) REPO="$2"; shift 2 ;;
      --wheel) WHEEL_PATH="$2"; shift 2 ;;
      --checksums) CHECKSUMS_PATH="$2"; shift 2 ;;
      --skip-checksum) SKIP_CHECKSUM=true; shift ;;
      --python) PYTHON_CMD="$2"; shift 2 ;;
      -h|--help) usage; exit 0 ;;
      *) die "Unknown option: $1" ;;
    esac
  done
}

[[ ${EUID} -eq 0 ]] || die "Must be run as root"
parse_args "$@"
[[ -n "$VERSION" ]] || die "--version is required"
[[ -f "$CONFIG_FILE" ]] || die "Missing config ${CONFIG_FILE}"

CURRENT="$("$PYTHON_CMD" -c 'import agentpulse; print(agentpulse.__version__)' 2>/dev/null || echo unknown)"
info "Rolling back from ${CURRENT} to ${VERSION:-local wheel}"
info "Preserving config and state under /etc/agentpulse and ${STATE_DIR}"

ARGS=(--version "${VERSION:-local}" --skip-enroll --skip-start --python "$PYTHON_CMD" --repo "$REPO")
[[ -n "$WHEEL_PATH" ]] && ARGS+=(--wheel "$WHEEL_PATH")
[[ -n "$CHECKSUMS_PATH" ]] && ARGS+=(--checksums "$CHECKSUMS_PATH")
[[ "$SKIP_CHECKSUM" == "true" ]] && ARGS+=(--skip-checksum)

bash "${SCRIPT_DIR}/install-agent.sh" "${ARGS[@]}"

NEW_VERSION="$("$PYTHON_CMD" -c 'import agentpulse; print(agentpulse.__version__)' )"
agentpulse validate "$CONFIG_FILE"
if [[ -f /etc/systemd/system/agentpulse.service ]]; then
  systemctl restart agentpulse
  systemctl is-active --quiet agentpulse || die "AgentPulse service failed after rollback"
elif [[ -f /Library/LaunchDaemons/com.agentpulse.agent.plist ]]; then
  launchctl kickstart -k system/com.agentpulse.agent
else
  die "No installed AgentPulse service definition found"
fi
mkdir -p "${STATE_DIR}/releases"
echo "$NEW_VERSION" > "${STATE_DIR}/releases/current-version"
success "Rollback complete: now running ${NEW_VERSION}"
