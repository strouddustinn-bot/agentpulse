#!/usr/bin/env bash
# install-agent.sh — Install a versioned, checksummed AgentPulse release.
#
# Usage:
#   sudo ./scripts/install-agent.sh \
#     --version 0.2.0-beta.1 \
#     --enrollment-token <token> \
#     --api-url https://staging-api.agentpulse.ca
#
# Optional:
#   --repo owner/name          GitHub repo for releases [default: strouddustinn-bot/agentpulse]
#   --wheel /path/to.whl       Use a local wheel instead of downloading
#   --checksums /path/file     Local SHA256SUMS file (required with --wheel unless --skip-checksum)
#   --skip-checksum            Dangerous; only for offline lab validation
#   --skip-enroll              Install package/service only; do not enroll
#   --skip-start               Do not start the service after install
#   --python python3           Python interpreter
#   --unattended               Non-interactive
#
# Security properties:
# - Requires an explicit release version (or a local wheel path).
# - Downloads only from GitHub Releases (immutable tag assets), never raw branch files.
# - Verifies SHA-256 before installation.
# - Writes agent credentials with mode 0600.
# - Never places the enrollment token into a world-readable process list after enroll
#   (token is passed via argv only to agentpulse enroll, then discarded from config).

set -euo pipefail

API_URL="${API_URL:-https://api.agentpulse.ca}"
REPO="${AGENTPULSE_REPO:-strouddustinn-bot/agentpulse}"
VERSION="${AGENTPULSE_VERSION:-}"
ENROLLMENT_TOKEN=""
WHEEL_PATH=""
CHECKSUMS_PATH=""
SKIP_CHECKSUM=false
SKIP_ENROLL=false
SKIP_START=false
UNATTENDED=false
PYTHON_CMD="${PYTHON_CMD:-python3}"
CONFIG_DIR="/etc/agentpulse"
STATE_DIR="/var/lib/agentpulse"
LOG_DIR="/var/log/agentpulse"
CONFIG_FILE="${CONFIG_DIR}/config.json"
CREDENTIAL_FILE="${CONFIG_DIR}/agent.credential"
INSTALL_TYPE=""
WORKDIR=""

RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[1;33m'; BLU='\033[0;34m'
BLD='\033[1m'; RST='\033[0m'
info()    { echo -e "${BLU}[INFO]${RST} $*"; }
success() { echo -e "${GRN}[OK]${RST}   $*"; }
warn()    { echo -e "${YEL}[WARN]${RST} $*"; }
error()   { echo -e "${RED}[ERR]${RST}  $*"; }
die()     { error "$@"; exit 1; }

cleanup() {
  if [[ -n "${WORKDIR}" && -d "${WORKDIR}" ]]; then
    rm -rf "${WORKDIR}"
  fi
}
trap cleanup EXIT

detect_os() {
  case "$(uname -s)" in
    Linux*)  INSTALL_TYPE=systemd ;;
    Darwin*) INSTALL_TYPE=launchd ;;
    *)       die "Unsupported OS: $(uname -s)" ;;
  esac
}

require_root() {
  [[ ${EUID} -eq 0 ]] || die "Must be run as root. Hint: sudo $0 $*"
}

http_fetch_file() {
  local url="$1" dest="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$dest"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$dest" "$url"
  else
    die "Neither curl nor wget found"
  fi
}

