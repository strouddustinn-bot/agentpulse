# AgentPulse

AgentPulse is a local-first server-remediation platform under active development. A dependency-light agent observes a host, proposes bounded fixes, executes only policy-approved actions, verifies the result, and can synchronize evidence to the Worker/D1 control plane. Fleet-console source exists, but public console deployment remains a release gate.

Target production surfaces:

- Website and documentation: https://agentpulse.ca
- Console: https://app.agentpulse.ca
- API: https://api.agentpulse.ca

As of 2026-07-17, those production hostnames are not deployed and do not
resolve. The staging control-plane health endpoint is live at
`https://staging-api.agentpulse.ca/health`; staging website and console
deployment remain release gates. See `STATUS.md` for the evidence-backed
readiness boundary rather than treating these target URLs as availability
claims.

## Repository map

```text
agent/              Dependency-light local observer and remediation engine
control-plane/      Cloudflare Worker + D1 tenant control plane
dashboard/          One routed React customer console
packages/contracts/ OpenAPI, JSON Schema, and fixtures
configs/            Agent configuration schema and safe examples
scripts/            Installation, bootstrap, validation, and smoke scripts
docs/               Public website and operator documentation
```

The product boundary is intentionally narrow:

```text
Observe → Reason → Simulate → Gate → Act → Verify → Record or Escalate
```

The cloud can narrow a host's policy but cannot increase the immutable local authority ceiling. Unknown actions fail closed. The cloud never executes arbitrary host commands or provides a remote shell. If the control plane is unavailable, the local agent continues operating and spools outbound evidence for later delivery.

## Local development

Prerequisites: Python 3.10+ and Node.js 22+.

```bash
./scripts/bootstrap-dev.sh
source .venv/bin/activate

# Independent gates
cd agent && python3 tools/run_tests.py
cd ../ && python3 scripts/validate-contracts.py
cd control-plane && npm test && npm run typecheck && npm run types:check
cd ../dashboard && npm run build
```

Run the Worker and console locally:

```bash
cd control-plane && npm run dev
cd dashboard && npm run dev
```

The dashboard is read-only in this consolidation. It displays authenticated fleet and incident state; it does not execute host commands. Its temporary beta credential is kept in `sessionStorage` only. Secure browser sessions remain a release requirement.

## Agent safety

The local agent is the authority for host actions. Every remediation must be simulated, policy-gated, allowlisted, verified, and recorded. Failed verification escalates once; it never starts an autonomous retry loop. Read `agent/README.md`, `SECURITY.md`, and `ARCHITECTURE.md` before changing remediation behavior.

## Verification and archives

Current verification receipts and explicit production release gates are summarized in `STATUS.md`. Historical source retention follows `ARCHIVES.md`; operational storage details remain private, and deletion is blocked until the owner approves the retention gate.

```bash
make agent-test
make contracts-validate
make cp-test
make cp-typecheck
make dashboard-build
```

## License

Apache-2.0. See `LICENSE`.
