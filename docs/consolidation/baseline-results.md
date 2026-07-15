# Pre-consolidation Baseline Results

Captured: 2026-07-15 17:54 EDT
Base: `origin/productization/cloudflare-paid-pilot` at `f2593dbd6201949866c4a35587e4666864c813ac`
Candidate: `agent/consolidate-agentpulse-v2`

## Agent

Command:

```text
cd agent && python3 tools/run_tests.py
```

Result: exit 0; `PASSED: 170 FAILED: 0`.

## Control plane

Commands:

```text
cd control-plane && npm test
cd control-plane && npm run typecheck
cd control-plane && npm run types:check
```

Result: exit 0; Vitest reported 1 file and 11 tests passed. TypeScript and generated Worker binding checks passed.

## Retained dashboard candidate: `dashboard/frontend`

Command:

```text
cd dashboard/frontend && npm run build
```

Result: exit 0; production build passed. Output was 252.97 kB JavaScript / 78.95 kB gzip and 14.31 kB CSS / 3.71 kB gzip.

## Superseded dashboard candidate: `dashboard/web`

Commands:

```text
cd dashboard/web && npm test -- --run
cd dashboard/web && npm run build
```

Result: the test command exited 1 because `package.json` has no `test` script. The build then passed with 556.15 kB JavaScript / 166.68 kB gzip and emitted a Vite chunk-size warning. This candidate is not selected for the consolidated product.

## Dependency notes

- `control-plane/npm ci`: passed; 0 reported vulnerabilities.
- `dashboard/frontend/npm ci`: passed; npm reported 2 vulnerabilities (1 moderate, 1 high) and a deprecated Recharts 2.x warning.
- `dashboard/web/npm ci`: passed; 0 reported vulnerabilities.
- Python dependencies were installed into the candidate-local `.venv`, not system Python.

## Interpretation

These are current executable baseline results from this worktree. They supersede
any test totals in imported reports. The consolidation must preserve the agent
and Worker passing baselines, replace the dashboard/frontend API assumptions, and
remove the dashboard/web implementation whose test command is absent.