usage() {
  cat <<'HELP'
Usage: install-agent.sh --version <ver> --enrollment-token <tok> [options]

Required (unless --skip-enroll and package-only lab use):
  --version <ver>              Release version without leading v (e.g. 0.2.0-beta.1)
  --enrollment-token <tok>     One-time enrollment token from the console

Options:
  --api-url <url>              Control-plane API [default: https://api.agentpulse.ca]
  --repo <owner/name>          GitHub repository [default: strouddustinn-bot/agentpulse]
  --wheel <path>               Install from a local wheel instead of GitHub Releases
  --checksums <path>           Local SHA256SUMS file
  --skip-checksum              Skip checksum verification (lab only; not for production)
  --skip-enroll                Do not enroll after install
  --skip-start                 Do not start the service
  --python <cmd>               Python interpreter [default: python3]
  --unattended                 Non-interactive
  -h, --help                   Show this help
HELP
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --version) VERSION="$2"; shift 2 ;;
      --enrollment-token) ENROLLMENT_TOKEN="$2"; shift 2 ;;
      --api-url) API_URL="$2"; shift 2 ;;
      --repo) REPO="$2"; shift 2 ;;
      --wheel) WHEEL_PATH="$2"; shift 2 ;;
      --checksums) CHECKSUMS_PATH="$2"; shift 2 ;;
      --skip-checksum) SKIP_CHECKSUM=true; shift ;;
      --skip-enroll) SKIP_ENROLL=true; shift ;;
      --skip-start) SKIP_START=true; shift ;;
      --python) PYTHON_CMD="$2"; shift 2 ;;
      --unattended) UNATTENDED=true; shift ;;
      -h|--help) usage; exit 0 ;;
      *) die "Unknown option: $1" ;;
    esac
  done
}

