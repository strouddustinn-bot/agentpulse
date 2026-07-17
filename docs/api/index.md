---
layout: default
title: AgentPulse API
permalink: /api/
---

# AgentPulse API

AgentPulse's control-plane API contract is published for integration review and controlled-beta development.

- **Machine-readable contract:** [OpenAPI 3.1 YAML](openapi.yaml)
- **Currently advertised service:** `https://staging-api.agentpulse.ca`
- **Staging health:** `https://staging-api.agentpulse.ca/health`

The production API is not deployed. The `https://api.agentpulse.ca` server entry in the OpenAPI document records the intended production address, not current availability. Do not send production credentials or customer data to staging.

Authentication currently uses scoped AgentPulse bearer credentials for controlled enrollment and agent communication. AgentPulse does not yet provide OAuth/OIDC authorization-server metadata, automated third-party registration, an MCP server, or WebMCP tools.
