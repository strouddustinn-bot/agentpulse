#!/usr/bin/env bash
# install-agent.sh — Install AgentPulse on Linux (systemd) or macOS (launchd)
# Usage: curl -fsSL https://install.agentpulse.io | bash
# Or:    ./install-agent.sh --enrollment-token <token> --backend-url https://api.agentpulse.io
#
# Options:
#   --enrollment-token <token>    Token from the dashboard [required]
#   --backend-url <url>           Control-plane API URL [default: https://api.agentpulse.io]
#   --config-url <url>            URL to fetch pre-generated config [optional]
#   --interactive                 Ask for confirmation before system changes
#   --unattended                  Skip all prompts (assumes --interactive was not passed)

set -euo pipefail

# ─── Defaults ─────────────────────────────────────────────────────────────────
BACKEND_URL="${BACKEND_URL:-https://api.agentpulse.io}"
ENROLLMENT_TOKEN=""
CONFIG_URL=""
INTERACTIVE=false
UNATTENDED=false
INSTALL_USER="${SUDO_USER:-$(whoami)}"
LOG_DIR="/var/log/agentpulse"
STATE_DIR="/var/lib/agentpulse"
CONFIG_DIR="/etc/agentpulse"
PYTHON_CMD="${PYTHON_CMD:-python3}"
INSTALL_TYPE=""

# ─── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[1;33m'; BLU='\033[0;34m'
BLD='\033[1m'; RST='\033[0m'

info()    { echo -e "${BLU}[INFO]${RST} $*"; }
success() { echo -e "${GRN}[OK]${RST}   $*"; }
warn()    { echo -e "${YEL}[WARN]${RST} $*"; }
error()   { echo -e "${RED}[ERR]${RST}  $*"; }
die()     { error "$@"; exit 1; }

# ─── OS detection ─────────────────────────────────────────────────────────────
detect_os() {
  case "$(uname -s)" in
    Linux*)  INSTALL_TYPE=systemd; INSTALL_USER="${INSTALL_USER:-root}";;
    Darwin*) INSTALL_TYPE=launchd;;
    *)       die "Unsupported OS: $(uname -s)";;
  esac
}

# ─── Helpers ──────────────────────────────────────────────────────────────────
require_root() {
  [[ $EUID -eq 0 ]] || die "Must be run as root. Hint: sudo $0 $*"
}
require_token() {
  [[ -n "$ENROLLMENT_TOKEN" ]] || die "Missing --enrollment-token. Get one from ${BACKEND_URL}/enrollment"
}
http_fetch() {
  command -v curl >/dev/null && curl -fsSL "$1" || command -v wget >/dev/null && wget -qO- "$1" || die "Neither curl nor wget found"
}
confirm() {
  local msg="${1:-Continue?}"
  if [[ "$UNATTENDED" == "true" ]]; then return 0; fi
  if [[ "$INTERACTIVE" != "true" ]]; then return 0; fi
  read -rp "$msg [y/N] " ans
  [[ "${ans,,}" == "y" ]] || { info "Aborted."; exit 0; }
}

# ─── Parse args ───────────────────────────────────────────────────────────────
parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --enrollment-token) ENROLLMENT_TOKEN="$2"; shift 2;;
      --backend-url)      BACKEND_URL="$2"; shift 2;;
      --config-url)       CONFIG_URL="$2"; shift 2;;
      --interactive)       INTERACTIVE=true; shift;;
      --unattended)       UNATTENDED=true; shift;;
      --python)           PYTHON_CMD="$2"; shift 2;;
      -h|--help)          cat <<'HELP'
Usage: install-agent.sh [options]

Options:
  --enrollment-token <tok>   Dashboard enrollment token [required]
  --backend-url <url>        Control-plane API [default: https://api.agentpulse.io]
  --config-url <url>         Pre-generated config to fetch [optional]
  --interactive              Confirm before system changes
  --unattended               Assume yes to all prompts
  --python <cmd>             Python interpreter [default: python3]
  -h, --help                 Show this help
HELP
                              exit 0;;
      *) warn "Unknown option: $1"; shift;;
    esac
  done
}