check_prereqs() {
  command -v "$PYTHON_CMD" >/dev/null 2>&1 || die "Python not found: $PYTHON_CMD"
  local pyver
  pyver=$("$PYTHON_CMD" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  "$PYTHON_CMD" - <<'PY' "$pyver" || die "Python 3.10+ required, found: $pyver"
import sys
major, minor = map(int, sys.argv[1].split("."))
raise SystemExit(0 if (major, minor) >= (3, 10) else 1)
PY
  command -v sha256sum >/dev/null 2>&1 || command -v shasum >/dev/null 2>&1 || die "sha256sum or shasum required"
  success "Prerequisites OK (Python $pyver, ${INSTALL_TYPE})"
}

normalize_version() {
  local v="$1"
  v="${v#v}"
  [[ -n "$v" ]] || die "Release version is required (--version)"
  echo "$v"
}

resolve_artifact() {
  if [[ -z "${VERSION}" && -n "${WHEEL_PATH}" ]]; then
    VERSION="local"
  fi
  VERSION="$(normalize_version "$VERSION")"
  WORKDIR="$(mktemp -d /tmp/agentpulse-install.XXXXXX)"
  local tag="v${VERSION}"
  local wheel_name="agentpulse-${VERSION}-py3-none-any.whl"
  # Hatch may normalize beta versions; accept either exact or glob match later.
  if [[ -n "$WHEEL_PATH" ]]; then
    [[ -f "$WHEEL_PATH" ]] || die "Wheel not found: $WHEEL_PATH"
    cp "$WHEEL_PATH" "$WORKDIR/"
    WHEEL_PATH="$WORKDIR/$(basename "$WHEEL_PATH")"
  else
    [[ "$VERSION" != "local" ]] || die "--version is required when not using --wheel"
    local base="https://github.com/${REPO}/releases/download/${tag}"
    info "Downloading release ${tag} wheel and SHA256SUMS"
    http_fetch_file "${base}/SHA256SUMS" "$WORKDIR/SHA256SUMS"
    # Try the conventional wheel name first, then discover from checksums.
    if ! http_fetch_file "${base}/${wheel_name}" "$WORKDIR/${wheel_name}" 2>/dev/null; then
      local discovered
      discovered="$(awk '/\.whl$/ {print $2; exit}' "$WORKDIR/SHA256SUMS" || true)"
      [[ -n "$discovered" ]] || die "No wheel listed in SHA256SUMS for ${tag}"
      wheel_name="$discovered"
      http_fetch_file "${base}/${wheel_name}" "$WORKDIR/${wheel_name}"
    fi
    WHEEL_PATH="$WORKDIR/${wheel_name}"
    CHECKSUMS_PATH="$WORKDIR/SHA256SUMS"
  fi

  if [[ "$SKIP_CHECKSUM" == "true" ]]; then
    warn "Skipping SHA-256 verification (--skip-checksum)"
    return
  fi
  [[ -n "$CHECKSUMS_PATH" && -f "$CHECKSUMS_PATH" ]] || die "SHA256SUMS required (or pass --skip-checksum for lab only)"
  verify_checksum "$WHEEL_PATH" "$CHECKSUMS_PATH"
}

verify_checksum() {
  local file="$1" sums="$2"
  local base
  base="$(basename "$file")"
  local expected
  expected="$(awk -v f="$base" '$2 == f {print $1; exit}' "$sums")"
  [[ -n "$expected" ]] || die "No SHA-256 entry for ${base} in $(basename "$sums")"
  local actual
  if command -v sha256sum >/dev/null 2>&1; then
    actual="$(sha256sum "$file" | awk '{print $1}')"
  else
    actual="$(shasum -a 256 "$file" | awk '{print $1}')"
  fi
  [[ "$expected" == "$actual" ]] || die "SHA-256 mismatch for ${base}: expected ${expected}, got ${actual}"
  success "SHA-256 verified for ${base}"
}

install_python_package() {
  info "Installing wheel: $(basename "$WHEEL_PATH")"
  "$PYTHON_CMD" -m pip install --upgrade pip >/dev/null
  "$PYTHON_CMD" -m pip install --force-reinstall "$WHEEL_PATH"
  command -v agentpulse >/dev/null 2>&1 || die "agentpulse console script not found on PATH after install"
  agentpulse --version >/dev/null
  success "Python package installed"
}

write_config() {
  mkdir -p "$CONFIG_DIR" "$STATE_DIR" "$LOG_DIR"
  if id agentpulse &>/dev/null; then
    chown agentpulse:agentpulse "$STATE_DIR" "$LOG_DIR" 2>/dev/null || true
  fi
  chmod 0750 "$CONFIG_DIR" "$STATE_DIR" "$LOG_DIR"

  if [[ ! -f "$CONFIG_FILE" ]]; then
    cat >"$CONFIG_FILE" <<EOF
{
  "hostname": "auto",
  "interval_seconds": 60,
  "state_file": "${STATE_DIR}/state.json",
  "log_file": "${LOG_DIR}/agentpulse.log",
  "notify": {
    "type": "stdout",
    "webhook_url": ""
  },
  "checkin": {
    "endpoint_url": "",
    "auth_token": "",
    "timeout_seconds": 10
  },
  "control_plane": {
    "enabled": true,
    "base_url": "${API_URL}",
    "credential_file": "${CREDENTIAL_FILE}",
    "timeout_seconds": 10,
    "local_policy_ceiling": "alert"
  },
  "baseline": {
    "enabled": true,
    "min_samples": 20,
    "z_threshold": 3.0,
    "min_abs_deviation": 2.0
  },
  "checks": {
    "disk": {
      "mode": "alert",
      "threshold_percent": 90,
      "paths": ["/"],
      "cleanup_globs": ["/tmp/*", "/var/tmp/*"],
      "cleanup_older_than_days": 3
    },
    "service": {
      "mode": "alert",
      "services": []
    },
    "process": {
      "mode": "alert",
      "mem_percent_threshold": 85
    }
  }
}
EOF
    success "Wrote alert-only config to ${CONFIG_FILE}"
  else
    info "Preserving existing config ${CONFIG_FILE}"
  fi
  chown root:root "$CONFIG_FILE" 2>/dev/null || true
  chmod 0640 "$CONFIG_FILE"
  # Ensure credential file path exists with tight perms if present.
  if [[ -f "$CREDENTIAL_FILE" ]]; then
    chmod 0600 "$CREDENTIAL_FILE"
  fi
}

install_systemd_unit() {
  local unit_src
  unit_src="$("$PYTHON_CMD" - <<'PY'
from agentpulse.assets import asset_path
print(asset_path("systemd", "agentpulse.service"))
PY
)"
  [[ -f "$unit_src" ]] || die "Packaged systemd unit missing from installed wheel"
  # Rewrite ExecStart to the resolved agentpulse binary and config path.
  local bin
  bin="$(command -v agentpulse)"
  sed -e "s|^ExecStart=.*|ExecStart=${bin} run ${CONFIG_FILE}|" \
      "$unit_src" > /etc/systemd/system/agentpulse.service
  chmod 0644 /etc/systemd/system/agentpulse.service
  systemctl daemon-reload
  systemctl enable agentpulse
  success "systemd unit installed"
}

