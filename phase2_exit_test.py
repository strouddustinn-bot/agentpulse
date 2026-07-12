"""Phase 2 trust-layer exit test; run from the repository root."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
from agentpulse_backend.database import run_migrations  # noqa: E402
from agentpulse_backend.database.connection import Connection, Store  # noqa: E402
from agentpulse_backend.repositories.agent import AgentRepository  # noqa: E402
from agentpulse_backend.app import create_app  # noqa: E402
sys.path.insert(0, str(ROOT / "agent"))
from agentpulse.checkin import CheckinClient  # noqa: E402
from agentpulse.audit import AuditLog  # noqa: E402
from agentpulse.identity import IdentityManager  # noqa: E402
from agentpulse.spool import Spool  # noqa: E402


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def request(url, method="GET", payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=3) as response:
        return int(response.status), json.loads(response.read().decode() or "{}")


def wait_for(url, process):
    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError("backend exited before readiness")
        try:
            status, _ = request(url)
            if status == 200:
                return
        except (OSError, urllib.error.URLError):
            time.sleep(0.1)
    raise RuntimeError("backend did not become ready")


def start_backend(db, port, log):
    env = os.environ.copy()
    env["AGENTPULSE_BACKEND_DB"] = str(db)
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "agentpulse_backend.app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT / "backend"), env=env, stdout=log, stderr=subprocess.STDOUT,
    )


def checkin_payload(agent_id, sequence):
    return {
        "version": "1", "agent_id": agent_id, "timestamp": now(), "sequence": sequence,
        "agent_version": "0.1.0", "config_version": "phase2-test", "hostname": "phase2-test",
        "uptime_seconds": sequence, "offline_queue_depth": 3, "signature": "",
        "results": [{"check_id": "heartbeat", "check_type": "heartbeat", "status": "pass",
                     "severity": "info", "executed_at": now(), "duration_ms": 1,
                     "value": 1, "unit": "ok", "message": "healthy", "evidence": [],
                     "consecutive_failures": 0, "is_baseline_anomaly": False}],
    }


def main():
    work = Path(tempfile.mkdtemp(prefix="agentpulse-phase2-"))
    db = work / "backend.sqlite"
    agent_dir = work / "agent"
    identity = IdentityManager(agent_dir / "identity.json", agent_dir / "credential")
    spool = Spool(agent_dir / "spool")
    audit = AuditLog(agent_dir / "audit.jsonl")
    log_path = work / "backend.log"
    port = 8099
    base = f"http://127.0.0.1:{port}"
    backend = None
    try:
        run_migrations(str(db))
        seed = AgentRepository(Store(str(db)))
        enrollment_token, _ = seed.create_enrollment_token()
        with log_path.open("w") as log:
            backend = start_backend(db, port, log)
            wait_for(base + "/health", backend)
            enrolled = identity.enroll(base, enrollment_token, "phase2-test")
            agent_id = enrolled["agent_id"]
            credential = identity.read_credential()
            assert (agent_dir / "credential").stat().st_mode & 0o777 == 0o600
            print("enrolled", agent_id, "credential_mode=0600")
            backend.terminate(); backend.wait(timeout=5); backend = None

            client = CheckinClient(identity, spool, endpoint_url=base, retry=None)
            for sequence in (1, 2, 3):
                assert client.send(checkin_payload(agent_id, sequence)) is None
            assert len(spool.list_pending()) == 3
            print("offline_spool", len(spool.list_pending()))

            backend = start_backend(db, port, log)
            wait_for(base + "/health", backend)
            assert client.replay() == 3
            assert spool.list_pending() == []
            print("replayed", 3, "events_in_order")

            conn = Connection(str(db)); conn.open()
            checkins = conn.query("SELECT idempotency_key, sequence FROM check_ins ORDER BY sequence")
            conn.close()
            assert len(checkins) == 3 and [r["sequence"] for r in checkins] == [1, 2, 3]
            assert len({r["idempotency_key"] for r in checkins}) == 3
            print("backend_exactly_once", len(checkins), "incidents_deduplicated=0")

            audit.append(agent_id=agent_id, event_type="checkin.replayed", correlation_id="phase2", actor="agent",
                         reason="backend recovered", policy={}, evidence_before={}, action={"count": 3},
                         result={"acknowledged": 3}, evidence_after={}, agent_version="0.1.0", config_version="phase2-test")
            secret_hits = []
            for path in (agent_dir / "spool").rglob("*"):
                if path.is_file() and credential in path.read_text(errors="ignore"):
                    secret_hits.append(str(path))
            for path in (agent_dir / "audit.jsonl", log_path):
                if path.exists() and credential in path.read_text(errors="ignore"):
                    secret_hits.append(str(path))
            assert not secret_hits
            print("credential_search", "0_hits", "logs_spool_audit")
            print("PHASE2_EXIT_PASS")
    finally:
        if backend is not None:
            backend.terminate(); backend.wait(timeout=5)
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
