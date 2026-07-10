"""AgentPulse dashboard service — FastAPI app factory.

Settings are injectable (tests build their own); ``app`` at module bottom is
built from environment variables for uvicorn:

  PULSE_STATE_FILE   — path to the agent's state.json (required in prod)
  PULSE_AGENT_DIR    — path to the agent/ directory (for CLI actions)
  PULSE_AGENT_CONFIG — path to the agent config json (for CLI actions)
  PULSE_DB           — sqlite path (default: ./pulse.db)
  PULSE_TOKEN        — bearer token required for POST endpoints ("" = reject all)
  PULSE_DISK_PATHS   — comma-separated paths to chart disk usage (default "/")
  PULSE_WEB_DIST     — path to built frontend (default ../web/dist)

Run: uvicorn pulse_server.main:app --host 127.0.0.1 --port 8790
(Bind address is launch configuration — keep it loopback unless fronted by a
reverse proxy with TLS + auth.)
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import hmac
import json
import os
import queue
import threading
import time
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import actions
from .db import Db
from .ingest import MetricSampler, StateWatcher

_POLL_INTERVAL_S = 1.0
_SAMPLE_EVERY_TICKS = 15
_PRUNE_EVERY_TICKS = 86400


@dataclasses.dataclass(frozen=True)
class Settings:
    state_file: str = "/var/lib/agentpulse/state.json"
    agent_dir: str = ""
    agent_config: str = ""
    db_path: str = "pulse.db"
    token: str = ""
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


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Db(settings.db_path)
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

    # ---- auth ---------------------------------------------------------------

    def require_token(authorization: str = Header(default="")) -> None:
        if not _token_ok(settings.token, authorization):
            raise HTTPException(status_code=401, detail="unauthorized")

    # ---- API ---------------------------------------------------------------

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": app.version,
                "state_file": settings.state_file,
                "last_run": watcher.snapshot.get("last_run")}

    def _state_payload() -> dict:
        s = watcher.snapshot
        pending = s.get("pending")
        blocked = s.get("blocked_ips")
        return {
            "last_run": s.get("last_run"),
            "pending": list(pending.values()) if isinstance(pending, dict)
            else (pending or []),
            "blocked_ips": list(blocked.values()) if isinstance(blocked, dict)
            else (blocked or []),
            "fleet": s.get("fleet", {}),
        }

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


app = create_app()
