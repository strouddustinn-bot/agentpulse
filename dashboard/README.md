# AgentPulse Dashboard Service

A persistent, always-on web dashboard for AgentPulse. It runs **separately
from the agent** as a FastAPI + uvicorn service with SQLite persistence and
Server-Sent Events (SSE) push, serving a built React UI.

The in-agent stdlib dashboard (`agent/agentpulse/dashboard.py`) is **not
replaced** — it remains the zero-dependency fallback that needs nothing but
Python. This service supersedes it for humans who want history, charts, and
one-click approvals that survive agent restarts.

---

## Architecture

```
┌─────────────────────┐   read-only file watch    ┌──────────────────────────┐
│  AgentPulse agent   │──── state.json ──────────▶│  Dashboard service       │
│  (dependency-free,  │                            │  (FastAPI + uvicorn)     │
│   systemd unit)     │◀── python3 -m agentpulse ──│  · StateWatcher (1s)     │
└─────────────────────┘    approve|deny (argv      │  · MetricSampler (15s)   │
                           subprocess, never       │  · SQLite (WAL) mirror   │
                           a shell string)         │  · SSE fan-out           │
                                                   │  · serves web/dist       │
                                                   └───────────┬──────────────┘
                                                               │ SSE + JSON
                                                               ▼
                                                        Browser (React 19)
```

Components (`pulse_server/`):

| Module | Role |
|---|---|
| `main.py` | FastAPI app: routes, auth, SSE fan-out, static frontend, background loop |
| `ingest.py` | `StateWatcher` — tails the agent's `state.json` (mtime_ns+size change detection, never crashes on missing/partial files); `MetricSampler` — reads `/proc` + `shutil.disk_usage` for chartable series |
| `db.py` | SQLite (stdlib `sqlite3`, WAL, no ORM). Tables: `history` (unbounded mirror of agent history — the agent caps at 200), `metric_samples`, `events` |
| `actions.py` | approve/deny via the agent CLI subprocess. Validates pending ids (`^[0-9a-f]{6,12}$`), fails closed, always argv lists |

### Safety invariant (the whole point)

**The dashboard never writes `state.json` — ever.** Reads are a passive file
watch. The ONLY write path is shelling out to
`python3 -m agentpulse approve|deny <config> <id>`, so every action flows
through the agent's own tested decision loop, safety gate, and
verify-or-escalate cycle. The dashboard is an additive control layer; the
agent's behavior, policy gate, and state format are untouched.

---

## Local quickstart

Prereqs: Python 3.10+, Node 18+ (frontend build only).

### 1. Backend setup

```bash
cd ~/Projects/agentpulse/dashboard
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. Frontend build (served by the backend from `web/dist`)

```bash
cd web
npm install
npm run build          # tsc -b + vite build → web/dist/
cd ..
```

### 3. Generate agent state and run

```bash
# The local agent config writes state to /tmp/agentpulse/state.json:
grep state_file ../agent/agentpulse.config.local.json

export PULSE_STATE_FILE=/tmp/agentpulse/state.json
export PULSE_AGENT_DIR=$(realpath ../agent)
export PULSE_AGENT_CONFIG=$(realpath ../agent/agentpulse.config.local.json)
export PULSE_TOKEN=devtoken          # any string; required for approve/deny

# produce a fresh state snapshot:
(cd ../agent && python3 -m agentpulse run-once agentpulse.config.local.json)

.venv/bin/uvicorn pulse_server.main:app --host 127.0.0.1 --port 8790
```

Open <http://localhost:8790>. Smoke checks:

```bash
curl -s localhost:8790/api/health                       # {"ok":true,...}
curl -s localhost:8790/api/state | head -c 200
curl -s -N localhost:8790/api/events | head -2          # data: {"type":"state",...}
curl -s -X POST localhost:8790/api/pending/abc123/approve
# {"detail":"unauthorized"}  ← 401 without token is REQUIRED behavior
```

For frontend development with hot reload, run `npm run dev` in `web/`
(<http://localhost:5173>, proxied to the backend) instead of building.

### Keep it running without root: tmux

```bash
tmux new-session -d -s pulse-dash \
  'cd ~/Projects/agentpulse/dashboard && \
   PULSE_STATE_FILE=/tmp/agentpulse/state.json \
   PULSE_AGENT_DIR=$HOME/Projects/agentpulse/agent \
   PULSE_AGENT_CONFIG=$HOME/Projects/agentpulse/agent/agentpulse.config.local.json \
   PULSE_TOKEN=devtoken \
   .venv/bin/uvicorn pulse_server.main:app --host 127.0.0.1 --port 8790'
