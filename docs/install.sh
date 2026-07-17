#!/usr/bin/env bash
#
# AgentPulse installer.
#
# Installs the AgentPulse monitoring + policy-gated remediation agent as a
# systemd service, configured ALERT-ONLY by default. Nothing is auto-fixed
# until you explicitly change a check's mode to "ask" or "auto" in
# /etc/agentpulse/config.json.
#
# Review this script before running it. Recommended usage:
#   curl -fsSL https://agentpulse.ca/install.sh -o install.sh
#   less install.sh         # read it
#   sudo bash install.sh
#
set -euo pipefail

REPO_TARBALL="https://github.com/strouddustinn-bot/agentpulse/archive/refs/heads/main.tar.gz"
PREFIX="/opt/agentpulse"
CONF_DIR="/etc/agentpulse"
CONF_FILE="${CONF_DIR}/config.json"
STATE_DIR="/var/lib/agentpulse"
LOG_DIR="/var/log/agentpulse"
BIN="/usr/local/bin/agentpulse"
UNIT="/etc/systemd/system/agentpulse.service"

say() { printf '\033[1;34m[AgentPulse]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[AgentPulse] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "please run as root (sudo bash install.sh)"

command -v python3 >/dev/null 2>&1 || die "python3 is required (3.8+)"
PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
say "found python ${PYV}"

DL=""
if command -v curl >/dev/null 2>&1; then DL="curl -fsSL"; elif command -v wget >/dev/null 2>&1; then DL="wget -qO-"; else die "need curl or wget"; fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

say "downloading agent..."
$DL "$REPO_TARBALL" > "$TMP/src.tar.gz" || die "download failed"
tar -xzf "$TMP/src.tar.gz" -C "$TMP" || die "extract failed"
SRC=$(find "$TMP" -maxdepth 3 -type d -name agentpulse -path '*/agent/agentpulse' | head -1)
[ -n "$SRC" ] || die "could not locate agent package in download"

say "installing package to ${PREFIX}"
mkdir -p "$PREFIX"
rm -rf "${PREFIX}/agentpulse"
cp -r "$SRC" "${PREFIX}/agentpulse"

say "installing launcher to ${BIN}"
cat > "$BIN" <<EOF
#!/usr/bin/env bash
exec env PYTHONPATH="${PREFIX}" python3 -m agentpulse.cli "\$@"
EOF
chmod +x "$BIN"

mkdir -p "$CONF_DIR" "$STATE_DIR" "$LOG_DIR"
if [ ! -f "$CONF_FILE" ]; then
  say "writing default ALERT-ONLY config to ${CONF_FILE}"
  EXAMPLE=$(dirname "$SRC")/agentpulse.config.example.json
  if [ -f "$EXAMPLE" ]; then cp "$EXAMPLE" "$CONF_FILE"; else
    cat > "$CONF_FILE" <<'JSON'
{
  "interval_seconds": 60,
  "state_file": "/var/lib/agentpulse/state.json",
  "log_file": "/var/log/agentpulse/agentpulse.log",
  "notify": {"type": "stdout"},
  "checks": {
    "disk": {"mode": "alert", "threshold_percent": 90, "paths": ["/"], "cleanup_globs": ["/tmp/*", "/var/tmp/*"], "cleanup_older_than_days": 3},
    "service": {"mode": "alert", "services": []},
    "process": {"mode": "alert", "mem_percent_threshold": 85}
  }
}
JSON
  fi
else
  say "keeping existing config at ${CONF_FILE}"
fi

say "validating config"
"$BIN" validate "$CONF_FILE" || die "config failed validation"

say "installing systemd unit"
UNIT_SRC=$(dirname "$(dirname "$SRC")")/systemd/agentpulse.service
if [ -f "$UNIT_SRC" ]; then cp "$UNIT_SRC" "$UNIT"; else
  cat > "$UNIT" <<'UNITEOF'
[Unit]
Description=AgentPulse monitoring + policy-gated remediation agent
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
ExecStart=/usr/local/bin/agentpulse run /etc/agentpulse/config.json
Restart=on-failure
RestartSec=10
NoNewPrivileges=true
[Install]
WantedBy=multi-user.target
UNITEOF
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
  systemctl enable --now agentpulse.service
  say "service started (alert-only). Status:"
  systemctl --no-pager --lines=3 status agentpulse.service || true
else
  say "systemd not detected; run manually with: ${BIN} run ${CONF_FILE}"
fi

cat <<DONE

[AgentPulse] Installed. AgentPulse is watching in ALERT-ONLY mode — it will not change anything yet.

Next steps:
  1. Edit ${CONF_FILE}: list the services you care about, set disk threshold.
  2. Run a single cycle to see what it finds:
       sudo ${BIN} run-once ${CONF_FILE}
  3. When ready, promote one safe action to "ask" (you approve each fix) or
     "auto" (the agent fixes it, then verifies and escalates if it didn't clear).
     Approve queued ask-first actions with:
       sudo ${BIN} list-pending ${CONF_FILE}
       sudo ${BIN} approve ${CONF_FILE} <id>

Uninstall:  sudo systemctl disable --now agentpulse && sudo rm -rf ${PREFIX} ${BIN} ${UNIT}
DONE
