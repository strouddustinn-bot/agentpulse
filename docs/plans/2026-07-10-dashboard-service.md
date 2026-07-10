# AgentPulse Persistent Dashboard Service — Implementation Plan

> **For the implementing agent:** Execute tasks strictly in order. Each task is
> small, has exact file paths, complete copy-pasteable code, and a verification
> command with expected output. Do not improvise architecture — every design
> decision is already made (see "Resolution decisions" below). If a verification
> step fails in a way not covered by the expected-failure list, STOP and report.

**Goal:** A beautiful, always-on dashboard for AgentPulse: a persistent FastAPI
backend (systemd service, SQLite persistence, SSE push) + a React 19/Vite/TS
frontend, wired to the existing agent via its JSON state file and CLI.

**Architecture:** The agent stays dependency-free and untouched except for one
small CLI addition (`deny`). A NEW separate service (`dashboard/`) owns
persistence and the UI: it tails the agent's `state.json`, mirrors history into
SQLite (unbounded, vs the agent's 200-record cap), samples host metrics for
charts, and pushes changes to browsers over Server-Sent Events. Approve/deny
actions shell out to the agent CLI so every action still flows through the
agent's tested safety loop. This is deliberately an *additive control layer* —
the agent's decision loop, policy gate, and state format are not modified.

**Tech Stack:** Python 3.10+ · FastAPI + uvicorn · SQLite (stdlib `sqlite3`) ·
SSE (no websocket lib needed) · React 19 + Vite + TypeScript · Tailwind CSS v4
· recharts.

---

## Verified current-state snapshot (2026-07-10)

Reproduce with the commands shown. If your numbers differ, stop and report.

```bash
cd /home/dstroud/Projects/agentpulse
git status --short --branch
# ## main...origin/main [ahead 1, behind 32]
# ~17 modified files under agent/, docs/
# ?? agent/agentpulse/dashboard.py
# ?? agent/agentpulse/federation.py

cd agent && python3 tools/run_tests.py
# PASSED: 79   FAILED: 0
```

- The ONLY acceptable baseline is **79 passed / 0 failed**. Any other failure
  at any gate below: stop.
- `agent/agentpulse/dashboard.py` (in-agent stdlib dashboard) and
  `federation.py` (hub/spoke) already exist and WORK. They are kept as the
  zero-dep fallback. The new service does not replace them; it supersedes them
  for humans.

### FLAG TO OPERATOR (do NOT perform these as the implementing agent)
1. Branch is **behind origin/main by 32 commits** with a dirty tree. Operator
   must decide whether to pull/rebase before this work lands. Default for the
   implementing agent: work on a new branch `feat/dashboard-service` off
   current local `main`, commit the currently-untracked
   `dashboard.py`/`federation.py` as Task 0, and DO NOT push or rebase.
2. Any production systemd install (`Task 22`) runs as root — operator applies
   it; the agent only writes the unit file into the repo.

### Resolution decisions already made (do not revisit)
| Decision | Choice |
|---|---|
| Audience scope | Both local single-server AND hosted multi-tenant path (design seams for tenancy, implement single-tenant now) |
| Persistence model | Separate always-running service, NOT inside the agent process |
| Real-time | SSE push (EventSource). Not polling, not raw WebSockets |
| Agent coupling | Read-only via `state.json` file watch; write path ONLY via `python3 -m agentpulse approve|deny` subprocess |
| Agent changes | Exactly one: add `deny` CLI command. Nothing else in `agent/` changes |
| Backend framework | FastAPI + uvicorn (the separate service MAY have deps; the agent may NOT) |
| DB | SQLite, stdlib `sqlite3`, WAL mode. No ORM |
| Frontend | React 19 + Vite + TS + Tailwind v4 + recharts, dark theme matching existing palette (`#0f1117` bg, `#7c6af7` accent) |
| Auth | Single static bearer token (env `PULSE_TOKEN`) for mutating endpoints; read endpoints open on localhost bind. Multi-tenant auth is deferred |
| Test framework | Backend: stdlib `unittest` (repo convention: no pytest). Frontend: build-time `tsc -b` + Playwright smoke only |

### Deferred — DO NOT build in this pass
- Multi-tenant auth/orgs/billing, hosted control plane
- Slack/Discord integrations
- ML baselines UI beyond showing anomaly counts
- Replacing the in-agent stdlib dashboard or federation hub
- WebSocket upgrade, terminal streaming, log tailing

---

## Directory layout being created

```
agentpulse/
├── agent/                      # existing — one file touched (cli.py) + one test file
├── dashboard/                  # NEW backend service
│   ├── requirements.txt
│   ├── pulse_server/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI app, SSE, routes
│   │   ├── db.py               # SQLite layer
│   │   ├── ingest.py           # state.json watcher + host metric sampler
│   │   └── actions.py          # approve/deny via agent CLI subprocess
│   ├── tests/
│   │   └── test_server.py      # unittest
│   └── web/                    # NEW frontend (Vite React TS)
│       ├── package.json ... (vite scaffold)
│       └── src/...
├── systemd/
│   └── agentpulse-dashboard.service   # NEW unit
└── docs/plans/2026-07-10-dashboard-service.md  # this file
```

---

## Phase 0 — Checkpoint

### Task 0: Branch + commit untracked agent files

**Objective:** Clean checkpoint so later diffs are reviewable.

```bash
cd /home/dstroud/Projects/agentpulse
git checkout -b feat/dashboard-service
git add agent/agentpulse/dashboard.py agent/agentpulse/federation.py docs/plans/2026-07-10-dashboard-service.md
git commit -m "chore: checkpoint in-agent dashboard/federation + dashboard service plan"
```

Verify: `git status --short` no longer lists those files as `??`.
(The pre-existing modified files stay uncommitted — they are the operator's
in-flight work. Do not add them.)

---

## Phase 1 — Agent-side minimal addition: `deny` command

### Task 1: Write failing test for deny

**Files:** Create `agent/tests/test_deny.py`

```python
"""Tests for the deny CLI path: pop a pending action without executing it."""

from agentpulse.models import Decision, Observation
from agentpulse.runner import deny
from agentpulse.state import State


def _mk_state(tmp_path):
    st = State(str(tmp_path / "state.json"))
    obs = Observation(check="service", target="nginx", breached=True)
    d = Decision(
        action="service_restart", target="nginx", mode_effective="ask",
        execute=False, requires_approval=True, reason="crashed", observation=obs,
    )
    pid = st.queue_pending(d)
    return st, pid


def test_deny_removes_pending_and_records_history(tmp_path):
    st, pid = _mk_state(tmp_path)
    entry = deny(st, pid)
    assert entry is not None
    assert st.get_pending(pid) is None
    assert st.data["history"][-1]["outcome"] == "denied"
    assert st.data["history"][-1]["action"] == "service_restart"


def test_deny_unknown_id_returns_none(tmp_path):
    st, _ = _mk_state(tmp_path)
    assert deny(st, "nope") is None
```

**Step 2:** Run `cd agent && python3 tools/run_tests.py` — expected: FAILED
(import error: `deny` not defined). This is the ONLY failure allowed at this
gate.

### Task 2: Implement `deny` in runner.py

**Files:** Modify `agent/agentpulse/runner.py` — append after the `approve`
function (ends near line 296):

```python
def deny(state: State, pending_id: str):
    """Reject a queued ask-first action: remove it and record the denial."""
    entry = state.pop_pending(pending_id)
    if entry is None:
        return None
    state.record_history({
        "action": entry.get("action", ""),
        "target": entry.get("target", ""),
        "outcome": "denied",
        "reason": "denied by operator",
        "ts": time.time(),
    })
    state.save()
    return entry
```

Run `python3 tools/run_tests.py` — expected: **81 passed / 0 failed**.

### Task 3: Wire `deny` into the CLI

**Files:** Modify `agent/agentpulse/cli.py`:

1. Change the import line to include deny:
   `from .runner import approve, deny, run_loop, run_once`
2. In `build_parser()`, after the `approve` subparser block, add:

```python
    pd = sub.add_parser("deny", help="reject a pending ask-first action without executing it")
    pd.add_argument("config")
    pd.add_argument("pending_id")
```

3. In `main()`, after the `approve` command handler, add:

```python
    if args.command == "deny":
        cfg, state, _ = _load(args.config)
        entry = deny(state, args.pending_id)
        if entry is None:
            print(f"no pending action with id {args.pending_id}", file=sys.stderr)
            return 2
        print(f"denied: {entry['action']} {entry['target']}")
        return 0
```

**Verify:**
```bash
python3 tools/run_tests.py                    # 81 passed / 0 failed
python3 -m agentpulse deny agentpulse.config.local.json bogus; echo "exit=$?"
# no pending action with id bogus
# exit=2
```

**Commit:** `git add agent/ && git commit -m "feat(agent): deny command for pending approvals"`

---

## Phase 2 — Backend service (`dashboard/`)

### Task 4: Scaffold + requirements

**Files:** Create `dashboard/requirements.txt`:

```
fastapi>=0.115
uvicorn[standard]>=0.30
```

Create empty `dashboard/pulse_server/__init__.py` (single line:
`__version__ = "0.1.0"`).

```bash
cd /home/dstroud/Projects/agentpulse/dashboard
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```
Expected: install succeeds. (If no network, FLAG TO OPERATOR and stop.)

### Task 5: SQLite layer

**Files:** Create `dashboard/pulse_server/db.py`:

```python
"""SQLite persistence for the dashboard service.

Tables:
  history        — mirror of agent history, unbounded (agent caps at 200)
  metric_samples — host metric time series for charts
  events         — service-level event log (ingest errors, actions taken via UI)
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    outcome TEXT NOT NULL,
    dedupe_key TEXT UNIQUE,
    raw TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_ts ON history(ts);

CREATE TABLE IF NOT EXISTS metric_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_samples_metric_ts ON metric_samples(metric, ts);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    detail TEXT NOT NULL
);
"""


class Db:
    def __init__(self, path: str):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def record_history(self, entry: Dict[str, Any]) -> bool:
        """Insert a history record; returns True if new (dedupe on ts+action+target)."""
        key = f"{entry.get('ts')}:{entry.get('action')}:{entry.get('target')}"
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO history (ts, action, target, outcome, dedupe_key, raw) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        float(entry.get("ts") or time.time()),
                        str(entry.get("action", "")),
                        str(entry.get("target", "")),
                        str(entry.get("outcome", "")),
                        key,
                        json.dumps(entry),
                    ),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def history(self, limit: int = 100, before_ts: Optional[float] = None) -> List[Dict]:
        q = "SELECT raw FROM history"
        args: list = []
        if before_ts is not None:
            q += " WHERE ts < ?"
            args.append(before_ts)
        q += " ORDER BY ts DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(q, args).fetchall()
        return [json.loads(r[0]) for r in rows]

    def record_sample(self, metric: str, value: float, ts: Optional[float] = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO metric_samples (ts, metric, value) VALUES (?, ?, ?)",
                (ts or time.time(), metric, value),
            )
            self._conn.commit()

    def samples(self, metric: str, since: float) -> List[Dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, value FROM metric_samples WHERE metric = ? AND ts >= ? ORDER BY ts",
                (metric, since),
            ).fetchall()
        return [{"ts": r[0], "value": r[1]} for r in rows]

    def metrics(self) -> List[str]:
        with self._lock:
            rows = self._conn.execute("SELECT DISTINCT metric FROM metric_samples").fetchall()
        return [r[0] for r in rows]

    def record_event(self, kind: str, detail: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (ts, kind, detail) VALUES (?, ?, ?)",
                (time.time(), kind, detail),
            )
            self._conn.commit()

    def prune(self, keep_days: int = 90) -> None:
        cutoff = time.time() - keep_days * 86400
        with self._lock:
            self._conn.execute("DELETE FROM metric_samples WHERE ts < ?", (cutoff,))
            self._conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
            self._conn.commit()
```

### Task 6: Failing tests for db + ingest

**Files:** Create `dashboard/tests/test_server.py`:

```python
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pulse_server.db import Db
from pulse_server.ingest import StateWatcher


class TestDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Db(os.path.join(self.tmp.name, "pulse.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_history_dedupe(self):
        e = {"ts": 123.0, "action": "disk_cleanup", "target": "/tmp/x", "outcome": "succeeded"}
        self.assertTrue(self.db.record_history(e))
        self.assertFalse(self.db.record_history(e))
        self.assertEqual(len(self.db.history()), 1)

    def test_samples_roundtrip(self):
        self.db.record_sample("mem", 41.5, ts=100.0)
        self.db.record_sample("mem", 43.0, ts=200.0)
        got = self.db.samples("mem", since=150.0)
        self.assertEqual(got, [{"ts": 200.0, "value": 43.0}])


class TestStateWatcher(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Db(os.path.join(self.tmp.name, "pulse.db"))
        self.state_path = os.path.join(self.tmp.name, "state.json")
        self.events = []

    def tearDown(self):
        self.tmp.cleanup()

    def _write_state(self, data):
        with open(self.state_path, "w") as fh:
            json.dump(data, fh)

    def test_detects_new_history_and_emits(self):
        self._write_state({
            "last_run": 111.0,
            "pending": {},
            "history": [{"ts": 1.0, "action": "a", "target": "t", "outcome": "succeeded"}],
            "blocked_ips": {},
        })
        w = StateWatcher(self.state_path, self.db, emit=self.events.append)
        w.poll_once()
        self.assertEqual(len(self.db.history()), 1)
        kinds = [e["type"] for e in self.events]
        self.assertIn("state", kinds)

    def test_missing_file_is_quiet(self):
        w = StateWatcher(os.path.join(self.tmp.name, "nope.json"), self.db,
                         emit=self.events.append)
        w.poll_once()  # must not raise
        self.assertEqual(self.db.history(), [])


if __name__ == "__main__":
    unittest.main()
```

Run: `cd dashboard && .venv/bin/python -m unittest tests.test_server -v`
Expected: FAIL — `ModuleNotFoundError: pulse_server.ingest`. Only this failure
is allowed.

### Task 7: Ingest — state watcher + metric sampler

**Files:** Create `dashboard/pulse_server/ingest.py`:

```python
"""Watches the agent's state.json and samples host metrics.

StateWatcher.poll_once(): re-reads state.json when mtime changes, mirrors new
history rows into SQLite, and emits SSE payloads via the injected `emit`
callback. MetricSampler.sample_once(): reads /proc + disk usage directly
(same host in v1) and records chartable series.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from typing import Callable, Dict, List, Optional

from .db import Db


class StateWatcher:
    def __init__(self, state_path: str, db: Db, emit: Callable[[dict], None]):
        self.state_path = state_path
        self.db = db
        self.emit = emit
        self._mtime: Optional[float] = None
        self.snapshot: Dict = {}

    def poll_once(self) -> None:
        try:
            mtime = os.stat(self.state_path).st_mtime
        except OSError:
            return
        if self._mtime is not None and mtime == self._mtime:
            return
        self._mtime = mtime
        try:
            with open(self.state_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            self.db.record_event("ingest_error", str(exc))
            return

        self.snapshot = data
        new_rows = 0
        for entry in data.get("history", []):
            if self.db.record_history(entry):
                new_rows += 1

        self.emit({
            "type": "state",
            "data": {
                "last_run": data.get("last_run"),
                "pending": list(data.get("pending", {}).values()),
                "blocked_ips": list(data.get("blocked_ips", {}).values()),
                "fleet": data.get("fleet", {}),
                "new_history": new_rows,
            },
        })
        if new_rows:
            self.emit({"type": "history", "data": self.db.history(limit=50)})


def _mem_percent() -> Optional[float]:
    try:
        info = {}
        with open("/proc/meminfo") as fh:
            for line in fh:
                parts = line.split()
                info[parts[0].rstrip(":")] = int(parts[1])
        total = info["MemTotal"]
        avail = info.get("MemAvailable", info.get("MemFree", 0))
        return round(100.0 * (total - avail) / total, 2)
    except (OSError, KeyError, ValueError, ZeroDivisionError):
        return None


def _load1() -> Optional[float]:
    try:
        return os.getloadavg()[0]
    except OSError:
        return None


class MetricSampler:
    def __init__(self, db: Db, disk_paths: List[str], emit: Callable[[dict], None]):
        self.db = db
        self.disk_paths = disk_paths
        self.emit = emit

    def sample_once(self) -> None:
        ts = time.time()
        point: Dict[str, float] = {}
        mem = _mem_percent()
        if mem is not None:
            self.db.record_sample("mem", mem, ts)
            point["mem"] = mem
        load = _load1()
        if load is not None:
            self.db.record_sample("load1", load, ts)
            point["load1"] = load
        for path in self.disk_paths:
            try:
                du = shutil.disk_usage(path)
                pct = round(100.0 * du.used / du.total, 2)
            except OSError:
                continue
            self.db.record_sample(f"disk:{path}", pct, ts)
            point[f"disk:{path}"] = pct
        if point:
            self.emit({"type": "metrics", "data": {"ts": ts, "values": point}})
```

Run: `.venv/bin/python -m unittest tests.test_server -v` — expected:
**4 tests, OK**.

**Commit:** `git add dashboard/ && git commit -m "feat(dashboard): sqlite layer + state ingest with tests"`

### Task 8: Actions — approve/deny via agent CLI

**Files:** Create `dashboard/pulse_server/actions.py`:

```python
"""Approve/deny pending actions by shelling out to the agent CLI.

The dashboard NEVER mutates state.json directly — the agent's own approve
path (decision loop, safety gate, verify) must run. Fail closed on anything
unexpected.
"""

from __future__ import annotations

import re
import subprocess
import sys
from typing import Tuple

_ID_RE = re.compile(r"^[0-9a-f]{6,12}$")


def _run_agent(agent_dir: str, config_path: str, verb: str, pending_id: str) -> Tuple[bool, str]:
    if verb not in ("approve", "deny"):
        return False, "invalid verb"
    if not _ID_RE.match(pending_id):
        return False, "invalid pending id format"
    cmd = [sys.executable, "-m", "agentpulse", verb, config_path, pending_id]
    try:
        proc = subprocess.run(
            cmd, cwd=agent_dir, capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return False, "agent CLI timed out"
    out = (proc.stdout + proc.stderr).strip()
    return proc.returncode == 0, out


def approve(agent_dir: str, config_path: str, pending_id: str) -> Tuple[bool, str]:
    return _run_agent(agent_dir, config_path, "approve", pending_id)


def deny(agent_dir: str, config_path: str, pending_id: str) -> Tuple[bool, str]:
    return _run_agent(agent_dir, config_path, "deny", pending_id)
```

### Task 9: FastAPI app with SSE

**Files:** Create `dashboard/pulse_server/main.py`:

```python
"""AgentPulse dashboard service.

Env config:
  PULSE_STATE_FILE   — path to the agent's state.json (required)
  PULSE_AGENT_DIR    — path to the agent/ directory (for CLI actions)
  PULSE_AGENT_CONFIG — path to the agent config json (for CLI actions)
  PULSE_DB           — sqlite path (default: ./pulse.db)
  PULSE_TOKEN        — bearer token required for POST endpoints ("" = reject all)
  PULSE_DISK_PATHS   — comma-separated paths to chart disk usage (default "/")
  PULSE_WEB_DIST     — path to built frontend (default ../web/dist)

Run: uvicorn pulse_server.main:app --host 127.0.0.1 --port 8790
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import time
from typing import List

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import actions
from .db import Db
from .ingest import MetricSampler, StateWatcher

STATE_FILE = os.environ.get("PULSE_STATE_FILE", "/var/lib/agentpulse/state.json")
AGENT_DIR = os.environ.get("PULSE_AGENT_DIR", "")
AGENT_CONFIG = os.environ.get("PULSE_AGENT_CONFIG", "")
DB_PATH = os.environ.get("PULSE_DB", "pulse.db")
TOKEN = os.environ.get("PULSE_TOKEN", "")
DISK_PATHS = [p for p in os.environ.get("PULSE_DISK_PATHS", "/").split(",") if p]
WEB_DIST = os.environ.get(
    "PULSE_WEB_DIST",
    os.path.join(os.path.dirname(__file__), "..", "web", "dist"),
)

app = FastAPI(title="AgentPulse Dashboard", version="0.1.0")
db = Db(DB_PATH)

# ---- SSE fan-out -----------------------------------------------------------

_subscribers: List[queue.Queue] = []
_sub_lock = threading.Lock()


def _emit(payload: dict) -> None:
    with _sub_lock:
        for q in list(_subscribers):
            try:
                q.put_nowait(payload)
            except queue.Full:
                pass


watcher = StateWatcher(STATE_FILE, db, emit=_emit)
sampler = MetricSampler(db, DISK_PATHS, emit=_emit)


def _background_loop() -> None:
    tick = 0
    while True:
        watcher.poll_once()          # every second
        if tick % 15 == 0:
            sampler.sample_once()    # every 15s
        if tick % 86400 == 0 and tick > 0:
            db.prune()
        tick += 1
        time.sleep(1)


threading.Thread(target=_background_loop, daemon=True).start()


# ---- auth ------------------------------------------------------------------

def require_token(authorization: str = Header(default="")) -> None:
    if not TOKEN or authorization != f"Bearer {TOKEN}":
        raise HTTPException(status_code=401, detail="unauthorized")


# ---- API -------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True, "state_file": STATE_FILE,
            "last_run": watcher.snapshot.get("last_run")}


@app.get("/api/state")
def state():
    s = watcher.snapshot
    return {
        "last_run": s.get("last_run"),
        "pending": list(s.get("pending", {}).values()),
        "blocked_ips": list(s.get("blocked_ips", {}).values()),
        "fleet": s.get("fleet", {}),
    }


@app.get("/api/history")
def history(limit: int = 100, before_ts: float | None = None):
    return {"history": db.history(limit=min(limit, 500), before_ts=before_ts)}


@app.get("/api/metrics")
def metrics(hours: float = 24.0):
    since = time.time() - hours * 3600
    return {m: db.samples(m, since) for m in db.metrics()}


@app.post("/api/pending/{pending_id}/approve", dependencies=[Depends(require_token)])
def approve_pending(pending_id: str):
    ok, out = actions.approve(AGENT_DIR, AGENT_CONFIG, pending_id)
    db.record_event("approve", f"{pending_id}: ok={ok} {out}")
    if not ok:
        raise HTTPException(status_code=409, detail=out)
    watcher.poll_once()
    return {"ok": True, "output": out}


@app.post("/api/pending/{pending_id}/deny", dependencies=[Depends(require_token)])
def deny_pending(pending_id: str):
    ok, out = actions.deny(AGENT_DIR, AGENT_CONFIG, pending_id)
    db.record_event("deny", f"{pending_id}: ok={ok} {out}")
    if not ok:
        raise HTTPException(status_code=409, detail=out)
    watcher.poll_once()
    return {"ok": True, "output": out}


@app.get("/api/events")
async def sse():
    q: queue.Queue = queue.Queue(maxsize=256)
    with _sub_lock:
        _subscribers.append(q)

    async def stream():
        try:
            # initial snapshot so a fresh tab renders instantly
            init = {"type": "state", "data": state()}
            yield f"data: {json.dumps(init)}\n\n"
            yield f"data: {json.dumps({'type': 'history', 'data': db.history(limit=50)})}\n\n"
            while True:
                try:
                    payload = q.get_nowait()
                    yield f"data: {json.dumps(payload)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
                    await asyncio.sleep(1)
        finally:
            with _sub_lock:
                if q in _subscribers:
                    _subscribers.remove(q)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# ---- static frontend (built) -------------------------------------------------

if os.path.isdir(WEB_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(WEB_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        candidate = os.path.join(WEB_DIST, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(WEB_DIST, "index.html"))
```

### Task 10: Verify backend end-to-end against the real agent state

```bash
cd /home/dstroud/Projects/agentpulse/dashboard
# find the local state file path:
grep state_file ../agent/agentpulse.config.local.json
export PULSE_STATE_FILE=<value from config>   # e.g. /tmp/agentpulse/state.json
export PULSE_AGENT_DIR=$(realpath ../agent)
export PULSE_AGENT_CONFIG=$(realpath ../agent/agentpulse.config.local.json)
export PULSE_TOKEN=devtoken
# generate fresh state:
(cd ../agent && python3 -m agentpulse run-once agentpulse.config.local.json)
.venv/bin/uvicorn pulse_server.main:app --port 8790 &
sleep 2
curl -s localhost:8790/api/health          # {"ok":true,...}
curl -s localhost:8790/api/state | head -c 200
curl -s localhost:8790/api/metrics | head -c 200
curl -s -N localhost:8790/api/events | head -2   # data: {"type":"state",...}
curl -s -X POST localhost:8790/api/pending/abc123/approve
# {"detail":"unauthorized"}  ← 401 without token: REQUIRED behavior
kill %1
```

Run unit tests again: `.venv/bin/python -m unittest tests.test_server -v` → OK.

**Commit:** `git add dashboard/ && git commit -m "feat(dashboard): fastapi service with SSE, actions, sqlite persistence"`

---

## Phase 3 — Frontend (`dashboard/web/`)

Design language: match the existing in-agent dashboard palette —
bg `#0f1117`, card `#1a1d27`, border `#2d3048`, accent `#7c6af7`,
ok `#22c55e`, warn `#f59e0b`, err `#ef4444`, text `#e2e8f0`, muted `#64748b`.
Inter or system font stack. Rounded-xl cards, subtle borders, generous spacing.
This must look like a premium ops product (Linear/Vercel tier), not bootstrap.

### Task 11: Scaffold Vite app

```bash
cd /home/dstroud/Projects/agentpulse/dashboard
npm create vite@latest web -- --template react-ts
cd web && npm install && npm install recharts
npm install tailwindcss @tailwindcss/vite
```

Add tailwind + dev proxy to `web/vite.config.ts`:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8790', changeOrigin: true },
    },
  },
})
```

Replace `web/src/index.css` entirely with:

```css
@import "tailwindcss";