```

This survives your terminal closing, but not a reboot — for that, use the
systemd unit below.

---

## Configuration (environment variables)

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `PULSE_STATE_FILE` | yes | `/var/lib/agentpulse/state.json` | Path to the agent's `state.json` (read-only watch) |
| `PULSE_AGENT_DIR` | for actions | `""` | Path to the `agent/` directory; approve/deny run `python3 -m agentpulse` from here |
| `PULSE_AGENT_CONFIG` | for actions | `""` | Agent config JSON passed to the CLI on approve/deny |
| `PULSE_DB` | no | `pulse.db` (cwd) | SQLite database path (WAL mode) |
| `PULSE_TOKEN` | for local actions | `""` | Bearer token for mutating approve/deny endpoints. **Empty = all POSTs rejected (fail closed)** |
| `PULSE_INGEST_TOKEN` | for admin ingest | `""` | Administrative bearer token for `POST /fleet/heartbeat`; paid customers use their issued AgentPulse API key |
| `PULSE_READ_USER` | no | `agentpulse` | HTTP Basic username when read protection is enabled |
| `PULSE_READ_PASSWORD` | hosted | `""` | Enables HTTP Basic protection for dashboard/API reads; health remains public for Fly checks |
| `STRIPE_SECRET_KEY` | for billing | `""` | Stripe restricted/secret key; enables verified checkout, subscription sync, and portal sessions |
| `STRIPE_WEBHOOK_SECRET` | for billing | `""` | Signing secret for `/api/stripe/webhook`; webhook events fail closed without it |
| `STRIPE_PRICE_STARTER` | recommended | `""` | Exact recurring Stripe Price ID mapped to Starter (1 server) |
| `STRIPE_PRICE_PRO` | recommended | `""` | Exact recurring Stripe Price ID mapped to Pro (5 servers) |
| `STRIPE_PRICE_BUSINESS` | recommended | `""` | Exact recurring Stripe Price ID mapped to Business (1000-server beta ceiling) |
| `PUBLIC_BASE_URL` | hosted | `http://127.0.0.1:8790` | Public HTTPS origin used for onboarding, portal returns, and generated federation config |
| `PULSE_DISK_PATHS` | no | `/` | Comma-separated mount paths charted for disk usage |
| `PULSE_WEB_DIST` | no | `../web/dist` (relative to `pulse_server/`) | Built frontend directory served at `/` |

---

## API reference

Base URL: `http://127.0.0.1:8790`. Read endpoints are unauthenticated (the
service binds localhost); mutating endpoints require the bearer token.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/health` | – | `{"ok": true, "state_file": ..., "last_run": ...}` |
| GET | `/api/state` | – | Live snapshot: `{"last_run", "pending": [...], "blocked_ips": [...], "fleet": {...}}` |
| GET | `/api/history?limit=100&before_ts=` | – | SQLite-backed history, newest first. `limit` capped at 500; pass the oldest row's `ts` as `before_ts` to paginate |
| GET | `/api/metrics?hours=24` | – | Time series per metric: `{"mem": [[ts, v], ...], "load1": [...], "disk:/": [...]}` |
| GET | `/api/events` | – | SSE stream (see payload shapes below) |
| POST | `/api/pending/{id}/approve` | Bearer | Approve a pending action via the agent CLI. `409` + CLI output on failure |
| POST | `/api/pending/{id}/deny` | Bearer | Deny a pending action via the agent CLI. `409` + CLI output on failure |
| POST | `/api/stripe/webhook` | Stripe signature | Idempotently sync checkout, subscription, renewal, cancellation, and failed-payment events |
| POST | `/api/onboarding/claim` | Checkout session + email | Verify a completed Stripe Checkout and issue a one-time AgentPulse API key |
| GET | `/onboarding?session_id=...` | Public | Post-checkout activation page; Stripe Payment Links redirect here |
| POST | `/api/billing/portal` | AgentPulse API key | Create a short-lived Stripe Customer Portal session |
| GET | `/billing` | Public | Customer-facing form that exchanges an AgentPulse API key for a portal session |
| GET | `/{path}` | – | SPA static serving from `PULSE_WEB_DIST` (falls back to `index.html`) |

Auth header for mutations:

```bash
curl -X POST -H "Authorization: Bearer $PULSE_TOKEN" \
  localhost:8790/api/pending/<id>/approve
