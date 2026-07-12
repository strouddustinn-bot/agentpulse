"""AgentPulse dashboard service — FastAPI app factory.

Settings are injectable (tests build their own); ``app`` at module bottom is
built from environment variables for uvicorn:

  PULSE_STATE_FILE   — path to the agent's state.json (required in prod)
  PULSE_AGENT_DIR    — path to the agent/ directory (for CLI actions)
  PULSE_AGENT_CONFIG — path to the agent config json (for CLI actions)
  PULSE_DB           — sqlite path (default: ./pulse.db)
  PULSE_TOKEN        — bearer token required for local action POST endpoints
  PULSE_INGEST_TOKEN — bearer token required for federation heartbeats
  PULSE_READ_USER    — HTTP Basic username (default: agentpulse)
  PULSE_READ_PASSWORD— enables HTTP Basic protection for dashboard reads
  PULSE_DISK_PATHS   — comma-separated paths to chart disk usage (default "/")
  PULSE_WEB_DIST     — path to built frontend (default ../web/dist)

Run: uvicorn pulse_server.main:app --host 127.0.0.1 --port 8790
(Bind address is launch configuration — keep it loopback unless fronted by a
reverse proxy with TLS + auth.)
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import dataclasses
import hmac
import json
import os
import queue
import re
import threading
import time
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import actions
from .billing import BillingService, StripeGateway
from .db import Db
from .ingest import MetricSampler, StateWatcher

_POLL_INTERVAL_S = 1.0
_SAMPLE_EVERY_TICKS = 15
_PRUNE_EVERY_TICKS = 86400
_AGENT_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

_ONBOARDING_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport"
content="width=device-width,initial-scale=1"><title>AgentPulse setup</title>
<style>body{font:16px system-ui;background:#08111f;color:#e8eef7;max-width:720px;
margin:8vh auto;padding:24px}main{background:#101d30;border:1px solid #29405e;
border-radius:16px;padding:28px}input,button{box-sizing:border-box;width:100%;padding:12px;
margin-top:10px;border-radius:8px;border:1px solid #47617f}button{background:#2f7df6;
color:white;font-weight:700;cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;
background:#07101c;padding:16px;border-radius:8px}small{color:#9fb0c5}</style></head>
<body><main><h1>Activate AgentPulse</h1><p>Enter the email used at Stripe
Checkout. Your API key is shown once.</p><form id="claim"><input id="email"
type="email" required autocomplete="email" placeholder="you@example.com"><button>
Verify subscription and issue key</button></form><pre id="result" hidden></pre>
<small>Keep the generated key private. Billing access is enforced automatically.</small>
</main><script>const f=document.getElementById('claim'),o=document.getElementById('result');
f.addEventListener('submit',async(e)=>{e.preventDefault();o.hidden=false;o.textContent='Verifying…';
const session_id=new URLSearchParams(location.search).get('session_id')||'';
const r=await fetch('/api/onboarding/claim',{method:'POST',headers:{'Content-Type':
'application/json'},body:JSON.stringify({session_id,email:document.getElementById('email').value})});
const b=await r.json();o.textContent=r.ok?JSON.stringify(b,null,2):(b.detail||'Activation failed');});
</script></body></html>"""