@theme {
  --color-bg: #0f1117;
  --color-card: #1a1d27;
  --color-edge: #2d3048;
  --color-accent: #7c6af7;
  --color-ok: #22c55e;
  --color-warn: #f59e0b;
  --color-err: #ef4444;
  --color-ink: #e2e8f0;
  --color-muted: #64748b;
}

body { @apply bg-bg text-ink antialiased; font-family: Inter, -apple-system, 'Segoe UI', sans-serif; }
```

Verify: `npm run dev` starts; `npm run build` passes (`tsc -b` + vite).

### Task 12: Shared types + SSE hook

**Files:** Create `web/src/lib/types.ts`:

```ts
export interface Pending {
  id: string; action: string; target: string; reason: string;
  check: string; queued_at: number;
}
export interface HistoryEntry {
  ts: number; action: string; target: string; outcome: string;
  reason?: string; approved?: boolean; dry_run?: boolean;
}
export interface BlockedIp { ip: string; blocked_at: number; duration: number; reason?: string }
export interface FleetAgent { agent_id: string; hostname: string; last_seen: number; state: unknown }
export interface StateSnapshot {
  last_run: number | null;
  pending: Pending[];
  blocked_ips: BlockedIp[];
  fleet: Record<string, FleetAgent>;
}
export interface MetricPoint { ts: number; value: number }
export type SseMsg =
  | { type: 'state'; data: StateSnapshot & { new_history?: number } }
  | { type: 'history'; data: HistoryEntry[] }
  | { type: 'metrics'; data: { ts: number; values: Record<string, number> } };
