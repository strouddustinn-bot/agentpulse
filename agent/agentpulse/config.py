"""Configuration loading and validation for AgentPulse.

Config is plain JSON so the agent has zero third-party dependencies.
Validation is strict: unknown modes, bad thresholds, or missing required
fields raise ConfigError rather than silently misbehaving on a server.
"""

from __future__ import annotations

import json
import os
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List

VALID_MODES = ("off", "alert", "ask", "auto")


class ConfigError(ValueError):
    """Raised when a config file is missing required fields or has bad values."""


@dataclass
class DiskCheckConfig:
    mode: str = "alert"
    threshold_percent: float = 90.0
    paths: List[str] = field(default_factory=lambda: ["/"])
    cleanup_globs: List[str] = field(default_factory=list)
    cleanup_older_than_days: float = 3.0


@dataclass
class ServiceCheckConfig:
    mode: str = "ask"
    services: List[str] = field(default_factory=list)


@dataclass
class ProcessCheckConfig:
    mode: str = "alert"
    mem_percent_threshold: float = 85.0


@dataclass
class NotifyConfig:
    type: str = "stdout"  # stdout | webhook
    webhook_url: str = ""


@dataclass
class CheckinConfig:
    endpoint_url: str = ""
    auth_token: str = ""
    timeout_seconds: float = 10.0
    identity_file: str = "/var/lib/agentpulse/identity.json"
    credential_file: str = "/var/lib/agentpulse/agent.credential"
    spool_directory: str = "/var/lib/agentpulse/spool"


@dataclass
class ControlPlaneConfig:
    enabled: bool = False
    base_url: str = ""
    credential_file: str = "/etc/agentpulse/agent.credential"
    spool_directory: str = "/var/lib/agentpulse/control-plane-spool"
    timeout_seconds: int = 10
    local_policy_ceiling: str = "alert"


@dataclass
class BaselineConfig:
    """Statistical baseline learning (per-metric mean/variance, z-score anomalies).

    Advisory only: anomalies raise alerts, never trigger auto-fix.
    """

    enabled: bool = True
    min_samples: int = 20          # warmup before any anomaly can fire
    z_threshold: float = 3.0       # std-devs from the learned mean
    min_abs_deviation: float = 2.0  # floor (pct points) so near-constant metrics don't flap
    ml_enabled: bool = False
    hw_alpha: float = 0.2
    hw_beta: float = 0.1


@dataclass
class Config:
    hostname: str = "auto"
    interval_seconds: int = 60
    state_file: str = "/var/lib/agentpulse/state.json"
    log_file: str = "/var/log/agentpulse/agentpulse.log"
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    checkin: CheckinConfig = field(default_factory=CheckinConfig)
    control_plane: ControlPlaneConfig = field(default_factory=ControlPlaneConfig)
    baseline: BaselineConfig = field(default_factory=BaselineConfig)
    disk: DiskCheckConfig = field(default_factory=DiskCheckConfig)
    service: ServiceCheckConfig = field(default_factory=ServiceCheckConfig)
    process: ProcessCheckConfig = field(default_factory=ProcessCheckConfig)

    def resolved_hostname(self) -> str:
        if self.hostname and self.hostname != "auto":
            return self.hostname
        return os.uname().nodename


def _check_mode(name: str, value: Any) -> str:
    if value not in VALID_MODES:
        raise ConfigError(
            f"{name}.mode must be one of {VALID_MODES}, got {value!r}"
        )
    return value


def _positive_number(name: str, value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"{name} must be a positive number, got {value!r}")
    return float(value)


def _str_list(name: str, value: Any) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ConfigError(f"{name} must be a list of strings, got {value!r}")
    return list(value)


