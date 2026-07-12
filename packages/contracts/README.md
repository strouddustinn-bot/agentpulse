# AgentPulse Contracts

Shared JSON schemas and OpenAPI specification for the AgentPulse platform.
These contracts define the communication protocol between the agent, control-plane API,
and dashboard — ensuring type-level agreement across all components.

## Schemas

| File | Description |
|------|-------------|
| `schemas/enrollment.schema.json` | Agent enrollment request/response |
| `schemas/checkin.schema.json` | Periodic check-in payload |
| `schemas/check-result.schema.json` | Individual check execution result |
| `schemas/incident.schema.json` | Opened/updated incident record |
| `schemas/remediation-request.schema.json` | Control-plane → agent remediation dispatch |
| `schemas/remediation-result.schema.json` | Agent → control-plane remediation outcome |
| `schemas/policy.schema.json` | Policy definition served to agents |
| `schemas/audit-event.schema.json` | Audit event emitted by all components |
| `schemas/error.schema.json` | Standardized error response |
| `schemas/agent-status.schema.json` | Agent inventory status payload |

## Versioning

Contracts follow [SemVer](https://semver.org/). A breaking change bumps the major
version and must be accompanied by a migration path. Agent and backend negotiate
the highest mutually-supported version via the `X-Contract-Version` header.

Current stable: **1.0.0**

## Validation

Schemas are draft-07 JSON Schema. Validate locally:

```bash
# Python
python3 -c "import json, jsonschema; jsonschema.validate(data, json.load(open('schemas/checkin.schema.json')))"

# Node.js
npx ajv validate -s schemas/checkin.schema.json -d data.json

# CLI
check-jsonschema --builtin-schema draft2020-12 schemas/*.schema.json
```

## Change Process

1. Draft new version alongside existing version.
2. Run `contract-backwards-test.py` against the old and new schemas.
3. Update `schemas/version.json` with the new stable version.
4. Update the OpenAPI spec.
5. Announce in CHANGELELOG with the contract version bump.
