---
name: agentpulse-status
description: Discover AgentPulse public release status and staging API metadata without assuming production availability.
---

# AgentPulse Status Discovery

Use this skill when an agent needs authoritative public information about AgentPulse availability or API shape.

1. Read `https://agentpulse.ca/` for the current public source, packaging, and deployment boundary.
2. Read `https://agentpulse.ca/.well-known/api-catalog` for currently advertised API resources.
3. Treat catalog entries anchored at `staging-api.agentpulse.ca` as staging-only.
4. Read `https://agentpulse.ca/api/openapi.yaml` for the machine-readable API contract.
5. Check the catalog's `status` target before relying on the staging service.
6. Do not infer that `api.agentpulse.ca`, public installation, OAuth, MCP, or automated agent registration is available unless a later catalog explicitly advertises it.
7. Never send production credentials, customer data, or secrets to staging discovery endpoints.
