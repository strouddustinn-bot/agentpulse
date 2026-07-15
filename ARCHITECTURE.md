# AgentPulse Architecture

## Product boundary

AgentPulse is a local-first server-remediation platform, not a generic observability system, remote-shell service, or unsupervised LLM infrastructure agent.

```text
Host agent → authenticated Worker/D1 control plane → React console
```

## Components

### `agent/`

The dependency-light Python runtime owns host observation, bounded reasoning, simulation, local policy ceilings, allowlisted remediation, post-action verification, evidence, local state, offline operation, and outbound replay. It remains useful when the network or control plane is unavailable.

### `control-plane/`

The Cloudflare Worker is the only hosted authority. D1 stores tenant metadata, subscription state, enrollment tokens, agent identities, heartbeats, materialized incidents, policies, and audit-relevant evidence. It authenticates requests and narrows policy intent. It does not run shell commands, dispatch arbitrary code, or provide remote execution.

Surviving API routes are documented in `packages/contracts/openapi.yaml`:

- `GET /health`
- `POST /v1/enrollment-tokens`
- `POST /v1/agents/enroll`
- `POST /v1/agents/heartbeat`
- `GET /v1/agents/policy`
- `GET /v1/fleet`
- `POST /v1/stripe/webhook`

Heartbeats are bounded and idempotent. Incident fingerprints are upserted per tenant and agent. Fleet reads are tenant-scoped and include recent incidents.

### `dashboard/`

One React console presents fleet and incident state from `GET /v1/fleet`. It is read-only: no approval endpoint, arbitrary command path, local state mutation, or second backend exists in the dashboard. The current beta connection form uses a tab-scoped credential and explicitly marks secure browser sessions as a production prerequisite.

### `packages/contracts/`

OpenAPI and JSON Schema are the shared contract source. Fixtures and `scripts/validate-contracts.py` validate the active Worker surface, local references, schemas, and representative payloads. Do not add an endpoint to a client or documentation page without adding it to the contract and Worker tests.

### `docs/`

The public website, product documentation, installation guidance, privacy/terms pages, and comparison content live here. The site is not a second dashboard or API implementation.

## Safety invariants

1. Cloud policy may reduce local authority but never increase it.
2. Unknown action names and malformed payloads fail closed.
3. The cloud cannot execute arbitrary host commands.
4. The agent remains functional during control-plane outages.
5. Remediation follows `Observe → Reason → Simulate → Gate → Act → Verify → Record or Escalate`.
6. Verification failure escalates once and never begins an autonomous repair loop.
7. Credentials and sensitive values are stored as hashes or protected local files and never emitted into logs, fixtures, or reports.
8. Tenant identifiers are enforced on every hosted read and write.

## Deliberate removals

The generic FastAPI backend, Python dashboard service, duplicate React dashboard, realtime Worker, Fly configuration, generic Docker production stack, load-test scaffolding, and premature Prometheus/Grafana stack were retired. They created competing authorities and were not required by the paid-pilot contract.

## Future expansion

Secure browser sessions, complete checkout/account claim, billing portal, richer audit/event routes, and staging lifecycle automation are separate release gates. They must extend this boundary rather than reintroduce a second backend or remote-shell capability.