```

`401 unauthorized` when the token is missing/wrong **or when `PULSE_TOKEN`
is unset on the server** — actions fail closed by default.

### SSE payload shapes (`GET /api/events`)

Each event is a single `data:` line of JSON. On connect, the stream first
sends one `state` and one `history` event so a fresh tab renders instantly;
a `: keepalive` comment goes out every second when idle.

```jsonc
// agent state changed (also the initial snapshot)
{"type": "state", "data": {"last_run": 1752170000.1, "pending": [], "blocked_ips": [], "fleet": {}, "new_history": 2}}

// new history rows were mirrored (latest 50, newest first)
{"type": "history", "data": [{"ts": 1752170000.1, "action": "disk_cleanup", "target": "/var/log/app", "outcome": "ok", "...": "..."}]}

// one metric sample tick (every ~15s)
{"type": "metrics", "data": {"ts": 1752170015.2, "values": {"mem": 41.3, "load1": 0.42, "disk:/": 63.1}}}
```

---

## Security model

- **Bind:** `127.0.0.1` only. Never expose port 8790 directly.
- **Reads:** localhost installs may leave reads open. Any public deployment must
  set `PULSE_READ_PASSWORD`, which protects the UI, API, and SSE stream with
  HTTP Basic auth while leaving `/api/health` available to platform checks.
- **Writes tokened:** local approve/deny endpoints require `PULSE_TOKEN`;
  hosted heartbeat ingest separately requires `PULSE_INGEST_TOKEN`. Both fail
  closed when their token is absent.
- **Remote access:** set `PULSE_READ_PASSWORD` before exposing the service.
  TLS must terminate at Fly or a reverse proxy; never publish plaintext HTTP.
- **Token storage (production):** `PULSE_TOKEN` goes in
  `/etc/agentpulse/dashboard.env` with mode `600` — never in the unit file
  (unit files are world-readable).
- **Injection surface:** pending ids are regex-validated and the agent CLI
  is invoked as an argv list, never a shell string.

---

## Production install (systemd)

> **FLAG TO OPERATOR:** everything in this section runs as root. The repo
> only ships the unit file (`agent/systemd/agentpulse-dashboard.service`);
> installing/enabling it is a deliberate operator action, not something the
> implementing agent performs.

Layout assumed by the unit: repo at `/opt/agentpulse`, venv at
`/opt/agentpulse/dashboard/.venv`, writable state dir `/var/lib/agentpulse`,
agent config `/etc/agentpulse/config.json`.

```bash
# 1. Dedicated user (no shell, no home login)
sudo useradd --system --home-dir /var/lib/agentpulse --shell /usr/sbin/nologin agentpulse || true

# 2. Code + venv + frontend build
sudo mkdir -p /opt/agentpulse
sudo rsync -a --exclude web/node_modules ~/Projects/agentpulse/ /opt/agentpulse/
cd /opt/agentpulse/dashboard
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
# build the frontend on a machine with Node and rsync web/dist over, or:
(cd web && npm install && npm run build)

# 3. Writable state dir (agent state + dashboard DB live here)
sudo mkdir -p /var/lib/agentpulse
sudo chown agentpulse:agentpulse /var/lib/agentpulse
sudo chmod 750 /var/lib/agentpulse

# 4. Verify the agentpulse user can read what it needs
sudo -u agentpulse test -r /etc/agentpulse/config.json && echo config-ok
sudo -u agentpulse test -r /var/lib/agentpulse/state.json && echo state-ok
sudo -u agentpulse /opt/agentpulse/dashboard/.venv/bin/python -c "import fastapi; print('venv-ok')"

# 5. Token env file — mode 600, never in the unit
printf 'PULSE_TOKEN=%s\n' "$(openssl rand -hex 24)" | sudo tee /etc/agentpulse/dashboard.env >/dev/null
sudo chown root:agentpulse /etc/agentpulse/dashboard.env
sudo chmod 600 /etc/agentpulse/dashboard.env

# 6. Install + enable the unit
sudo cp /opt/agentpulse/agent/systemd/agentpulse-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now agentpulse-dashboard
systemctl status agentpulse-dashboard
curl -s localhost:8790/api/health
```

Notes:

- The unit is hardened (`ProtectSystem=strict`, `ProtectHome=true`,
  `NoNewPrivileges`, `PrivateTmp`, `UMask=0077`); the only writable path is
  `/var/lib/agentpulse` (dashboard DB + the state file the agent CLI
  rewrites on approve/deny). `/opt/agentpulse` and `/etc/agentpulse` are
  read-only to the service.
- If the agent runs as root and its state/config aren't readable by the
  `agentpulse` user, fix group ownership/permissions on those files rather
  than weakening the unit.
- Sanity-check the unit before install:
  `systemd-analyze verify agent/systemd/agentpulse-dashboard.service`
  (a missing `/opt/.../uvicorn` warning is expected until step 2 is done).

---

## Tests & build

```bash
# backend unit tests (stdlib unittest — repo convention, no pytest)
cd dashboard && .venv/bin/python -m unittest tests.test_server -v

