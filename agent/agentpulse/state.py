"""Durable state: pending ask-first approvals and last-run bookkeeping.

Stored as JSON. Pending actions get a short id a human approves out-of-band
via the CLI (`agentpulse approve <id>`).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional

from .models import Decision


def _pending_id(decision: Decision) -> str:
    raw = f"{decision.action}:{decision.target}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:10]


class State:
    def __init__(self, path: str):
        self.path = path
        self.data: Dict[str, Any] = {"pending": {}, "last_run": None, "baselines": {}}

    @classmethod
    def load(cls, path: str) -> "State":
        st = cls(path)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    st.data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                st.data = {"pending": {}, "last_run": None, "baselines": {}}
        st.data.setdefault("pending", {})
        st.data.setdefault("baselines", {})
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

    def pop_pending(self, pid: str) -> Optional[Dict[str, Any]]:
        return self.data["pending"].pop(pid, None)

    def mark_run(self) -> None:
        self.data["last_run"] = time.time()
