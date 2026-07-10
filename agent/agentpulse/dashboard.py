"""Lightweight HTTP dashboard server (stdlib only, zero deps).

Runs in a daemon thread so it never blocks the main agent loop.
Exposes:
    GET /              — HTML dashboard UI (auto-refreshes every 30s)
    GET /api/state     — JSON state snapshot (pending, history, blocked IPs)
    GET /api/status    — JSON health summary
    GET /api/fleet     — JSON fleet-wide state (hub mode only)

Start it with dashboard.start(cfg, state).
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

# Shared references updated by the runner each cycle.
_cfg_ref = None
_state_ref = None

_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AgentPulse Dashboard</title>
<style>
  :root{--bg:#0f1117;--card:#1a1d27;--accent:#7c6af7;--ok:#22c55e;--warn:#f59e0b;--err:#ef4444;--text:#e2e8f0;--muted:#64748b}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;line-height:1.6}
  header{background:var(--card);border-bottom:1px solid #2d3048;padding:16px 24px;display:flex;align-items:center;gap:12px}
  header h1{font-size:18px;font-weight:700;color:var(--accent)}
  header .badge{background:var(--accent);color:#fff;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600}
  .container{max-width:1200px;margin:24px auto;padding:0 24px;display:grid;gap:20px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}
  .card{background:var(--card);border-radius:12px;padding:20px;border:1px solid #2d3048}
  .card h2{font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:14px}
  .stat{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #2d3048}
  .stat:last-child{border-bottom:none}
  .stat-label{color:var(--muted);font-size:13px}
  .stat-value{font-weight:600;font-size:14px}
  .ok{color:var(--ok)} .warn{color:var(--warn)} .err{color:var(--err)}
  .entry{padding:10px 0;border-bottom:1px solid #2d3048;font-size:13px}
  .entry:last-child{border-bottom:none}
  .entry .ts{color:var(--muted);font-size:11px}
  .entry .action{display:inline-block;background:#2d3048;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:600;margin-right:6px}
  .entry.ok .action{color:var(--ok)} .entry.warn .action{color:var(--warn)} .entry.err .action{color:var(--err)}
  .empty{color:var(--muted);font-size:13px;text-align:center;padding:20px 0}
  .refresh{margin-left:auto;font-size:12px;color:var(--muted)}
  .fleet-agent{padding:10px 0;border-bottom:1px solid #2d3048;font-size:13px}
  .fleet-agent:last-child{border-bottom:none}
  .fleet-agent .hostname{font-weight:600}
  .fleet-agent .last-seen{color:var(--muted);font-size:11px}
  .fleet-agent.stale .hostname{color:var(--warn)}
</style>
</head>
<body>
<header>
  <h1>AgentPulse</h1>
  <span class="badge">LIVE</span>
  <span class="refresh" id="refresh-ts">Refreshing…</span>
</header>
<div class="container" id="root">Loading…</div>
<script>
const fmt = ts => ts ? new Date(ts*1000).toLocaleString() : '—';
const ago = ts => {
  if(!ts) return '—';
  const s = Math.floor(Date.now()/1000 - ts);
  if(s<60) return s+'s ago';
  if(s<3600) return Math.floor(s/60)+'m ago';
  return Math.floor(s/3600)+'h ago';
};
const outcomeClass = o => o==='succeeded'||o==='executed_unverified'||o==='simulated_only'?'ok':o==='escalated'||o==='blocked'?'warn':'err';

async function load() {
  const [stateRes, fleetRes] = await Promise.all([
    fetch('/api/state').then(r=>r.json()).catch(()=>null),
    fetch('/api/fleet').then(r=>r.json()).catch(()=>null),
  ]);
  if(!stateRes){document.getElementById('root').innerHTML='<p class="empty">Failed to load state.</p>';return;}
  const {last_run, pending, history, blocked_ips} = stateRes;

  let html = '';

  // Status card
  html += `<div class="card">
    <h2>Status</h2>
    <div class="stat"><span class="stat-label">Last run</span><span class="stat-value">${ago(last_run)}</span></div>
    <div class="stat"><span class="stat-label">Pending approvals</span><span class="stat-value ${pending.length?'warn':'ok'}">${pending.length}</span></div>
    <div class="stat"><span class="stat-label">Blocked IPs</span><span class="stat-value ${blocked_ips.length?'warn':'ok'}">${blocked_ips.length}</span></div>
  </div>`;

  // Pending approvals card
  html += `<div class="card"><h2>Pending Approvals</h2>`;
  if(pending.length===0){
    html += '<div class="empty">No actions waiting for approval.</div>';
  } else {
    pending.forEach(p=>{
      html += `<div class="entry warn">
        <span class="action">${p.action}</span>
        <strong>${p.target}</strong>
        <div class="ts">Queued ${ago(p.queued_at)} — ID: <code>${p.id}</code></div>
        <div>${p.reason||''}</div>
      </div>`;
    });
  }
  html += '</div>';

  // History card
  html += `<div class="card" style="grid-column:1/-1"><h2>Recent Activity</h2>`;
  if(!history||history.length===0){
    html += '<div class="empty">No activity recorded yet.</div>';
  } else {
    history.slice(0,20).forEach(h=>{
      const cls = outcomeClass(h.outcome);
      html += `<div class="entry ${cls}">
        <span class="action">${h.action}</span>
        <strong>${h.target}</strong>
        <span class="ts" style="float:right">${fmt(h.ts)}</span>
        <div style="margin-top:4px;color:var(--muted)">${h.outcome} ${h.verified!=null?'· verified='+h.verified:''}</div>
        ${h.notes&&h.notes.length?'<div style="font-size:12px;color:var(--muted)">'+h.notes.join('; ')+'</div>':''}
      </div>`;
    });
  }
  html += '</div>';

  // Blocked IPs card
  if(blocked_ips&&blocked_ips.length>0){
    html += `<div class="card"><h2>Blocked IPs</h2>`;
    blocked_ips.forEach(b=>{
      const expires = b.duration_seconds>0 ? fmt(b.blocked_at+b.duration_seconds) : 'permanent';
      html += `<div class="entry warn">
        <strong>${b.ip}</strong>
        <span class="ts">Blocked ${ago(b.blocked_at)} · expires ${expires}</span>
        <div style="font-size:12px;color:var(--muted)">${b.reason||''}</div>
      </div>`;
    });
    html += '</div>';
  }

  // Fleet card (hub mode)
  if(fleetRes && Object.keys(fleetRes).length>0){
    html += `<div class="card"><h2>Fleet (${Object.keys(fleetRes).length} agents)</h2>`;
    Object.values(fleetRes).forEach(agent=>{
      const stale = !agent.last_seen || (Date.now()/1000 - agent.last_seen) > 300;
      html += `<div class="fleet-agent ${stale?'stale':''}">
        <span class="hostname">${agent.hostname||agent.agent_id}</span>
        <span class="last-seen"> · last seen ${ago(agent.last_seen)}</span>
        ${(agent.state&&agent.state.blocked_ips&&agent.state.blocked_ips.length)?'<span class="warn"> · '+agent.state.blocked_ips.length+' blocked IPs</span>':''}
        ${(agent.state&&agent.state.pending&&agent.state.pending.length)?'<span class="warn"> · '+agent.state.pending.length+' pending</span>':''}
      </div>`;
    });
    html += '</div>';
  }

  document.getElementById('root').innerHTML = html;
  document.getElementById('refresh-ts').textContent = 'Updated '+new Date().toLocaleTimeString();
}

load();
setInterval(load, 30000);
</script>
</body>
</html>
"""


