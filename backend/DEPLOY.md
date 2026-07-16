# Deploying the AgentPulse backend on Fly.io

The backend runs as a **single Fly machine** with SQLite on a persistent
volume. This is deliberate: one cheap container is all the paid beta needs,
and the schema already carries `org_id` everywhere so it can migrate to
Postgres later without changing agent payloads.

> **Hard constraint:** SQLite on a volume means exactly **one** machine.
> Never `fly scale count 2`, never add regions, and keep `--ha=false` on the
> first deploy. Outgrowing this is the trigger to move to Postgres.

## One-time setup

1. Install flyctl and sign in:

   ```bash
   curl -L https://fly.io/install.sh | sh
   fly auth login
   ```

2. Create the app and volume (if the app name is taken, pick another and
   update `app` in `fly.toml`):

   ```bash
   fly apps create agentpulse-backend
   fly volumes create agentpulse_data --app agentpulse-backend --region yyz --size 1
   ```

3. First deploy, from the repository root:

   ```bash
   fly deploy --ha=false
   ```

   The app initializes its own schema on startup. Verify:

   ```bash
   curl https://agentpulse-backend.fly.dev/health
   ```

4. Custom domain (`api.agentpulse.ca`):

   ```bash
   fly certs add api.agentpulse.ca
   ```

   In Cloudflare, add a `CNAME` for `api` → `agentpulse-backend.fly.dev`
   with the proxy **off** (grey cloud / DNS-only) so Fly can issue the
   certificate. Check with `fly certs show api.agentpulse.ca`.

5. Wire CI deploys — create a deploy-scoped token and save it as the
   `FLY_API_TOKEN` repository secret:

   ```bash
   fly tokens create deploy --expiry 8760h
   ```

   After that, every push to `main` touching `backend/`, `fly.toml`, or the
   deploy workflow redeploys automatically
   (`.github/workflows/deploy_backend.yml`). Until the secret exists the
   workflow skips with a note instead of failing.

## Issuing agent tokens and licenses

The management CLI runs inside the machine:

```bash
fly ssh console -C "agentpulse-backend create-api-key --org default --label first-customer"
fly ssh console -C "agentpulse-backend create-license --org default --plan pro --max-agents 5"
fly ssh console -C "agentpulse-backend verify-license apl_..."
```

Tokens/licenses are printed once and only their hashes are stored — copy them
immediately.

Point an agent at production in its config:

```json
"checkin": {
  "endpoint_url": "https://api.agentpulse.ca/api/agent/checkin",
  "auth_token": "ap_...",
  "timeout_seconds": 5
}
```

## Operations

- **Logs:** `fly logs`
- **Status:** `fly status` and `curl https://api.agentpulse.ca/health`
- **Backups:** Fly snapshots volumes daily (5-day retention). Take a manual
  snapshot before risky changes: `fly volumes snapshots create <volume-id>`
  (find the id with `fly volumes list`).
- **Deploy manually:** `fly deploy` from the repo root, or the
  "Deploy backend (Fly.io)" workflow's *Run workflow* button.
- **DB shell:** `fly ssh console -C "sqlite3 /data/agentpulse.db"` (install
  sqlite3 in the image first if needed) — or copy the file out with
  `fly ssh sftp get /data/agentpulse.db`.

## When to leave this setup

Move to Fly Postgres (or managed Postgres) when any of these happen: more
than ~50 agents checking in every 60s, a second machine/region is needed, or
check-in history growth makes the volume a chore. The `Store` class is the
only thing that has to change.