_BILLING_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport"
content="width=device-width,initial-scale=1"><title>Manage AgentPulse billing</title>
<style>body{font:16px system-ui;background:#08111f;color:#e8eef7;max-width:640px;
margin:10vh auto;padding:24px}main{background:#101d30;border:1px solid #29405e;
border-radius:16px;padding:28px}input,button{box-sizing:border-box;width:100%;padding:12px;
margin-top:10px;border-radius:8px;border:1px solid #47617f}button{background:#2f7df6;
color:white;font-weight:700}</style></head><body><main><h1>Manage billing</h1>
<p>Enter your AgentPulse API key to open Stripe's secure customer portal.</p>
<form id="portal"><input id="key" type="password" required autocomplete="off"
placeholder="ap_live_…"><button>Open billing portal</button></form><p id="error"></p>
</main><script>document.getElementById('portal').addEventListener('submit',async(e)=>{
e.preventDefault();const r=await fetch('/api/billing/portal',{method:'POST',headers:
{'Authorization':'Bearer '+document.getElementById('key').value}});const b=await r.json();
if(r.ok)location.href=b.url;else document.getElementById('error').textContent=b.detail||
'Portal unavailable';});</script></body></html>"""


@dataclasses.dataclass(frozen=True)
class Settings:
    state_file: str = "/var/lib/agentpulse/state.json"
    agent_dir: str = ""
    agent_config: str = ""
    db_path: str = "pulse.db"
    token: str = ""
    ingest_token: str = ""
    read_user: str = "agentpulse"
    read_password: str = ""
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_starter: str = ""
    stripe_price_pro: str = ""
    stripe_price_business: str = ""
    public_base_url: str = "http://127.0.0.1:8790"
    disk_paths: tuple = ("/",)
    web_dist: str = os.path.join(os.path.dirname(__file__), "..", "web", "dist")
    enable_background: bool = True
    keep_days: int = 90
    max_subscribers: int = 64

    @classmethod
    def from_env(cls) -> "Settings":
        disks = tuple(
            p for p in os.environ.get("PULSE_DISK_PATHS", "/").split(",") if p)
        return cls(
            state_file=os.environ.get(
                "PULSE_STATE_FILE", "/var/lib/agentpulse/state.json"),
            agent_dir=os.environ.get("PULSE_AGENT_DIR", ""),
            agent_config=os.environ.get("PULSE_AGENT_CONFIG", ""),
            db_path=os.environ.get("PULSE_DB", "pulse.db"),
            token=os.environ.get("PULSE_TOKEN", ""),
            ingest_token=os.environ.get("PULSE_INGEST_TOKEN", ""),
            read_user=os.environ.get("PULSE_READ_USER", "agentpulse"),
            read_password=os.environ.get("PULSE_READ_PASSWORD", ""),
            stripe_secret_key=os.environ.get("STRIPE_SECRET_KEY", ""),
            stripe_webhook_secret=os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
            stripe_price_starter=os.environ.get("STRIPE_PRICE_STARTER", ""),
            stripe_price_pro=os.environ.get("STRIPE_PRICE_PRO", ""),
            stripe_price_business=os.environ.get("STRIPE_PRICE_BUSINESS", ""),
            public_base_url=os.environ.get(
                "PUBLIC_BASE_URL", "http://127.0.0.1:8790"),
            disk_paths=disks or ("/",),
            web_dist=os.environ.get(
                "PULSE_WEB_DIST",
                os.path.join(os.path.dirname(__file__), "..", "web", "dist")),
        )


class EventBroker:
    """Thread-safe SSE fan-out with a bounded subscriber count."""

    def __init__(self, max_subscribers: int = 64, queue_size: int = 256):
        self._subscribers: List[queue.Queue] = []
        self._lock = threading.Lock()
        self._max = max_subscribers
        self._queue_size = queue_size

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=self._queue_size)
        with self._lock:
            if len(self._subscribers) >= self._max:
                raise RuntimeError("too many subscribers")
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, payload: dict) -> None:
        with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(payload)
            except queue.Full:
                pass  # slow consumer drops events; SSE reconnect resyncs


def format_sse(payload: dict) -> str:
    """Serialize one payload as an SSE 'data:' frame."""
    return "data: %s\n\n" % json.dumps(payload)


def _token_ok(configured: str, authorization: str) -> bool:
    """Constant-time bearer check. Empty configured token fails closed."""
    if not configured:
        return False
    expected = "Bearer %s" % configured
    return hmac.compare_digest(
        (authorization or "").encode(), expected.encode())


def create_app(settings: Optional[Settings] = None, stripe_gateway=None) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Db(settings.db_path)
    if stripe_gateway is None and settings.stripe_secret_key:
        stripe_gateway = StripeGateway(settings.stripe_secret_key)
    billing = None
    if stripe_gateway is not None:
        billing = BillingService(
            db, stripe_gateway, settings.stripe_webhook_secret,
            settings.public_base_url,
            {
                settings.stripe_price_starter: "starter",
                settings.stripe_price_pro: "pro",
                settings.stripe_price_business: "business",
            },
        )
    broker = EventBroker(max_subscribers=settings.max_subscribers)
    watcher = StateWatcher(settings.state_file, db, emit=broker.publish)
    sampler = MetricSampler(db, list(settings.disk_paths),
                            emit=broker.publish)

    stop_event = threading.Event()

    def _background_loop() -> None:
        tick = 0
        while not stop_event.is_set():
            watcher.poll_once()
            if tick % _SAMPLE_EVERY_TICKS == 0:
                sampler.sample_once()
            if tick and tick % _PRUNE_EVERY_TICKS == 0:
                db.prune(keep_days=settings.keep_days)
            tick += 1
            stop_event.wait(_POLL_INTERVAL_S)

    worker: Optional[threading.Thread] = None

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        nonlocal worker
        watcher.poll_once()  # prime snapshot before serving
        if settings.enable_background:
            worker = threading.Thread(
                target=_background_loop, name="pulse-ingest", daemon=True)
            worker.start()
        yield
        stop_event.set()
        if worker is not None:
            worker.join(timeout=5)
        db.close()

    app = FastAPI(title="AgentPulse Dashboard", version="0.1.0",
                  lifespan=lifespan)
    app.state.db = db
    app.state.broker = broker
    app.state.watcher = watcher
    app.state.settings = settings
    app.state.billing = billing

    @app.middleware("http")
    async def protect_reads(request: Request, call_next):
        """Optional browser-friendly Basic auth for all dashboard reads."""
        if (not settings.read_password or request.method not in ("GET", "HEAD")
                or request.url.path in ("/api/health", "/onboarding", "/billing")):
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        valid = False
        if auth.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth[6:], validate=True).decode("utf-8")
                user, password = decoded.split(":", 1)
                valid = (hmac.compare_digest(user, settings.read_user)
                         and hmac.compare_digest(password, settings.read_password))
            except (binascii.Error, UnicodeDecodeError, ValueError):
                valid = False
        if not valid:
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="AgentPulse"'},
            )
        return await call_next(request)

    # ---- auth ---------------------------------------------------------------

    def require_token(authorization: str = Header(default="")) -> None:
        if not _token_ok(settings.token, authorization):
            raise HTTPException(status_code=401, detail="unauthorized")

    # ---- API ---------------------------------------------------------------

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": app.version,
                "state_file": settings.state_file,
                "last_run": watcher.snapshot.get("last_run"),
                "billing_configured": billing is not None
                and bool(settings.stripe_webhook_secret)}

    @app.post("/api/stripe/webhook")
    async def stripe_webhook(
            request: Request,
            stripe_signature: str = Header(default="", alias="Stripe-Signature")):
        if billing is None:
            raise HTTPException(status_code=503, detail="billing not configured")
        payload = await request.body()
        try:
            return billing.process_webhook(payload, stripe_signature)
        except Exception as exc:
            db.record_event("stripe_webhook_error", str(exc))
            raise HTTPException(status_code=400, detail="invalid Stripe event")

    @app.post("/api/onboarding/claim")
    def onboarding_claim(payload: dict):
        if billing is None:
            raise HTTPException(status_code=503, detail="billing not configured")
        session_id = str(payload.get("session_id", ""))
        email = str(payload.get("email", ""))
        if not session_id or not email or len(email) > 320:
            raise HTTPException(status_code=422,
                                detail="session_id and email are required")
        try:
            return billing.claim_onboarding(session_id, email)
        except FileExistsError:
            raise HTTPException(status_code=409,
                                detail="onboarding credentials already claimed")
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except Exception as exc:
            db.record_event("stripe_onboarding_error", str(exc))
            raise HTTPException(status_code=502, detail="Stripe verification failed")

    @app.post("/api/billing/portal")
    def billing_portal(authorization: str = Header(default="")):
        if billing is None:
            raise HTTPException(status_code=503, detail="billing not configured")
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="API key required")
        try:
            url = billing.create_portal(authorization[7:])
        except PermissionError:
            raise HTTPException(status_code=401,
                                detail="active subscription API key required")
        except Exception as exc:
            db.record_event("stripe_portal_error", str(exc))
            raise HTTPException(status_code=502, detail="portal unavailable")
        return {"url": url}

    @app.get("/onboarding", response_class=HTMLResponse,
             include_in_schema=False)
    def onboarding_page():
        return HTMLResponse(_ONBOARDING_HTML, headers={
            "Content-Security-Policy":
                "default-src 'none'; style-src 'unsafe-inline'; "
                "script-src 'unsafe-inline'; connect-src 'self'; "
                "base-uri 'none'; frame-ancestors 'none'",
            "Cache-Control": "no-store",
        })

    @app.get("/billing", response_class=HTMLResponse,
             include_in_schema=False)
    def billing_page():
        return HTMLResponse(_BILLING_HTML, headers={
            "Content-Security-Policy":
                "default-src 'none'; style-src 'unsafe-inline'; "
                "script-src 'unsafe-inline'; connect-src 'self'; "
                "base-uri 'none'; frame-ancestors 'none'",
            "Cache-Control": "no-store",
        })

    def _state_payload() -> dict:
        s = watcher.snapshot
        pending = s.get("pending")
        blocked = s.get("blocked_ips")
        fleet = dict(s.get("fleet") or {})
        fleet.update(db.fleet_agents())
        return {
            "last_run": s.get("last_run"),
            "pending": list(pending.values()) if isinstance(pending, dict)
            else (pending or []),
            "blocked_ips": list(blocked.values()) if isinstance(blocked, dict)
            else (blocked or []),
            "fleet": fleet,
        }

    @app.post("/fleet/heartbeat")
    def fleet_heartbeat(payload: dict,
                        authorization: str = Header(default="")):
        """Persist admin or paid-license heartbeats with plan-limit enforcement."""
        agent_id = str(payload.get("agent_id", ""))
        hostname = str(payload.get("hostname", agent_id))
        state = payload.get("state")
        if not _AGENT_ID_RE.fullmatch(agent_id):
            raise HTTPException(status_code=422, detail="invalid agent_id")
        if not hostname or len(hostname) > 255:
            raise HTTPException(status_code=422, detail="invalid hostname")
        if not isinstance(state, dict):
            raise HTTPException(status_code=422, detail="state must be an object")
        storage_agent_id = agent_id
        if not _token_ok(settings.ingest_token, authorization):
            if not authorization.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="unauthorized")
            entitlement = db.authorize_agent(authorization[7:], agent_id)
            reason = entitlement.get("reason")
            if not entitlement.get("allowed"):
                status = 402 if reason == "subscription_inactive" else (
                    403 if reason == "server_limit_exceeded" else 401)
                raise HTTPException(status_code=status, detail=reason)
            storage_agent_id = "%s:%s" % (
                entitlement["stripe_customer_id"], agent_id)
        db.upsert_agent(storage_agent_id, hostname, state)
        new_history = []
        history = state.get("history", [])
        if isinstance(history, list):
            for entry in history:
                if isinstance(entry, dict) and db.record_history(entry):
                    new_history.append(entry)
        broker.publish({"type": "state", "data": _state_payload()})
        if new_history:
            broker.publish({"type": "history", "data": db.history(limit=50)})
        return {"ok": True, "agent_id": agent_id}

    @app.get("/api/state")
    def state():
        return _state_payload()

    @app.get("/api/history")
    def history(limit: int = Query(default=100, ge=1, le=500),
                before_ts: Optional[float] = Query(default=None)):
        return {"history": db.history(limit=limit, before_ts=before_ts)}

    @app.get("/api/metrics")
    def metrics(hours: float = Query(default=24.0, gt=0, le=24 * 90)):
        since = time.time() - hours * 3600
        return {m: db.samples(m, since) for m in db.metrics()}

    def _mutate(verb: str, pending_id: str) -> dict:
        fn = actions.approve if verb == "approve" else actions.deny
        ok, out = fn(settings.agent_dir, settings.agent_config, pending_id)
        db.record_event(verb, "%s: ok=%s %s" % (pending_id, ok, out))
        if not ok:
            raise HTTPException(status_code=409, detail=out)
        # Force a re-read even if the state file's mtime didn't tick over.
        watcher.force_refresh()
        return {"ok": True, "output": out}

    @app.post("/api/pending/{pending_id}/approve",
              dependencies=[Depends(require_token)])
    def approve_pending(pending_id: str):
        return _mutate("approve", pending_id)

    @app.post("/api/pending/{pending_id}/deny",
              dependencies=[Depends(require_token)])
    def deny_pending(pending_id: str):
        return _mutate("deny", pending_id)

    @app.get("/api/events")
    async def sse():
        try:
            q = broker.subscribe()
        except RuntimeError:
            raise HTTPException(status_code=503, detail="too many subscribers")

        async def stream():
            try:
                # initial snapshot so a fresh tab renders instantly
                yield format_sse({"type": "state", "data": _state_payload()})
                yield format_sse(
                    {"type": "history", "data": db.history(limit=50)})
                while True:
                    try:
                        payload = q.get_nowait()
                        yield format_sse(payload)
                    except queue.Empty:
                        yield ": keepalive\n\n"
                        await asyncio.sleep(1)
            finally:
                broker.unsubscribe(q)

        return StreamingResponse(
            stream(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ---- static frontend (built) — registered AFTER API routes -------------

    web_dist = settings.web_dist
    if os.path.isdir(web_dist):
        assets = os.path.join(web_dist, "assets")
        if os.path.isdir(assets):
            app.mount("/assets", StaticFiles(directory=assets), name="assets")
        index_html = os.path.join(web_dist, "index.html")
        dist_real = os.path.realpath(web_dist)

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            candidate = os.path.realpath(os.path.join(web_dist, full_path))
            if (full_path and candidate.startswith(dist_real + os.sep)
                    and os.path.isfile(candidate)):
                return FileResponse(candidate)
            return FileResponse(index_html)

    return app


def __getattr__(name: str):
    # PEP 562: build the env-configured app lazily on first attribute access
    # (i.e. when uvicorn asks for `pulse_server.main:app`). Importing this
    # module — e.g. from tests — has no side effects: no DB file, no threads.
    if name == "app":
        application = create_app()
        globals()["app"] = application
        return application
    raise AttributeError(name)
