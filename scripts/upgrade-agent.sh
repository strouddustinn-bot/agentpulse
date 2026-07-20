#!/usr/bin/env bash
# upgrade-agent.sh — Upgrade AgentPulse to a newer immutable release while
# preserving config and state.
#
# Usage:
#   sudo ./scripts/upgrade-agent.sh --version 0.2.0-beta.2
#
# Options mirror install-agent.sh for --repo/--wheel/--checksums/--python.
# Config (/etc/agentpulse) and state (/var/lib/agentpulse) are preserved.
# A backup of the previously installed wheel metadata is recorded under
# /var/lib/agentpulse/releases/ for rollback.

set -euo pipefail

API_URL="${API_URL:-}"
REPO="${AGENTPULSE_REPO:-strouddustinn-bot/agentpulse}"
VERSION="${AGENTPULSE_VERSION:-}"
WHEEL_PATH=""
CHECKSUMS_PATH=""
SKIP_CHECKSUM=false
PYTHON_CMD="${PYTHON_CMD:-python3}"
CONFIG_DIR="/etc/agentpulse"
STATE_DIR="/var/lib/agentpulse"
CONFIG_FILE="${CONFIG_DIR}/config.json"
RELEASE_DIR="${STATE_DIR}/releases"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[1;33m'; BLU='\033[0;34m'; RST='\033[0m'
info()    { echo -e "${BLU}[INFO]${RST} $*"; }
success() { echo -e "${GRN}[OK]${RST}   $*"; }
warn()    { echo -e "${YEL}[WARN]${RST} $*"; }
error()   { echo -e "${RED}[ERR]${RST}  $*"; }
die()     { error "$@"; exit 1; }

usage() {
  cat <<'HELP'
Usage: upgrade-agent.sh --version <ver> [options]

Upgrades the installed AgentPulse package to an immutable release artifact.
Preserves /etc/agentpulse and /var/lib/agentpulse.

Options:
  --version <ver>       Target release version without leading v
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
[[ -f "$CONFIG_FILE" ]] || die "Missing config ${CONFIG_FILE}; use install-agent.sh first"

mkdir -p "$RELEASE_DIR"
PREV_VERSION="$("$PYTHON_CMD" -c 'import agentpulse; print(agentpulse.__version__)' 2>/dev/null || echo unknown)"
info "Current version: ${PREV_VERSION}"
echo "$PREV_VERSION" > "${RELEASE_DIR}/previous-version"
# Preserve config and state intentionally — never wipe during upgrade.
cp -a "$CONFIG_DIR" "${RELEASE_DIR}/config-backup-${PREV_VERSION}" 2>/dev/null || true

ARGS=(--version "${VERSION:-local}" --skip-enroll --skip-start --python "$PYTHON_CMD" --repo "$REPO")
[[ -n "$WHEEL_PATH" ]] && ARGS+=(--wheel "$WHEEL_PATH")
[[ -n "$CHECKSUMS_PATH" ]] && ARGS+=(--checksums "$CHECKSUMS_PATH")
[[ "$SKIP_CHECKSUM" == "true" ]] && ARGS+=(--skip-checksum)
# Reuse installer for download + SHA-256 + package install + unit refresh.
bash "${SCRIPT_DIR}/install-agent.sh" "${ARGS[@]}"

# Record new version and restart while preserving config/state.
NEW_VERSION="$("$PYTHON_CMD" -c 'import agentpulse; print(agentpulse.__version__)' )"
echo "$NEW_VERSION" > "${RELEASE_DIR}/current-version"
agentpulse validate "$CONFIG_FILE"
if [[ -f /etc/systemd/system/agentpulse.service ]]; then
  systemctl restart agentpulse
  systemctl is-active --quiet agentpulse || die "AgentPulse service failed after upgrade"
elif [[ -f /Library/LaunchDaemons/com.agentpulse.agent.plist ]]; then
  launchctl kickstart -k system/com.agentpulse.agent
else
  die "No installed AgentPulse service definition found"
fi
success "Upgraded ${PREV_VERSION} -> ${NEW_VERSION} (config/state preserved)"
info "Rollback: sudo ${SCRIPT_DIR}/rollback-agent.sh --version ${PREV_VERSION}"
