"""Fleet federation — hub/spoke multi-server coordination (stdlib only).

Hub mode: receives heartbeats from spoke agents, aggregates fleet state.
Spoke mode: posts local state to the hub on each cycle (called from runner.py).

The hub exposes:
    POST /fleet/heartbeat  — agent_id, hostname, state payload (auth via Bearer)
    GET  /fleet/agents     — list all registered agents + their last-seen state
    GET  /fleet/agent/<id> — state for a single agent

Hub data is stored in state.data["fleet"] and persisted with the normal
state.save() call that the runner already does.

Start the hub with federation.start_hub(cfg, state).
Spoke push is handled inline in runner.py (_push_to_hub).
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config
    from .state import State

_hub_cfg_ref = None
_hub_state_ref = None

# How long before an agent is considered stale (seconds).
_STALE_THRESHOLD = 600


class _HubHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, data, code=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth_ok(self) -> bool:
        cfg: "Config" = _hub_cfg_ref
        if not cfg or not cfg.federation.secret:
            return True  # no secret configured — open hub
        auth = self.headers.get("Authorization", "")
        expected = f"Bearer {cfg.federation.secret}"
        return auth == expected

    def do_POST(self):
        if not self._auth_ok():
            self._json({"error": "unauthorized"}, 401)
            return

        if self.path == "/fleet/heartbeat":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                payload = json.loads(body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._json({"error": "invalid JSON"}, 400)
                return

            agent_id = str(payload.get("agent_id", ""))
            hostname = str(payload.get("hostname", agent_id))
            state_snapshot = payload.get("state", {})

            if not agent_id:
                self._json({"error": "agent_id required"}, 400)
                return

            state: "State" = _hub_state_ref
            if state is not None:
                state.data.setdefault("fleet", {})
                state.data["fleet"][agent_id] = {
                    "agent_id": agent_id,
                    "hostname": hostname,
                    "last_seen": time.time(),
                    "state": state_snapshot,
                }
                # Persist fleet state.
                try:
                    state.save()
                except OSError:
                    pass

            self._json({"ok": True})
            return

        self._json({"error": "not found"}, 404)

    def do_GET(self):
        if not self._auth_ok():
            self._json({"error": "unauthorized"}, 401)
            return

        state: "State" = _hub_state_ref
        fleet = state.data.get("fleet", {}) if state else {}

        if self.path == "/fleet/agents":
            agents = []
            now = time.time()
            for agent in fleet.values():
                last_seen = agent.get("last_seen", 0)
                agents.append({
                    **agent,
                    "stale": (now - last_seen) > _STALE_THRESHOLD,
                })
            self._json({"agents": agents, "count": len(agents)})
            return

        if self.path.startswith("/fleet/agent/"):
            agent_id = self.path[len("/fleet/agent/"):]
            agent = fleet.get(agent_id)
            if agent is None:
                self._json({"error": f"agent {agent_id!r} not found"}, 404)
                return
            self._json(agent)
            return

        self._json({"error": "not found"}, 404)


def start_hub(cfg: "Config", state: "State") -> None:
    """Start the federation hub HTTP server in a daemon thread."""
    global _hub_cfg_ref, _hub_state_ref
    _hub_cfg_ref = cfg
    _hub_state_ref = state

    state.data.setdefault("fleet", {})
    server = HTTPServer((cfg.federation.bind, cfg.federation.port), _HubHandler)
    t = threading.Thread(
        target=server.serve_forever,
        name="agentpulse-federation-hub",
        daemon=True,
    )
    t.start()
    print(
        f"[AgentPulse] federation hub listening on "
        f"http://{cfg.federation.bind}:{cfg.federation.port}/",
        flush=True,
    )
