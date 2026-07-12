"""Append-only structured audit events for the agent."""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .redaction import redact


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class AuditLog:
    def __init__(self, path: os.PathLike[str] | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        if self.path.exists():
            os.chmod(self.path, 0o600)

    def append(
        self,
        *,
        agent_id: str,
        event_type: str,
        correlation_id: str,
        actor: str,
        reason: str,
        policy: Dict[str, Any],
        evidence_before: Dict[str, Any],
        action: Dict[str, Any],
        result: Dict[str, Any],
        evidence_after: Dict[str, Any],
        agent_version: str,
        config_version: str,
    ) -> Dict[str, Any]:
        entry = redact({
            "event_id": str(uuid.uuid4()),
            "timestamp": _now(),
            "agent_id": agent_id,
            "event_type": event_type,
            "correlation_id": correlation_id,
            "actor": actor,
            "reason": reason,
            "policy": policy,
            "evidence_before": evidence_before,
            "action": action,
            "result": result,
            "evidence_after": evidence_after,
            "agent_version": agent_version,
            "config_version": config_version,
        })
        serialized = json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n"
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as handle:
                fd = -1
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            if fd >= 0:
                os.close(fd)
        return entry

    def read(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        entries: List[Dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    entries.append(value)
        return entries


__all__ = ["AuditLog"]
