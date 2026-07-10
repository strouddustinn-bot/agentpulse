# AgentPulse Dashboard Service

Separate, stunning, persistent dashboard for AgentPulse.

## Structure
- `backend/` — FastAPI ingestion service
- `realtime/` — Cloudflare Durable Object (WebSocket + state)
- `frontend/` — React 19 + shadcn/ui (stunning UI)
- `shared/` — TypeScript types

## Next Steps
1. Run backend: `cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload`
2. Deploy realtime: `cd realtime && wrangler deploy`
3. Run frontend: `cd frontend && npm install && npm run dev`

This is the initial skeleton. Ready for the beautiful React frontend and full integration.