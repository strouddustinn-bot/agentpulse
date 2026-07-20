#!/usr/bin/env bash
# uninstall-agent.sh — Remove AgentPulse from Linux (systemd) or macOS (launchd)
# Usage: sudo ./uninstall-agent.sh [--purge] [--skip-backup]
#
# Options:
#   --purge       Remove ALL state, logs, and credentials (default: preserve state)
#   --skip-backup Skip backing up config before removal
#   --unattended  Assume yes to all prompts

set -euo pipefail

PURGE=false
SKIP_BACKUP=false
UNATTENDED=false

RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[1;33m'; BLU='\033[0;34m'; RST='\033[0m'
info()    { echo -e "${BLU}[INFO]${RST} $*"; }
success() { echo -e "${GRN}[OK]${RST}   $*"; }
warn()    { echo -e "${YEL}[WARN]${RST} $*"; }
error()   { echo -e "${RED}[ERR]${RST}  $*"; }
die()     { error "$@"; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --purge)       PURGE=true; shift;;
    --skip-backup) SKIP_BACKUP=true; shift;;
    --unattended)  UNATTENDED=true; shift;;
    *)             die "Unknown option: $1";;
  esac
done

confirm() {
  [[ "$UNATTENDED" == "true" ]] && return 0
  read -rp "$1 [y/N] " ans; [[ "${ans,,}" == "y" ]]
}

backup_config() {
  local backup_dir
  backup_dir="$(mktemp -d /tmp/agentpulse-uninstall.XXXXXX)" || die "Could not create secure backup directory"
  chmod 0700 "$backup_dir"
  [[ -f /etc/agentpulse/config.json ]] && cp -p /etc/agentpulse/config.json "$backup_dir/"
  [[ -f /etc/agentpulse/agent.credential ]] && cp -p /etc/agentpulse/agent.credential "$backup_dir/"
  info "Config backed up to $backup_dir"
}

uninstall_linux() {
  require_root() { [[ $EUID -eq 0 ]] || die "Must be run as root (sudo)."; }
  require_root

  info "Uninstalling AgentPulse from Linux (systemd)..."

  # 1. Stop service
  if systemctl is-active --quiet agentpulse 2>/dev/null; then
    confirm "Stop AgentPulse service?" && systemctl stop agentpulse
  fi
  if systemctl is-enabled --quiet agentpulse 2>/dev/null; then
    confirm "Disable AgentPulse service?" && systemctl disable agentpulse
  fi

  # 2. Remove systemd unit and logrotate
  [[ -f /etc/systemd/system/agentpulse.service ]] && \
    confirm "Remove systemd unit?" && rm -f /etc/systemd/system/agentpulse.service
  [[ -f /etc/logrotate.d/agentpulse ]] && \
    confirm "Remove logrotate config?" && rm -f /etc/logrotate.d/agentpulse
  systemctl daemon-reload

  # 3. Backup config
  if [[ "$SKIP_BACKUP" != "true" ]]; then
    backup_config
  fi

  # 4. Remove Python package
  confirm "Uninstall Python package?" && pip3 uninstall -y agentpulse 2>/dev/null || true

  # 5. Purge or preserve state
  if [[ "$PURGE" == "true" ]]; then
    confirm "PURGE: Remove all state, logs, and credentials?" || die "Purge cancelled"
    rm -rf /var/lib/agentpulse /var/log/agentpulse /etc/agentpulse
    userdel agentpulse 2>/dev/null || true
    success "All AgentPulse data purged"
  else
    warn "State preserved at /var/lib/agentpulse and /var/log/agentpulse"
    warn "Credentials preserved at /etc/agentpulse"
    success "AgentPulse uninstalled"
  fi
}

uninstall_macos() {
  info "Uninstalling AgentPulse from macOS (launchd)..."

  local plist="/Library/LaunchDaemons/com.agentpulse.agent.plist"

  # 1. Unload
  if launchctl list | grep -q com.agentpulse; then
    confirm "Unload launchd service?" && launchctl unload "$plist" 2>/dev/null || true
  fi

  # 2. Remove plist
  [[ -f "$plist" ]] && confirm "Remove launchd plist?" && rm -f "$plist"

  # 3. Backup
  if [[ "$SKIP_BACKUP" != "true" ]]; then
    backup_config
  fi

  # 4. Remove Python package
  confirm "Uninstall Python package?" && pip3 uninstall -y agentpulse 2>/dev/null || true

  # 5. Purge or preserve
  if [[ "$PURGE" == "true" ]]; then
    confirm "PURGE: Remove all state, logs, and credentials?" || die "Purge cancelled"
    rm -rf /var/lib/agentpulse /var/log/agentpulse /etc/agentpulse
    dscl . -delete /Users/agentpulse 2>/dev/null || true
    success "All AgentPulse data purged"
  else
    warn "State preserved at /var/lib/agentpulse and /var/log/agentpulse"
    success "AgentPulse uninstalled"
  fi
}

# ─── Detect OS and run ────────────────────────────────────────────────────────
case "$(uname -s)" in
  Linux)  uninstall_linux;;
  Darwin) uninstall_macos;;
  *)      die "Unsupported OS: $(uname -s)";;
esac

success "Done."
