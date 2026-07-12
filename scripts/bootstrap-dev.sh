#!/usr/bin/env bash
# bootstrap-dev.sh — Set up a local development environment for AgentPulse
# Usage: ./bootstrap-dev.sh [--skip-frontend] [--skip-backend]
#
# Prerequisites: Python 3.10+, Node.js 22+, Docker (for backend dev)
set -euo pipefail

SKIP_FRONTEND=false
SKIP_BACKEND=false
SKIP_DOCKER=false

# ─── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[1;33m'; BLU='\033[0;34m'; RST='\033[0m'
info()    { echo -e "${BLU}[INFO]${RST}  $*"; }
success() { echo -e "${GRN}[OK]${RST}    $*"; }
warn()    { echo -e "${YEL}[WARN]${RST}  $*"; }
die()     { echo -e "${RED}[ERR]${RST}   $*"; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-frontend) SKIP_FRONTEND=true; shift;;
    --skip-backend)  SKIP_BACKEND=true; shift;;
    --skip-docker)   SKIP_DOCKER=true; shift;;
    *) die "Unknown option: $1";;
  esac
done

echo "═══════════════════════════════════════"
echo " AgentPulse Development Bootstrap"
echo "═══════════════════════════════════════"

# ─── Python virtualenv ────────────────────────────────────────────────────────
setup_python() {
  info "Setting up Python environment..."
  local venv="${HOME}/.venv/agentpulse"
  python3 -m venv "$venv"
  # shellcheck source=/dev/null
  source "${venv}/bin/activate"
  pip install --quiet -q pip --upgrade
  pip install --quiet -q -r agent/requirements.txt 2>/dev/null || true
  pip install --quiet -q -r backend/requirements.txt 2>/dev/null || true
  pip install --quiet -q pytest pytest-asyncio httpx
  success "Python environment ready at $venv"
  echo "  Activate with: source $venv/bin/activate"
}

# ─── Agent ────────────────────────────────────────────────────────────────────
setup_agent() {
  info "Setting up agent..."
  # Validate config example
  python3 -c "import json; json.load(open('agent/agentpulse.config.example.json'))" || \
    die "Config example is not valid JSON"
  python3 agent/tools/run_tests.py > /dev/null 2>&1 && \
    success "Agent tests pass" || warn "Agent tests had failures"
}

# ─── Backend ─────────────────────────────────────────────────────────────────
setup_backend() {
  [[ "$SKIP_BACKEND" == "true" ]] && info "Skipping backend" && return
  info "Setting up backend..."

  if [[ "$SKIP_DOCKER" != "true" ]] && command -v docker >/dev/null 2>&1; then
    info "Starting backend services via Docker..."
    docker compose -f docker-compose.dev.yml up -d backend prometheus 2>/dev/null || \
      warn "Docker not available, skipping backend"
  fi

  python3 -c "import fastapi, uvicorn, pydantic" 2>/dev/null && \
    success "Backend dependencies available" || warn "Backend deps not installed"
}

# ─── Frontend ────────────────────────────────────────────────────────────────
setup_frontend() {
  [[ "$SKIP_FRONTEND" == "true" ]] && info "Skipping frontend" && return
  info "Setting up frontend..."
  if [[ -d dashboard/web ]]; then
    (cd dashboard/web && npm install --silent 2>/dev/null && \
      npm run build 2>/dev/null && success "Frontend builds OK") || \
      warn "Frontend setup had issues"
  fi
}

# ─── Git hooks ────────────────────────────────────────────────────────────────
setup_git_hooks() {
  info "Installing pre-commit hooks..."
  if command -v pre-commit >/dev/null 2>&1; then
    pre-commit install --allow-missing-config 2>/dev/null || true
    success "Pre-commit hooks installed"
  else
    warn "pre-commit not installed (pip install pre-commit)"
  fi
}

# ─── .env.local ───────────────────────────────────────────────────────────────
setup_env() {
  local envfile=".env.local"
  if [[ ! -f "$envfile" ]]; then
    info "Creating $envfile from example..."
    cp .env.example "$envfile"
    success "Created $envfile — fill in real values before starting services"
  else
    success "$envfile already exists"
  fi
}

# ─── Run ─────────────────────────────────────────────────────────────────────
setup_python
setup_agent
setup_backend
setup_frontend
setup_git_hooks
setup_env

echo ""
echo "═══════════════════════════════════════"
success "Bootstrap complete!"
echo ""
echo "  Agent tests:    python3 agent/tools/run_tests.py"
echo "  Backend:        docker compose -f docker-compose.dev.yml up backend"
echo "  Frontend dev:   cd dashboard/web && npm run dev"
echo "  Full stack:     docker compose -f docker-compose.yml -f docker-compose.dev.yml up"
echo ""
echo "  See ARCHITECTURE.md for the full system design."
echo "═══════════════════════════════════════"