```

Create `web/src/lib/useLive.ts`:

```ts
import { useEffect, useRef, useState } from 'react'
import type { HistoryEntry, SseMsg, StateSnapshot } from './types'

export function useLive() {
  const [state, setState] = useState<StateSnapshot | null>(null)
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [live, setLive] = useState(false)
  const [lastMetric, setLastMetric] = useState<Record<string, number>>({})
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    let stopped = false
    function connect() {
      const es = new EventSource('/api/events')
      esRef.current = es
      es.onopen = () => setLive(true)
      es.onmessage = (ev) => {
        const msg: SseMsg = JSON.parse(ev.data)
        if (msg.type === 'state') setState(msg.data)
        else if (msg.type === 'history') setHistory(msg.data)
        else if (msg.type === 'metrics') setLastMetric(msg.data.values)
      }
      es.onerror = () => {
        setLive(false)
        es.close()
        if (!stopped) setTimeout(connect, 3000) // auto-reconnect
      }
    }
    connect()
    return () => { stopped = true; esRef.current?.close() }
  }, [])

  return { state, history, live, lastMetric }
}
```

### Task 13: API client with token

**Files:** Create `web/src/lib/api.ts`:

```ts
const TOKEN_KEY = 'pulse_token'
export const getToken = () => localStorage.getItem(TOKEN_KEY) ?? ''
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t)

