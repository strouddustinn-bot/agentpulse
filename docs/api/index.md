---
layout: default
title: AgentPulse API
permalink: /api/
---

# AgentPulse API

AgentPulse's control-plane API contract is published for integration review and pre-pilot development.

- **Machine-readable contract:** [OpenAPI 3.1 YAML on GitHub](https://github.com/strouddustinn-bot/agentpulse/blob/master/packages/contracts/openapi.yaml)
- **Staging target:** `https://staging-api.agentpulse.ca` (health is live; migrations `0001` through `0003` are applied; the exact Phase 3D Worker deploy and lifecycle proof remain pending)
- **Deployed staging health:** `https://staging-api.agentpulse.ca/health`

The production API is not deployed. The `https://api.agentpulse.ca` server entry in the OpenAPI document records the intended production address, not current availability. Billing checkout, claim, browser session, account, and portal routes are implemented and locally verified in source (`x-implementation-status: implemented`) but are not Phase 3D-proven on staging or available in production until the exact Worker candidate is deployed and Stripe test bindings and staging lifecycle proof complete. Do not send production credentials or customer data to staging.

Authentication currently uses scoped AgentPulse bearer credentials for controlled enrollment and agent communication, plus an implemented browser session cookie path for account lifecycle once claim is complete. AgentPulse does not yet provide OAuth/OIDC authorization-server metadata, automated third-party registration, an MCP server, or WebMCP tools.
