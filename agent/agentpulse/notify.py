"""Notifications. stdout always works; webhook uses urllib (stdlib, zero deps)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .config import NotifyConfig


class Notifier:
    def __init__(self, cfg: NotifyConfig, opener=None):
        self.cfg = cfg
        # opener injectable for tests; defaults to urllib.
        self._opener = opener or urllib.request.urlopen

    def send(self, title: str, body: str) -> bool:
        """Return True if delivered. stdout never fails."""
        line = f"[AgentPulse] {title}\n{body}"
        if self.cfg.type == "stdout" or not self.cfg.webhook_url:
            print(line, flush=True)
            return True
        payload = json.dumps({"text": line}).encode("utf-8")
        req = urllib.request.Request(
            self.cfg.webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener(req, timeout=10) as resp:  # noqa: S310 (trusted user URL)
                return 200 <= getattr(resp, "status", 200) < 300
        except (urllib.error.URLError, OSError) as exc:
            # Never let a failed webhook crash the agent; fall back to stdout.
            print(f"{line}\n(webhook delivery failed: {exc})", flush=True)
            return False