async function post(path: string): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { Authorization: `Bearer ${getToken()}` },
  })
  if (res.ok) return { ok: true }
  const body = await res.json().catch(() => ({ detail: res.statusText }))
  return { ok: false, error: body.detail }
}

export const approvePending = (id: string) => post(`/api/pending/${id}/approve`)
export const denyPending = (id: string) => post(`/api/pending/${id}/deny`)

export async function fetchMetrics(hours = 24) {
  const res = await fetch(`/api/metrics?hours=${hours}`)
  return res.json() as Promise<Record<string, { ts: number; value: number }[]>>
}
```

### Task 14–18: Components

Build these five components under `web/src/components/`, each its own task +
commit. Styling: card = `bg-card border border-edge rounded-xl p-5`.

**Task 14 — `TopBar.tsx`:** logo mark ("AgentPulse" + shield glyph, accent
color), a live-status pill (green pulse dot + "LIVE" when SSE connected,
amber "RECONNECTING…" otherwise — use `animate-pulse`), "last agent run Xs
ago" (recompute every 5s), and a token input (small, right-aligned,
password-type, persists via `setToken`).

**Task 15 — `StatCards.tsx`:** 4-up grid of headline stats: Pending approvals
(warn color when >0), Actions (24h, from history), Escalations (24h, err
color when >0), Blocked IPs. Big number (text-3xl font-bold), small muted
label, subtle icon. Data: props from `useLive`.

**Task 16 — `PendingList.tsx`:** the money component. Each pending item: action
badge, target in bold mono, reason, "queued Xm ago", and two buttons —
**Approve** (accent, solid) and **Deny** (ghost, err border). Buttons call the
api client, show spinner while in-flight, toast on error (401 → "Set your
token in the top bar"). Empty state: centered muted "No actions waiting —
the agent is holding steady." SSE refreshes the list automatically after
approve/deny (the backend re-polls state).

**Task 17 — `ActivityTimeline.tsx`:** vertical timeline of history entries
(newest first): colored dot by outcome (succeeded=ok, escalated/blocked=warn,
denied=muted, failed=err), action + target, relative time, expandable raw
detail (`<details>`). "Load older" button → `GET /api/history?before_ts=` and
append.

**Task 18 — `MetricsPanel.tsx`:** recharts `AreaChart` per metric family:
Memory %, Load, one chart per `disk:*` path. Fetch `fetchMetrics(hours)` on
mount with a 1h/24h/7d segmented control; append live points from
`lastMetric`. Accent-colored gradient fill, edge-colored grid,
muted axis text, tooltip with dark card styling. Y-axis 0–100 for percent
metrics.

**Task 19 — `App.tsx` composition:**

```
TopBar
StatCards
grid lg:grid-cols-2 → [PendingList, ActivityTimeline]
MetricsPanel (full width)
footer: muted "AgentPulse · alert-only by default · every fix verifies or escalates"
```

Delete Vite boilerplate (`App.css`, logo assets).
Verify after each component task: `npm run build` → exit 0. Commit each task.

### Task 20: Live e2e check

```bash
# terminal A — backend (env from Task 10)
cd dashboard && .venv/bin/uvicorn pulse_server.main:app --port 8790
# terminal B — generate agent activity every 30s
cd agent && python3 -m agentpulse run --max-cycles 10 agentpulse.config.local.json
# terminal C — frontend
cd dashboard/web && npm run dev
```

Open http://localhost:5173 — REQUIRED observations:
1. LIVE pill green within 2s, stats populated without reload.
2. After each agent cycle, "last run" updates without refresh (SSE, not poll).
3. Metrics charts draw and gain a point every ~15s.
4. Approve on a bogus/pending item without token → toast about setting token;
   with `devtoken` set → 409 or success passed through from the agent CLI.

**Commit:** `git add dashboard/web && git commit -m "feat(dashboard): react ui — live stats, approvals, timeline, metrics"`

---

## Phase 4 — Persistence (systemd) + docs

### Task 21: Production build served by the backend

```bash
cd dashboard/web && npm run build
cd .. && .venv/bin/uvicorn pulse_server.main:app --port 8790 &
sleep 2 && curl -s localhost:8790/ | grep -o '<title>[^<]*' # <title>AgentPulse
kill %1
```

### Task 22: systemd unit (written to repo; operator installs)

**Files:** Create `systemd/agentpulse-dashboard.service`:

```ini
[Unit]
Description=AgentPulse Dashboard Service
After=network.target

