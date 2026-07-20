"""Durable, redacted, FIFO JSON event spool."""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .redaction import redact


class SpoolFull(RuntimeError):
    """The queue has reached its configured capacity."""


class SpoolCorruptEntry(ValueError):
    """A queued file failed envelope or hash validation."""


class SpoolPermanentFailure(RuntimeError):
    """The event cannot succeed after retry and must leave the FIFO queue."""


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Spool:
    def __init__(
        self,
        directory: os.PathLike[str] | str,
        *,
        max_events: int = 1000,
        max_age_seconds: float = 7 * 24 * 3600,
        max_event_bytes: int = 256 * 1024,
        max_auxiliary_files: int = 1000,
        max_auxiliary_bytes: int = 256 * 1024 * 1024,
    ) -> None:
        if (
            max_events < 1
            or max_age_seconds <= 0
            or max_event_bytes < 1
            or max_auxiliary_files < 1
            or max_auxiliary_bytes < 1
        ):
            raise ValueError("spool limits must be positive")
        self.directory = Path(directory)
        self.quarantine = self.directory / "quarantine"
        self.acknowledged = self.directory / "acknowledged"
        self.max_events = max_events
        self.max_age_seconds = max_age_seconds
        self.max_event_bytes = max_event_bytes
        self.max_auxiliary_files = max_auxiliary_files
        self.max_auxiliary_bytes = max_auxiliary_bytes
        self.lock_file = self.directory / ".spool.lock"
        self._ensure_dirs()

    def enqueue(self, event_type: str, payload: Any, *, event_id: Optional[str] = None) -> str:
        with self._locked():
            self._quarantine_expired_unlocked()
            event_id = event_id or str(uuid.uuid4())
            pending = self._list_pending_unlocked()
            if (self.acknowledged / f"{event_id}.ack").exists() or any(
                item["event_id"] == event_id for item in pending
            ):
                raise ValueError("event_id is already queued")
            if len(pending) >= self.max_events:
                raise SpoolFull("spool queue is full; caller must apply backpressure")
            safe_payload = redact(payload)
            event = {
                "event_id": event_id,
                "event_type": str(event_type),
                "created_at": _timestamp(),
                "attempts": 0,
                "payload": safe_payload,
                "payload_hash": _hash_payload(safe_payload),
            }
            encoded = json.dumps(
                event, sort_keys=True, separators=(",", ":"), default=str
            ).encode()
            if len(encoded) > self.max_event_bytes:
                raise ValueError("spool event exceeds size limit")
            # UUID is unique; the timestamp prefix and event ID provide stable
            # FIFO ordering without requiring a mutable index file.
            filename = f"{time.time_ns():020d}-{event_id}.json"
            self._atomic_write(self.directory / filename, event)
            self._prune_auxiliary_unlocked()
            return event_id

    def list_pending(self) -> List[Dict[str, Any]]:
        with self._locked():
            return self._list_pending_unlocked()

    def _list_pending_unlocked(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                event = self._read_valid(path)
            except SpoolCorruptEntry:
                self._quarantine(path)
                continue
            if self._is_expired(event, path):
                self._quarantine(path)
                continue
            items.append(event)
        self._prune_auxiliary_unlocked()
        return items

    def replay(
        self,
        acknowledge: Callable[[Dict[str, Any]], bool],
        *,
        max_events: Optional[int] = None,
        propagate_exceptions: tuple[type[BaseException], ...] = (),
    ) -> int:
        with self._locked():
            delivered = 0
            attempted = 0
            for path in sorted(self.directory.glob("*.json")):
                try:
                    event = self._read_valid(path)
                except SpoolCorruptEntry:
                    self._quarantine(path)
                    continue
                if self._is_expired(event, path):
                    self._quarantine(path)
                    continue
                if max_events is not None and attempted >= max_events:
                    break
                attempted += 1
                try:
                    accepted = bool(acknowledge(event))
                except SpoolPermanentFailure:
                    self._quarantine(path)
                    continue
                except Exception as exc:
                    if isinstance(exc, propagate_exceptions):
                        raise
                    accepted = False
                if accepted:
                    path.unlink(missing_ok=True)
                    marker = self.acknowledged / f"{event['event_id']}.ack"
                    self._atomic_write(
                        marker,
                        {
                            "event_id": event["event_id"],
                            "acknowledged_at": _timestamp(),
                        },
                    )
                    delivered += 1
                else:
                    event["attempts"] = int(event.get("attempts", 0)) + 1
                    self._atomic_write(path, event)
                    break
            self._prune_auxiliary_unlocked()
            return delivered

    def _read_valid(self, path: Path) -> Dict[str, Any]:
        try:
            if path.stat().st_size > self.max_event_bytes:
                raise ValueError("spool entry exceeded size limit")
            data = json.loads(path.read_text(encoding="utf-8"))
            required = {"event_id", "event_type", "created_at", "attempts", "payload", "payload_hash"}
            if not isinstance(data, dict) or set(data) != required:
                raise ValueError("invalid event envelope")
            if data["payload_hash"] != _hash_payload(data["payload"]):
                raise ValueError("payload hash mismatch")
            return data
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise SpoolCorruptEntry(str(exc)) from exc

    def _is_expired(self, event: Dict[str, Any], path: Optional[Path] = None) -> bool:
        try:
            created = datetime.fromisoformat(str(event["created_at"]).replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError, OverflowError):
            return True
        modified = path.stat().st_mtime if path is not None else created
        return min(created, modified) < time.time() - self.max_age_seconds

    def _quarantine_expired_unlocked(self) -> None:
        # list_pending performs validation and age quarantine.
        self._list_pending_unlocked()

    def _prune_auxiliary_unlocked(self) -> None:
        cutoff = time.time() - self.max_age_seconds
        for directory in (self.acknowledged, self.quarantine):
            files = sorted(
                (path for path in directory.iterdir() if path.is_file()),
                key=lambda path: path.stat().st_mtime,
            )
            for path in list(files):
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
                    files.remove(path)
            while len(files) > self.max_auxiliary_files:
                files.pop(0).unlink(missing_ok=True)
            total = sum(path.stat().st_size for path in files)
            while files and total > self.max_auxiliary_bytes:
                oldest = files.pop(0)
                total -= oldest.stat().st_size
                oldest.unlink(missing_ok=True)

    def _quarantine(self, path: Path) -> None:
        self.quarantine.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination = self.quarantine / path.name
        if destination.exists():
            destination = self.quarantine / f"{path.stem}-{uuid.uuid4().hex}.json"
        try:
            os.replace(path, destination)
            os.chmod(destination, 0o600)
            os.utime(destination, None)
        except FileNotFoundError:
            pass

    def _ensure_dirs(self) -> None:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        self.quarantine.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.quarantine, 0o700)
        self.acknowledged.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.acknowledged, 0o700)

    @contextmanager
    def _locked(self):
        self._ensure_dirs()
        fd = os.open(self.lock_file, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @staticmethod
    def _atomic_write(path: Path, event: Dict[str, Any]) -> None:
        fd, temporary = tempfile.mkstemp(prefix=".spool-", dir=str(path.parent))
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                fd = -1
                json.dump(event, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        except Exception:
            if fd >= 0:
                os.close(fd)
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise


__all__ = ["Spool", "SpoolCorruptEntry", "SpoolFull", "SpoolPermanentFailure"]