# frontend type-check + production build
cd dashboard/web && npm run build

# agent suite must stay green (dashboard changes must never break it)
cd agent && python3 tools/run_tests.py
```

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `/api/health` returns `"last_run": null`, UI empty | Agent hasn't written state yet, or `PULSE_STATE_FILE` points to the wrong path. Run `python3 -m agentpulse run-once <config>` and check `grep state_file <config>` |
| UI shows stale data, no live updates | SSE stream not connected — check the browser console for `/api/events` errors; a proxy in front must not buffer SSE (nginx: `proxy_buffering off`, the service already sends `X-Accel-Buffering: no`) |
| Approve/deny returns `401` | Missing/incorrect `Authorization: Bearer` header, or `PULSE_TOKEN` unset on the server (fail-closed) |
| Approve/deny returns `409` | The agent CLI rejected it — the detail field carries the CLI output (unknown/expired id, gate refusal, missing `PULSE_AGENT_DIR`/`PULSE_AGENT_CONFIG`) |
| `invalid pending id format` | Ids must match `[0-9a-f]{6,12}`; anything else is rejected before any subprocess runs |
| `database is locked` / DB errors | Check `PULSE_DB` parent dir is writable by the service user; WAL needs write access to the DB's directory (`-wal`/`-shm` files) |
| Blank page at `/` | Frontend not built or `PULSE_WEB_DIST` wrong — run `npm run build` in `web/` and confirm `web/dist/index.html` exists |
| systemd: service crash-loops | `journalctl -u agentpulse-dashboard -e`. Usual suspects: venv missing at `/opt/agentpulse/dashboard/.venv`, `/var/lib/agentpulse` not writable by `agentpulse`, or a sandbox path missing |
| Ingest errors in the `events` table | Partial/invalid `state.json` reads are logged and retried next poll — transient ones during agent writes are normal |

---

## Fly.io hosted backend

The checked-in `Dockerfile` builds the React UI and serves it from FastAPI.
`fly.toml` deploys one `yyz` Machine with a persistent `/data` volume. SQLite
must remain single-writer, so do not scale this app above one Machine without
moving persistence to Postgres.

Hosted data arrives through the existing AgentPulse federation spoke protocol:

- `POST /fleet/heartbeat` requires `Authorization: Bearer <PULSE_INGEST_TOKEN>`.
- Heartbeats are upserted by `agent_id` into SQLite and emitted over SSE.
- Dashboard/API reads require HTTP Basic auth when `PULSE_READ_PASSWORD` is set.
- `/api/health` stays unauthenticated for Fly health checks.
- Remote approve/deny is deliberately disabled: the Fly container has no safe
  access to the monitored host's local agent CLI. Remediation remains local.

Deploy from the repository root:

```bash
flyctl apps create agentpulse-stroud --org personal
flyctl volumes create agentpulse_data --app agentpulse-stroud --region yyz --size 1
flyctl secrets set --app agentpulse-stroud \
  PULSE_INGEST_TOKEN='<strong-random-token>' \
  PULSE_READ_PASSWORD='<different-strong-random-password>'
flyctl deploy --app agentpulse-stroud --remote-only
curl -fsS https://agentpulse-stroud.fly.dev/api/health
```

Configure each monitored AgentPulse host as a federation spoke:

```json
"federation": {
  "enabled": true,
  "mode": "spoke",
  "hub_url": "https://agentpulse-stroud.fly.dev",
  "secret": "<same value as PULSE_INGEST_TOKEN>",
  "port": 8766,
  "bind": "127.0.0.1",
  "push_interval_seconds": 60
}
```

Then run one agent cycle and verify the host appears under `fleet`:

```bash
python3 -m agentpulse run-once agentpulse.config.local.json
curl -u agentpulse:'<read-password>' \
  https://agentpulse-stroud.fly.dev/api/state
```

Credential values belong in a mode-600 local config or secret manager, never
in committed JSON. Fly volume snapshots are not a backup strategy; export or
snapshot `/data/pulse.db` before destructive changes.
