#!/usr/bin/env bash
# smoke-test.sh — Quick sanity check that AgentPulse is installed and healthy
# Usage: ./smoke-test.sh [--config /path/to/config.json]
#
# Exit codes: 0 = all OK, 1 = warnings, 2 = critical failures

set -euo pipefail

CONFIG_PATH="${1:-/etc/agentpulse/agentpulse.json}"
RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[1;33m'; RST='\033[0m'
WARN_COUNT=0; FAIL_COUNT=0

ok()   { echo -e "${GRN}[PASS]${RST} $*"; }
fail() { echo -e "${RED}[FAIL]${RST} $*"; ((FAIL_COUNT++)); }
warn() { echo -e "${YEL}[WARN]${RST} $*"; ((WARN_COUNT++)); }

# 1. Binary
command -v agentpulse >/dev/null 2>&1 && ok "agentpulse binary" || { fail "agentpulse not in PATH"; }

# 2. Python module
python3 -c "import agentpulse" 2>/dev/null && ok "agentpulse Python module" || { fail "agentpulse not importable"; }

# 3. Config file
[[ -f "$CONFIG_PATH" ]] && ok "config: $CONFIG_PATH" || fail "config not found: $CONFIG_PATH"

# 4. Config valid JSON
python3 -c "import json; json.load(open('$CONFIG_PATH'))" 2>/dev/null \
  && ok "config is valid JSON" || fail "config is not valid JSON"

# 5. Required config fields
python3 -c "
import json, sys
cfg = json.load(open('$CONFIG_PATH'))
required = ['version', 'control_plane', 'checks']
missing = [k for k in required if k not in cfg]
sys.exit(len(missing))" 2>/dev/null \
  && ok "config has required fields" || fail "config missing required fields"

# 6. Service running (Linux)
if command -v systemctl >/dev/null 2>&1; then
  systemctl is-active --quiet agentpulse 2>/dev/null && ok "systemd service active" \
    || warn "systemd service not active (may be stopped or not yet enrolled)"
fi

# 7. Service running (macOS)
if command -v launchctl >/dev/null 2>&1; then
  launchctl list | grep -q com.agentpulse && ok "launchd service loaded" \
    || warn "launchd service not loaded"
fi

# 8. Log directory writable
[[ -d /var/log/agentpulse ]] && [[ -w /var/log/agentpulse ]] \
  && ok "log dir writable" || warn "log dir missing or not writable"

# 9. State directory
[[ -d /var/lib/agentpulse ]] && ok "state dir exists" || warn "state dir missing"

# 10. Python deps
for pkg in agentpulse.decision_loop agentpulse.checks agentpulse.baseline; do
  python3 -c "import $pkg" 2>/dev/null && ok "module: $pkg" || fail "missing: $pkg"
done

echo ""
echo "Results: $FAIL_COUNT failures, $WARN_COUNT warnings"

[[ $FAIL_COUNT -eq 0 ]] && exit 0
[[ $FAIL_COUNT -le 2 ]] && exit 1
exit 2
