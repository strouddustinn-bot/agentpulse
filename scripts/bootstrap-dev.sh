#!/usr/bin/env bash
# Bootstrap the local AgentPulse development environment.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

command -v python3 >/dev/null || { echo 'python3 is required' >&2; exit 1; }
command -v node >/dev/null || { echo 'Node.js 22+ is required' >&2; exit 1; }

VENV="${AGENTPULSE_VENV:-$ROOT/.venv}"
python3 -m venv "$VENV"
# shellcheck source=/dev/null
source "$VENV/bin/activate"
python -m pip install --upgrade pip >/dev/null
python -m pip install PyYAML jsonschema ruff >/dev/null

python agent/tools/run_tests.py
python scripts/validate-contracts.py
(cd control-plane && npm ci && npm test && npm run typecheck && npm run types:check)
(cd dashboard && npm ci && npm run build)

printf '\nAgentPulse bootstrap complete.\n'
printf 'Activate Python: source %s/bin/activate\n' "$VENV"
printf 'Worker dev:      cd control-plane && npm run dev\n'
printf 'Dashboard dev:   cd dashboard && npm run dev\n'
printf 'Canonical API:   https://api.agentpulse.ca\n'
printf 'Canonical app:   https://app.agentpulse.ca\n'
