---
layout: default
title: AgentPulse API
permalink: /api/
---

# AgentPulse API

AgentPulse's control-plane API contract is published for integration review and pre-pilot development.

- **Machine-readable contract:** [OpenAPI 3.1 YAML on GitHub](https://github.com/strouddustinn-bot/agentpulse/blob/master/packages/contracts/openapi.yaml)
- **Staging target:** `https://staging-api.agentpulse.ca` (health endpoint only; Phase 3A operations are not deployed)
- **Deployed staging health:** `https://staging-api.agentpulse.ca/health`

The production API is not deployed. The `https://api.agentpulse.ca` server entry in the OpenAPI document records the intended production address, not current availability. Operations marked `x-implementation-status: contract-only` describe the approved Phase 3A interface but are not available on staging or production until Phase 3B handlers pass verification. Do not send production credentials or customer data to staging.

Authentication currently uses scoped AgentPulse bearer credentials for controlled enrollment and agent communication. AgentPulse does not yet provide OAuth/OIDC authorization-server metadata, automated third-party registration, an MCP server, or WebMCP tools.