install_launchd_plist() {
  local plist_src plist_dest
  plist_src="$("$PYTHON_CMD" - <<'PY'
from agentpulse.assets import asset_path
print(asset_path("launchd", "com.agentpulse.agent.plist"))
PY
)"
  [[ -f "$plist_src" ]] || die "Packaged launchd plist missing from installed wheel"
  plist_dest="/Library/LaunchDaemons/com.agentpulse.agent.plist"
  local bin
  bin="$(command -v agentpulse)"
  # Replace ProgramArguments binary and config paths if defaults differ.
  sed -e "s|/usr/local/bin/agentpulse|${bin}|g" \
      -e "s|/usr/local/etc/agentpulse/config.json|${CONFIG_FILE}|g" \
      -e "s|/usr/local/var/log/agentpulse/agentpulse.log|${LOG_DIR}/agentpulse.log|g" \
      "$plist_src" > "$plist_dest"
  chown root:wheel "$plist_dest"
  chmod 0644 "$plist_dest"
  success "launchd plist installed at ${plist_dest}"
}

enroll_atomically() {
  if [[ "$SKIP_ENROLL" == "true" ]]; then
    warn "Skipping enrollment (--skip-enroll)"
    return
  fi
  [[ -n "$ENROLLMENT_TOKEN" ]] || die "Missing --enrollment-token (or pass --skip-enroll)"
  info "Enrolling with control plane (atomic credential exchange)"
  # Enrollment token is only on this command line, not written into config JSON.
  agentpulse enroll "$CONFIG_FILE" "$ENROLLMENT_TOKEN"
  [[ -f "$CREDENTIAL_FILE" ]] || die "Enrollment did not create credential file"
  chmod 0600 "$CREDENTIAL_FILE"
  # Best-effort: ensure enrollment token is not left in config if an older template had it.
  "$PYTHON_CMD" - <<PY
import json
from pathlib import Path
path = Path("${CONFIG_FILE}")
data = json.loads(path.read_text())
cp = data.get("control_plane") or {}
changed = False
for key in ("enrollment_token", "auth_token"):
    if key in cp and cp[key]:
        cp[key] = ""
        changed = True
if "enabled" in cp:
    cp["enabled"] = True
data["control_plane"] = cp
if changed:
    path.write_text(json.dumps(data, indent=2) + "\\n")
print("credential_file=", cp.get("credential_file", "${CREDENTIAL_FILE}"))
PY
  success "Enrollment complete; credential mode 0600"
}

validate_and_start() {
  agentpulse validate "$CONFIG_FILE"
  agentpulse run-once --dry-run "$CONFIG_FILE" >/dev/null || warn "dry-run reported issues; review logs"
  if [[ "$SKIP_START" == "true" ]]; then
    warn "Skipping service start (--skip-start)"
    return
  fi
  case "$INSTALL_TYPE" in
    systemd)
      systemctl restart agentpulse
      systemctl --no-pager --full status agentpulse || true
      ;;
    launchd)
      launchctl bootout system/com.agentpulse.agent 2>/dev/null || true
      launchctl bootstrap system /Library/LaunchDaemons/com.agentpulse.agent.plist
      launchctl kickstart -k system/com.agentpulse.agent
      ;;
  esac
  success "Service started"
}

ensure_system_user() {
  if ! id agentpulse &>/dev/null; then
    if [[ "$INSTALL_TYPE" == "systemd" ]]; then
      useradd --system --no-create-home --shell /usr/sbin/nologin agentpulse 2>/dev/null || true
    fi
  fi
}

main() {
  echo -e "${BLD}AgentPulse Installer (immutable release)${RST}"
  detect_os
  parse_args "$@"
  require_root
  check_prereqs
  resolve_artifact
  ensure_system_user
  install_python_package
  write_config
  case "$INSTALL_TYPE" in
    systemd) install_systemd_unit ;;
    launchd) install_launchd_plist ;;
  esac
  enroll_atomically
  validate_and_start
  echo ""
  success "Installation complete for version ${VERSION}"
  info "Config: ${CONFIG_FILE}"
  info "Credentials: ${CREDENTIAL_FILE} (mode 0600)"
}

main "$@"
