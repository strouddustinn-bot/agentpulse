# AgentPulse Backend

FastAPI backend for AgentPulse agent check-ins, fleet status, and license verification.

## Local setup

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
agentpulse-backend init-db
TOKEN=$(agentpulse-backend create-api-key --org default --label local-dev)
uvicorn agentpulse_backend.app:app --reload
```

Configure an agent:

```json
"checkin": {
  "endpoint_url": "http://localhost:8000/api/agent/checkin",
  "auth_token": "paste-token-here",
  "timeout_seconds": 5
}
```

The agent daemon sends check-ins automatically after each successful cycle when `endpoint_url` is set.

## API

- `GET /health` — public health check
- `POST /api/agent/checkin` — bearer-token protected agent check-in
- `GET /api/agents` — bearer-token protected fleet list
- `GET /api/agents/{agent_id}/checkins` — bearer-token protected recent check-ins
- `POST /api/license/verify` — verify a license key

## Docker

From the repository root:

```bash
docker build -f backend/Dockerfile -t agentpulse-backend:dev .
docker run --rm -p 8000:8000 -v agentpulse-backend-data:/data agentpulse-backend:dev
```
