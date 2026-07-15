# AgentPulse Console

The single React customer console reads authenticated fleet state from the Cloudflare Worker. It does not host a Python service, mirror agent state in SQLite, execute approvals, or expose arbitrary commands.

## Local development

```bash
npm ci
npm run dev
npm run build
```

Set `VITE_API_BASE_URL` to the Worker origin when it is not `http://localhost:8787`.

The beta connection form stores the account credential only in the current browser tab. This is intentionally labeled as an interim arrangement; production release requires secure cookie-backed browser sessions.

## Active data path

```text
Browser → GET /v1/fleet → Cloudflare Worker → D1
```

The response includes tenant-scoped agents and their recent materialized incidents. The console is read-only in the consolidation branch.
