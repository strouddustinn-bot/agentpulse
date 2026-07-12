"""Durable state: pending approvals, execution history, blocked IPs, baselines.

Stored as JSON. Pending actions get a short id a human approves out-of-band
via the CLI (`agentpulse approve <id>`). History is capped at 200 records.
Blocked IPs store timestamp + duration for auto-expiry.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional

from .models import Decision

HISTORY_MAX = 200


def _pending_id(decision: Decision) -> str:
    raw = f"{decision.action}:{decision.target}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:10]


class State:
    def __init__(self, path: str):
        self.path = path
        self.data: Dict[str, Any] = {
            "pending": {},
            "last_run": None,
            "baselines": {},
            "history": [],
            "blocked_ips": {},
            "alert_cooldowns": {},
        }

    @classmethod
    def load(cls, path: str) -> "State":
        st = cls(path)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    st.data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                pass
        st.data.setdefault("pending", {})
        st.data.setdefault("baselines", {})
        st.data.setdefault("history", [])
        st.data.setdefault("blocked_ips", {})
        st.data.setdefault("alert_cooldowns", {})
        return st

    @property
    def baselines(self) -> Dict[str, Any]:
        return self.data["baselines"]

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2)
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------
    # Pending approval queue
    # ------------------------------------------------------------------

    def queue_pending(self, decision: Decision) -> str:
        pid = _pending_id(decision)
        obs = decision.observation
        self.data["pending"][pid] = {
            "id": pid,
            "action": decision.action,
            "target": decision.target,
            "reason": decision.reason,
            "check": obs.check if obs else "",
            "metadata": dict(obs.metadata) if obs else {},
            "queued_at": time.time(),
        }
        return pid

    def has_pending(self, decision: Decision) -> bool:
        return _pending_id(decision) in self.data["pending"]

    def list_pending(self) -> List[Dict[str, Any]]:
        return list(self.data["pending"].values())

    def get_pending(self, pid: str) -> Optional[Dict[str, Any]]:
        return self.data["pending"].get(pid)

    def pop_pending(self, pid: str) -> Optional[Dict[str, Any]]:
        return self.data["pending"].pop(pid, None)

    # ------------------------------------------------------------------
    # Execution history (circular buffer)
    # ------------------------------------------------------------------

    def record_history(self, entry: Dict[str, Any]) -> None:
        entry.setdefault("ts", time.time())
        history = self.data["history"]
        history.append(entry)
        if len(history) > HISTORY_MAX:
            self.data["history"] = history[-HISTORY_MAX:]

    def list_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(reversed(self.data["history"][-limit:]))

    # ------------------------------------------------------------------
    # Blocked IPs (SSH brute-force)
    # ------------------------------------------------------------------

    def block_ip(self, ip: str, duration_seconds: int, reason: str) -> None:
        self.data["blocked_ips"][ip] = {
            "ip": ip,
            "blocked_at": time.time(),
            "duration_seconds": duration_seconds,
            "reason": reason,
        }

    def unblock_ip(self, ip: str) -> bool:
        return self.data["blocked_ips"].pop(ip, None) is not None

    def is_ip_blocked(self, ip: str) -> bool:
        entry = self.data["blocked_ips"].get(ip)
        if not entry:
            return False
        duration = entry.get("duration_seconds", 0)
        if duration == 0:
            return True  # permanent
        return (time.time() - entry["blocked_at"]) < duration

    def list_blocked_ips(self) -> List[Dict[str, Any]]:
        return list(self.data["blocked_ips"].values())

    def expire_blocked_ips(self) -> List[str]:
        """Remove expired IP blocks. Returns list of unblocked IPs."""
        now = time.time()
        expired = []
        for ip, entry in list(self.data["blocked_ips"].items()):
            duration = entry.get("duration_seconds", 0)
            if duration > 0 and (now - entry["blocked_at"]) >= duration:
                del self.data["blocked_ips"][ip]
                expired.append(ip)
        return expired

    # ------------------------------------------------------------------
    # Alert deduplication cooldowns
    # ------------------------------------------------------------------

    def is_on_cooldown(self, key: str, cooldown_seconds: int = 300) -> bool:
        last = self.data["alert_cooldowns"].get(key)
        if last is None:
            return False
        return (time.time() - last) < cooldown_seconds

    def set_cooldown(self, key: str) -> None:
        self.data["alert_cooldowns"][key] = time.time()

    def clear_cooldown(self, key: str) -> None:
        self.data["alert_cooldowns"].pop(key, None)

    # ------------------------------------------------------------------
    # Bookkeeping
    # ------------------------------------------------------------------

    def mark_run(self) -> None:
        self.data["last_run"] = time.time()
