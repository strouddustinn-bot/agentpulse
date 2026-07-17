#!/usr/bin/env bash
# smoke-test.sh — Quick sanity check that AgentPulse is installed and healthy
# Usage: ./smoke-test.sh [--config /path/to/config.json]
#
# Exit codes: 0 = all OK, 1 = warnings, 2 = critical failures

set -euo pipefail

CONFIG_PATH="/etc/agentpulse/config.json"
if [[ "${1:-}" == "--config" ]]; then
  CONFIG_PATH="${2:?--config requires a path}"
elif [[ -n "${1:-}" ]]; then
  CONFIG_PATH="$1"
fi

RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[1;33m'; RST='\033[0m'
WARN_COUNT=0; FAIL_COUNT=0

ok()   { echo -e "${GRN}[PASS]${RST} $*"; }
fail() { echo -e "${RED}[FAIL]${RST} $*"; FAIL_COUNT=$((FAIL_COUNT + 1)); }
warn() { echo -e "${YEL}[WARN]${RST} $*"; WARN_COUNT=$((WARN_COUNT + 1)); }

# 1. Binary
if command -v agentpulse >/dev/null 2>&1; then
  ok "agentpulse binary"
else
  fail "agentpulse not in PATH"
fi

# 2. Version
if command -v agentpulse >/dev/null 2>&1; then
  VER="$(agentpulse --version 2>&1 || true)"
  if [[ "$VER" =~ agentpulse[[:space:]]+[0-9]+\.[0-9]+\.[0-9]+ ]]; then
    ok "version: $VER"
  else
    fail "unexpected version output: $VER"
  fi
fi

# 3. Python module
if python3 -c "import agentpulse" 2>/dev/null; then
  ok "agentpulse Python module"
else
  fail "agentpulse not importable"
fi

# 4. Config file
if [[ -f "$CONFIG_PATH" ]]; then
  ok "config: $CONFIG_PATH"
else
  fail "config not found: $CONFIG_PATH"
fi

# 5. Schema validation via agent CLI (stronger than JSON shape)
if command -v agentpulse >/dev/null 2>&1 && [[ -f "$CONFIG_PATH" ]]; then
  if agentpulse validate "$CONFIG_PATH" >/dev/null 2>&1; then
    ok "config schema valid"
  else
    fail "config failed agentpulse validate"
  fi
fi

# 6. Secure ownership/modes for credentials
if [[ -f /etc/agentpulse/agent.credential ]]; then
  MODE="$(stat -c '%a' /etc/agentpulse/agent.credential 2>/dev/null || stat -f '%OLp' /etc/agentpulse/agent.credential 2>/dev/null || echo '')"
  if [[ "$MODE" == "600" || "$MODE" == "0600" ]]; then
    ok "credential mode 0600"
  else
    fail "credential mode is ${MODE:-unknown}, expected 0600"
  fi
else
  warn "credential file not present (host may not be enrolled)"
fi

if [[ -f "$CONFIG_PATH" ]]; then
  MODE="$(stat -c '%a' "$CONFIG_PATH" 2>/dev/null || stat -f '%OLp' "$CONFIG_PATH" 2>/dev/null || echo '')"
  if [[ "$MODE" == "640" || "$MODE" == "0640" || "$MODE" == "600" || "$MODE" == "0600" ]]; then
    ok "config mode ${MODE}"
  else
    warn "config mode is ${MODE:-unknown}; prefer 0640 or 0600"
  fi
fi

# 7. Service running (Linux)
if command -v systemctl >/dev/null 2>&1; then
  if systemctl is-active --quiet agentpulse 2>/dev/null; then
    ok "systemd service active"
  else
    warn "systemd service not active (may be stopped or not yet enrolled)"
  fi
fi

# 8. Service running (macOS)
if command -v launchctl >/dev/null 2>&1; then
  if launchctl list 2>/dev/null | grep -q com.agentpulse; then
    ok "launchd service loaded"
  else
    warn "launchd service not loaded"
  fi
fi

# 9. Log / state directories
if [[ -d /var/log/agentpulse ]]; then
  ok "log dir exists"
else
  warn "log dir missing"
fi
if [[ -d /var/lib/agentpulse ]]; then
  ok "state dir exists"
else
  warn "state dir missing"
fi

# 10. Core modules
for pkg in agentpulse.decision_loop agentpulse.checks agentpulse.baseline; do
  if python3 -c "import $pkg" 2>/dev/null; then
    ok "module: $pkg"
  else
    fail "missing: $pkg"
  fi
done

# 11. Control-plane health when configured
if [[ -f "$CONFIG_PATH" ]]; then
  BASE_URL="$(python3 - <<PY
import json
from pathlib import Path
cfg = json.loads(Path("${CONFIG_PATH}").read_text())
cp = cfg.get("control_plane") or {}
if cp.get("enabled") and cp.get("base_url"):
    print(cp["base_url"].rstrip("/"))
PY
)"
  if [[ -n "${BASE_URL}" ]]; then
    if command -v curl >/dev/null 2>&1; then
      CODE="$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 10 "${BASE_URL}/health" || true)"
      if [[ "$CODE" == "200" ]]; then
        ok "control-plane health ${BASE_URL}/health"
      else
        warn "control-plane health not 200 (${CODE:-error}) at ${BASE_URL}/health"
      fi
    else
      warn "curl missing; skipped control-plane health check"
    fi
  fi
fi

echo ""
echo "Results: $FAIL_COUNT failures, $WARN_COUNT warnings"

if [[ $FAIL_COUNT -eq 0 ]]; then
  exit 0
fi
if [[ $FAIL_COUNT -le 2 ]]; then
  exit 1
fi
exit 2