def from_dict(data: Dict[str, Any]) -> Config:
    """Build and validate a Config from a parsed JSON dict."""
    if not isinstance(data, dict):
        raise ConfigError("config root must be a JSON object")

    cfg = Config()

    if "hostname" in data:
        if not isinstance(data["hostname"], str):
            raise ConfigError("hostname must be a string")
        cfg.hostname = data["hostname"]

    if "interval_seconds" in data:
        cfg.interval_seconds = int(_positive_number("interval_seconds", data["interval_seconds"]))

    if "state_file" in data:
        cfg.state_file = str(data["state_file"])
    if "log_file" in data:
        cfg.log_file = str(data["log_file"])

    n = data.get("notify", {})
    if n:
        ntype = n.get("type", "stdout")
        if ntype not in ("stdout", "webhook"):
            raise ConfigError(f"notify.type must be 'stdout' or 'webhook', got {ntype!r}")
        url = n.get("webhook_url", "")
        if ntype == "webhook":
            if not url:
                raise ConfigError("notify.webhook_url is required when notify.type is 'webhook'")
            # The URL is handed to urllib verbatim; only web schemes make sense
            # (file:// or ftp:// here is a misconfiguration at best).
            if not str(url).startswith(("http://", "https://")):
                raise ConfigError(
                    f"notify.webhook_url must be an http:// or https:// URL, got {url!r}"
                )
        cfg.notify = NotifyConfig(type=ntype, webhook_url=str(url))

    cin = data.get("checkin", {})
    if cin:
        endpoint_url = str(cin.get("endpoint_url", ""))
        if endpoint_url and not endpoint_url.startswith(("http://", "https://")):
            raise ConfigError(
                f"checkin.endpoint_url must be an http:// or https:// URL, got {endpoint_url!r}"
            )
        cfg.checkin = CheckinConfig(
            endpoint_url=endpoint_url,
            auth_token=str(cin.get("auth_token", "")),
            timeout_seconds=_positive_number(
                "checkin.timeout_seconds", cin.get("timeout_seconds", 10.0)
            ),
            identity_file=str(cin.get("identity_file", "/var/lib/agentpulse/identity.json")),
            credential_file=str(cin.get("credential_file", "/var/lib/agentpulse/agent.credential")),
            spool_directory=str(cin.get("spool_directory", "/var/lib/agentpulse/spool")),
        )

    cp = data.get("control_plane", {})
    if cp:
        if not isinstance(cp, dict):
            raise ConfigError("control_plane must be a JSON object")
        enabled = cp.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ConfigError("control_plane.enabled must be true/false")
        base_url = str(cp.get("base_url", "")).rstrip("/")
        if enabled:
            parsed = urllib.parse.urlparse(base_url)
            if not base_url or parsed.scheme not in ("http", "https"):
                raise ConfigError("control_plane.base_url must be an absolute HTTP(S) URL")
            if parsed.scheme != "https" and parsed.hostname not in (
                "127.0.0.1",
                "localhost",
                "::1",
            ):
                raise ConfigError("control_plane.base_url must use HTTPS outside localhost")
        ceiling = cp.get("local_policy_ceiling", "alert")
        if ceiling not in VALID_MODES:
            raise ConfigError("control_plane.local_policy_ceiling must be a valid mode")
        cfg.control_plane = ControlPlaneConfig(
            enabled=enabled,
            base_url=base_url,
            credential_file=str(
                cp.get("credential_file", "/etc/agentpulse/agent.credential")
            ),
            spool_directory=str(
                cp.get(
                    "spool_directory",
                    "/var/lib/agentpulse/control-plane-spool",
                )
            ),
            timeout_seconds=int(
                _positive_number(
                    "control_plane.timeout_seconds", cp.get("timeout_seconds", 10)
                )
            ),
            local_policy_ceiling=str(ceiling),
        )

    b = data.get("baseline", {})
    if b:
        enabled = b.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ConfigError("baseline.enabled must be true/false")
        ml_enabled = b.get("ml_enabled", False)
        if not isinstance(ml_enabled, bool):
            raise ConfigError("baseline.ml_enabled must be true/false")
        cfg.baseline = BaselineConfig(
            enabled=enabled,
            min_samples=int(_positive_number("baseline.min_samples", b.get("min_samples", 20))),
            z_threshold=_positive_number("baseline.z_threshold", b.get("z_threshold", 3.0)),
            min_abs_deviation=_positive_number("baseline.min_abs_deviation", b.get("min_abs_deviation", 2.0)),
            ml_enabled=ml_enabled,
            hw_alpha=_positive_number("baseline.hw_alpha", b.get("hw_alpha", 0.2)),
            hw_beta=_positive_number("baseline.hw_beta", b.get("hw_beta", 0.1)),
        )

    checks = data.get("checks", {})
    if not isinstance(checks, dict):
        raise ConfigError("checks must be a JSON object")

    if "disk" in checks:
        d = checks["disk"]
        cfg.disk = DiskCheckConfig(
            mode=_check_mode("checks.disk", d.get("mode", "alert")),
            threshold_percent=_positive_number(
                "checks.disk.threshold_percent", d.get("threshold_percent", 90)
            ),
            paths=_str_list("checks.disk.paths", d.get("paths", ["/"])),
            cleanup_globs=_str_list("checks.disk.cleanup_globs", d.get("cleanup_globs", [])),
            cleanup_older_than_days=_positive_number(
                "checks.disk.cleanup_older_than_days", d.get("cleanup_older_than_days", 3)
            ),
        )
        if cfg.disk.threshold_percent > 100:
            raise ConfigError("checks.disk.threshold_percent cannot exceed 100")
        if cfg.disk.mode == "auto" and not cfg.disk.cleanup_globs:
            raise ConfigError(
                "checks.disk.mode is 'auto' but no cleanup_globs are configured; "
                "auto-fix has nothing safe to do"
            )

    if "service" in checks:
        s = checks["service"]
        cfg.service = ServiceCheckConfig(
            mode=_check_mode("checks.service", s.get("mode", "ask")),
            services=_str_list("checks.service.services", s.get("services", [])),
        )

    if "process" in checks:
        p = checks["process"]
        mode = _check_mode("checks.process", p.get("mode", "alert"))
        cfg.process = ProcessCheckConfig(
            mode=mode,
            mem_percent_threshold=_positive_number(
                "checks.process.mem_percent_threshold", p.get("mem_percent_threshold", 85)
            ),
        )
        if cfg.process.mem_percent_threshold > 100:
            raise ConfigError("checks.process.mem_percent_threshold cannot exceed 100")

    return cfg


def load(path: str) -> Config:
    """Load and validate config from a JSON file path."""
    if not os.path.exists(path):
        raise ConfigError(f"config file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config file is not valid JSON: {exc}") from exc
    return from_dict(data)