[Service]
Type=simple
User=agentpulse
Environment=PULSE_STATE_FILE=/var/lib/agentpulse/state.json
Environment=PULSE_AGENT_DIR=/opt/agentpulse/agent
Environment=PULSE_AGENT_CONFIG=/etc/agentpulse/config.json
Environment=PULSE_DB=/var/lib/agentpulse/pulse.db
Environment=PULSE_DISK_PATHS=/
EnvironmentFile=-/etc/agentpulse/dashboard.env
ExecStart=/opt/agentpulse/dashboard/.venv/bin/uvicorn pulse_server.main:app \
  --host 127.0.0.1 --port 8790 --app-dir /opt/agentpulse/dashboard
Restart=always
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/agentpulse
ProtectHome=true

[Install]
WantedBy=multi-user.target
```

Note in the unit-adjacent docs: `PULSE_TOKEN` goes in
`/etc/agentpulse/dashboard.env` (mode 600), never in the unit file.
**FLAG TO OPERATOR:** installing/enabling this unit is a root action.

For local persistent dev (no root): tmux —
`tmux new-session -d -s pulse-dash 'cd ~/Projects/agentpulse/dashboard && PULSE_STATE_FILE=... .venv/bin/uvicorn pulse_server.main:app --port 8790'`

### Task 23: Docs

Create `dashboard/README.md` covering: what it is (separate persistent service;
in-agent stdlib dashboard remains the zero-dep fallback), env vars table,
local quickstart (Task 10 commands), production install (systemd), API
reference (all 8 endpoints incl. SSE payload shapes), security model (bearer
token for mutations; bind 127.0.0.1 by default, put a reverse proxy + TLS in
front for remote access), and the hosted/multi-tenant seam note below.

Update root `README.md` "What's NOT here yet" — move "Cloud dashboard" honesty
note to reflect: local persistent dashboard now EXISTS; hosted control plane
still roadmap.

**Hosted-path seam (document, don't build):** multi-tenant = this same service
with (a) `agent_id` column added to all three tables, (b) ingest switched from
file-watch to authenticated `POST /ingest/heartbeat` (the federation spoke
already pushes this exact payload shape), (c) real auth in `require_token`.
The schema and route shapes were chosen so this is additive.

**Commit:** `git add systemd/ dashboard/README.md README.md && git commit -m "docs+ops: dashboard systemd unit, README, hosted seam notes"`

---

## Phase 5 — Final gates

Run ALL of these; every one must pass:

```bash
cd agent && python3 tools/run_tests.py                 # 81 passed / 0 failed
cd ../dashboard && .venv/bin/python -m unittest tests.test_server -v  # OK
cd web && npm run build                                # exit 0 (tsc -b + vite)
# smoke: Task 21 curl returns the AgentPulse title
git log --oneline feat/dashboard-service ^main | wc -l # ≥ 8 commits
```

Deliverables checklist:
- [ ] `deny` CLI + 2 tests (agent suite: 81/0)
- [ ] `dashboard/pulse_server/` — db, ingest, actions, main (SSE) + unittest suite
- [ ] `dashboard/web/` — Vite React TS UI, 6 components, dark premium theme
- [ ] `systemd/agentpulse-dashboard.service` + `dashboard/README.md`
- [ ] Root README updated honestly
- [ ] Branch `feat/dashboard-service`, NOT pushed, NOT rebased (operator decides)

## Findings → task traceability

| Finding (from repo review) | Addressed by |
|---|---|
| In-agent dashboard dies with the agent process | Separate service, systemd Restart=always (Tasks 9, 22) |
| History capped at 200 in state.json | SQLite unbounded mirror w/ dedupe (Task 5, 7) |
| No metric time series exists anywhere | MetricSampler + metric_samples table (Task 7) |
| Approvals only possible via SSH + CLI | UI approve/deny routed through agent CLI (Tasks 8, 16) |
| No deny path existed at all | Agent `deny` command (Tasks 1–3) |
| Fleet data exists (federation hub) but no UI | fleet passed through /api/state; grid deferred to hosted pass |
| Mutating endpoints need auth | Bearer token, fail-closed when unset (Task 9) |