# ─── Prerequisites ─────────────────────────────────────────────────────────────
check_prereqs() {
  info "Checking prerequisites for ${INSTALL_TYPE} install..."
  command -v "$PYTHON_CMD" >/dev/null 2>&1 || die "Python not found: $PYTHON_CMD"
  local pyver
  pyver=$("$PYTHON_CMD" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  if [[ $(echo -e "$pyver\n3.10" | sort -V | head -1) != "3.10" ]]; then
    die "Python 3.10+ required, found: $pyver"
  fi
  success "Prerequisites OK (Python $pyver)"
}

# ─── Install steps ─────────────────────────────────────────────────────────────
install_linux() {
  require_root
  info "Installing AgentPulse for Linux (systemd)..."

  # 1. Create system user
  if ! id "agentpulse" &>/dev/null; then
    confirm "Create system user 'agentpulse'?"
    useradd --system --no-create-home --shell /usr/sbin/nologin agentpulse 2>/dev/null || true
    success "System user 'agentpulse' created"
  fi

  # 2. Create directories
  mkdir -p "$CONFIG_DIR" "$STATE_DIR" "$LOG_DIR"
  chown agentpulse:agentpulse "$STATE_DIR" "$LOG_DIR"
  chmod 0750 "$CONFIG_DIR" "$STATE_DIR" "$LOG_DIR"
  success "Directories created"

  # 3. Install package
  local pip_dest
  pip_dest=$("$PYTHON_CMD" -c "import site; print(site.getsitepackages()[0])")
  info "Installing AgentPulse Python package to ${pip_dest}..."
  "$PYTHON_CMD" -m pip install --quiet agentpulse
  success "Python package installed"

  # 4. Write config
  if [[ -n "$CONFIG_URL" ]]; then
    info "Fetching config from $CONFIG_URL..."
    http_fetch "$CONFIG_URL" > "$CONFIG_DIR/agentpulse.json"
  else
    cat > "$CONFIG_DIR/agentpulse.json" <<EOF
{
  "version": "1",
  "control_plane": {
    "backend_url": "$BACKEND_URL",
    "enrollment_token": "$ENROLLMENT_TOKEN",
    "auth_token": "",
    "checkin_interval": 60
  },
  "checks": {},
  "policy": { "mode": "alert_only" }
}
EOF
    info "Config written to $CONFIG_DIR/agentpulse.json"
    info "IMPORTANT: Replace 'auth_token' with the token returned after enrollment."
  fi
  chown root:root "$CONFIG_DIR/agentpulse.json"
  chmod 0640 "$CONFIG_DIR/agentpulse.json"

  # 5. Install systemd unit
  confirm "Install systemd unit file?"
  http_fetch "https://raw.githubusercontent.com/strouddustinn-bot/agentpulse/main/agent/systemd/agentpulse.service" \
    > /etc/systemd/system/agentpulse.service
  systemctl daemon-reload
  systemctl enable agentpulse
  success "Systemd unit installed and enabled"

  # 6. Logrotate
  confirm "Install logrotate config?"
  cat > /etc/logrotate.d/agentpulse <<'LOGROTATE'
/var/log/agentpulse/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0640 agentpulse agentpulse
LOGROTATE
  success "Logrotate configured"

  # 7. Start
  confirm "Start AgentPulse now?"
  systemctl start agentpulse
  systemctl status --no-pager agentpulse
  success "AgentPulse started"
  info "Run 'agentpulse enroll --config $CONFIG_DIR/agentpulse.json' to complete enrollment."
}

install_macos() {
  info "Installing AgentPulse for macOS (launchd)..."

  local homebrew_prefix
  homebrew_prefix=$(command -v brew >/dev/null 2>&1 && brew --prefix || echo "/usr/local")
  local plist_src="$homebrew_prefix/etc/agentpulse/com.agentpulse.agent.plist"

  # 1. Create user if needed
  if ! id "agentpulse" &>/dev/null 2>&1; then
    confirm "Create system user 'agentpulse'?"
    useradd -r -s /usr/bin/false agentpulse 2>/dev/null || true
    success "System user created"
  fi

  # 2. Create directories
  mkdir -p "$CONFIG_DIR" "$STATE_DIR" "$LOG_DIR"
  chown agentpulse:agentpulse "$STATE_DIR" "$LOG_DIR"
  success "Directories created"

  # 3. Install package
  info "Installing AgentPulse Python package..."
  "$PYTHON_CMD" -m pip install --quiet agentpulse
  success "Python package installed"

  # 4. Install plist
  confirm "Install launchd plist?"
  mkdir -p "$(dirname "$plist_src")"
  http_fetch "https://raw.githubusercontent.com/strouddustinn-bot/agentpulse/main/agent/launchd/com.agentpulse.agent.plist" \
    > "$plist_src"
  sed -i '' "s|__CONFIG_DIR__|$CONFIG_DIR|g" "$plist_src"
  sed -i '' "s|__LOG_DIR__|$LOG_DIR|g" "$plist_src"
  sed -i '' "s|__BACKEND_URL__|$BACKEND_URL|g" "$plist_src"
  sed -i '' "s|__ENROLLMENT_TOKEN__|$ENROLLMENT_TOKEN|g" "$plist_src"
  chown root:wheel "$plist_src"
  chmod 0644 "$plist_src"
  success "launchd plist installed"

  # 5. Load
  confirm "Load launchd service?"
  launchctl load "$plist_src"
  launchctl list | grep agentpulse || true
  success "AgentPulse loaded"
  info "Run 'agentpulse enroll --config $CONFIG_DIR/agentpulse.json' to complete enrollment."
}

# ─── Main ──────────────────────────────────────────────────────────────────────
main() {
  echo -e "${BLD}AgentPulse Installer${RST}"
  echo "─────────────────────────────────"
  detect_os
  parse_args "$@"
  require_token
  check_prereqs

  case "$INSTALL_TYPE" in
    systemd) install_linux;;
    launchd) install_macos;;
  esac

  echo ""
  success "Installation complete!"
  info "Next: Run 'agentpulse enroll' to register this server."
}

main "$@"
