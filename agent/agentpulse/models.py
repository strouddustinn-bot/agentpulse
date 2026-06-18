"""Shared data models for observations and policy decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Observation:
    """A single thing the agent noticed about the host.

    check: "disk" | "service" | "process"
    target: the specific resource (mount path, service name, "pid:1234 name")
    breached: True if it crossed the configured threshold / failed state
    value: the measured value (percent used, etc.) for context
    detail: human-readable description
    metadata: structured extras used by remediation (e.g. cleanup globs)
    """

    check: str
    target: str
    breached: bool
    value: float = 0.0
    detail: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Decision:
    """What policy decided to do about an Observation."""

    action: str  # "disk_cleanup" | "service_restart" | "process_alert" | "none"
    target: str
    mode_effective: str  # mode actually applied after safety clamps
    execute: bool  # act automatically now
    requires_approval: bool  # queue for human approval
    reason: str
    clamped_from: Optional[str] = None  # original mode if a safety clamp changed it
    observation: Optional[Observation] = None