class _DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # silence default request logging

    def _json(self, data, code=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, body: str):
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        state: "State" = _state_ref
        cfg: "Config" = _cfg_ref

        if self.path in ("/", "/index.html"):
            self._html(_DASHBOARD_HTML)
            return

        if self.path == "/api/state":
            if not state:
                self._json({"error": "state not initialised"}, 503)
                return
            data = {
                "last_run": state.data.get("last_run"),
                "pending": state.list_pending(),
                "history": state.list_history(50),
                "blocked_ips": state.list_blocked_ips(),
            }
            self._json(data)
            return

        if self.path == "/api/status":
            data = {
                "ok": True,
                "ts": time.time(),
                "hostname": cfg.resolved_hostname() if cfg else "unknown",
            }
            self._json(data)
            return

        if self.path == "/api/fleet":
            fleet = {}
            if state:
                fleet = state.data.get("fleet", {})
            self._json(fleet)
            return

        self.send_response(404)
        self.end_headers()


def start(cfg: "Config", state: "State") -> None:
    """Start the dashboard HTTP server in a daemon thread."""
    global _cfg_ref, _state_ref
    _cfg_ref = cfg
    _state_ref = state

    server = HTTPServer((cfg.dashboard.bind, cfg.dashboard.port), _DashboardHandler)
    t = threading.Thread(
        target=server.serve_forever,
        name="agentpulse-dashboard",
        daemon=True,
    )
    t.start()
    print(
        f"[AgentPulse] dashboard listening on "
        f"http://{cfg.dashboard.bind}:{cfg.dashboard.port}/",
        flush=True,
    )
