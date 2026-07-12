"""Configuration loading and validation for AgentPulse.

Config is plain JSON so the agent has zero third-party dependencies.
Validation is strict: unknown modes, bad thresholds, or missing required
fields raise ConfigError rather than silently misbehaving on a server.
"""

from __future__ import annotations

import json
import os
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
    kill_allowed_names: List[str] = field(default_factory=list)
    kill_grace_seconds: float = 10.0
    never_kill: List[str] = field(
        default_factory=lambda: ["systemd", "init", "kthreadd", "sshd", "kernel"]
    )


@dataclass
class SshCheckConfig:
    mode: str = "alert"
    log_file: str = ""  # empty = auto-detect
    failure_threshold: int = 5
    window_seconds: int = 60
    block_duration_seconds: int = 3600  # 0 = permanent
    never_block: List[str] = field(default_factory=list)


@dataclass
class NotifyChannel:
    type: str = "stdout"
    # webhook
    webhook_url: str = ""
    # email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    from_address: str = ""
    to_addresses: List[str] = field(default_factory=list)
    use_tls: bool = True
    # telegram
    bot_token: str = ""
    chat_id: str = ""


@dataclass
class NotifyConfig:
    channels: List[NotifyChannel] = field(
        default_factory=lambda: [NotifyChannel(type="stdout")]
    )


@dataclass
class BaselineConfig:
    enabled: bool = True
    min_samples: int = 20
    z_threshold: float = 3.0
    min_abs_deviation: float = 2.0
    ml_enabled: bool = True
    hw_alpha: float = 0.2   # Holt-Winters level smoothing
    hw_beta: float = 0.1    # Holt-Winters trend smoothing


@dataclass
class DashboardConfig:
    enabled: bool = False
    port: int = 8765
    bind: str = "127.0.0.1"


@dataclass
class FederationConfig:
    enabled: bool = False
    mode: str = "spoke"      # "spoke" | "hub" | "both"
    hub_url: str = ""
    secret: str = ""
    port: int = 8766
    bind: str = "0.0.0.0"
    push_interval_seconds: int = 60


@dataclass
class Config:
    hostname: str = "auto"
    interval_seconds: int = 60
    state_file: str = "/var/lib/agentpulse/state.json"
    log_file: str = "/var/log/agentpulse/agentpulse.log"
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    baseline: BaselineConfig = field(default_factory=BaselineConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    federation: FederationConfig = field(default_factory=FederationConfig)
    disk: DiskCheckConfig = field(default_factory=DiskCheckConfig)
    service: ServiceCheckConfig = field(default_factory=ServiceCheckConfig)
    process: ProcessCheckConfig = field(default_factory=ProcessCheckConfig)
    ssh: SshCheckConfig = field(default_factory=SshCheckConfig)

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


def _nonneg_number(name: str, value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ConfigError(f"{name} must be a non-negative number, got {value!r}")
    return float(value)


def _str_list(name: str, value: Any) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ConfigError(f"{name} must be a list of strings, got {value!r}")
    return list(value)


def _parse_notify_channel(raw: Dict[str, Any], prefix: str) -> NotifyChannel:
    ctype = raw.get("type", "stdout")
    valid_types = ("stdout", "webhook", "email", "telegram")
    if ctype not in valid_types:
        raise ConfigError(f"{prefix}.type must be one of {valid_types}, got {ctype!r}")
    ch = NotifyChannel(type=ctype)
    if ctype == "webhook":
        url = raw.get("webhook_url", "")
        if not url:
            raise ConfigError(f"{prefix}.webhook_url is required when type is 'webhook'")
        ch.webhook_url = str(url)
    elif ctype == "email":
        for required in ("smtp_host", "from_address"):
            if not raw.get(required):
                raise ConfigError(f"{prefix}.{required} is required when type is 'email'")
        if not raw.get("to_addresses"):
            raise ConfigError(f"{prefix}.to_addresses is required when type is 'email'")
        ch.smtp_host = str(raw.get("smtp_host", ""))
        ch.smtp_port = int(raw.get("smtp_port", 587))
        ch.smtp_user = str(raw.get("smtp_user", ""))
        ch.smtp_password = str(raw.get("smtp_password", ""))
        ch.from_address = str(raw.get("from_address", ""))
        ch.to_addresses = _str_list(f"{prefix}.to_addresses", raw.get("to_addresses", []))
        ch.use_tls = bool(raw.get("use_tls", True))
    elif ctype == "telegram":
        for required in ("bot_token", "chat_id"):
            if not raw.get(required):
                raise ConfigError(f"{prefix}.{required} is required when type is 'telegram'")
        ch.bot_token = str(raw.get("bot_token", ""))
        ch.chat_id = str(raw.get("chat_id", ""))
    return ch


def _parse_notify(raw: Any) -> NotifyConfig:
    if raw is None:
        return NotifyConfig()
    if not isinstance(raw, dict):
        raise ConfigError("notify must be a JSON object")

    # New multi-channel format: {"channels": [...]}
    if "channels" in raw:
        channels_raw = raw["channels"]
        if not isinstance(channels_raw, list):
            raise ConfigError("notify.channels must be a list")
        channels = [
            _parse_notify_channel(ch, f"notify.channels[{i}]")
            for i, ch in enumerate(channels_raw)
        ]
        return NotifyConfig(channels=channels)

    # Legacy single-channel format: {"type": "...", "webhook_url": "..."}
    return NotifyConfig(channels=[_parse_notify_channel(raw, "notify")])


def from_dict(data: Dict[str, Any]) -> Config:
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

    cfg.notify = _parse_notify(data.get("notify"))

    b = data.get("baseline", {})
    if b:
        enabled = b.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ConfigError("baseline.enabled must be true/false")
        ml_enabled = b.get("ml_enabled", True)
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

    d = data.get("dashboard", {})
    if d:
        enabled = d.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ConfigError("dashboard.enabled must be true/false")
        cfg.dashboard = DashboardConfig(
            enabled=enabled,
            port=int(_positive_number("dashboard.port", d.get("port", 8765))),
            bind=str(d.get("bind", "127.0.0.1")),
        )

    f = data.get("federation", {})
    if f:
        enabled = f.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ConfigError("federation.enabled must be true/false")
        fmode = f.get("mode", "spoke")
        if fmode not in ("spoke", "hub", "both"):
            raise ConfigError("federation.mode must be 'spoke', 'hub', or 'both'")
        cfg.federation = FederationConfig(
            enabled=enabled,
            mode=fmode,
            hub_url=str(f.get("hub_url", "")),
            secret=str(f.get("secret", "")),
            port=int(_positive_number("federation.port", f.get("port", 8766))),
            bind=str(f.get("bind", "0.0.0.0")),
            push_interval_seconds=int(_positive_number(
                "federation.push_interval_seconds", f.get("push_interval_seconds", 60)
            )),
        )

    checks = data.get("checks", {})
    if not isinstance(checks, dict):
        raise ConfigError("checks must be a JSON object")

    if "disk" in checks:
        dk = checks["disk"]
        cfg.disk = DiskCheckConfig(
            mode=_check_mode("checks.disk", dk.get("mode", "alert")),
            threshold_percent=_positive_number(
                "checks.disk.threshold_percent", dk.get("threshold_percent", 90)
            ),
            paths=_str_list("checks.disk.paths", dk.get("paths", ["/"])),
            cleanup_globs=_str_list("checks.disk.cleanup_globs", dk.get("cleanup_globs", [])),
            cleanup_older_than_days=_positive_number(
                "checks.disk.cleanup_older_than_days", dk.get("cleanup_older_than_days", 3)
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
        cfg.process = ProcessCheckConfig(
            mode=_check_mode("checks.process", p.get("mode", "alert")),
            mem_percent_threshold=_positive_number(
                "checks.process.mem_percent_threshold", p.get("mem_percent_threshold", 85)
            ),
            kill_allowed_names=_str_list(
                "checks.process.kill_allowed_names", p.get("kill_allowed_names", [])
            ),
            kill_grace_seconds=_nonneg_number(
                "checks.process.kill_grace_seconds", p.get("kill_grace_seconds", 10)
            ),
            never_kill=_str_list(
                "checks.process.never_kill",
                p.get("never_kill", ["systemd", "init", "kthreadd", "sshd", "kernel"]),
            ),
        )
        if cfg.process.mem_percent_threshold > 100:
            raise ConfigError("checks.process.mem_percent_threshold cannot exceed 100")

    if "ssh" in checks:
        sh = checks["ssh"]
        threshold = sh.get("failure_threshold", 5)
        if not isinstance(threshold, int) or threshold < 1:
            raise ConfigError("checks.ssh.failure_threshold must be a positive integer")
        cfg.ssh = SshCheckConfig(
            mode=_check_mode("checks.ssh", sh.get("mode", "alert")),
            log_file=str(sh.get("log_file", "")),
            failure_threshold=threshold,
            window_seconds=int(_positive_number(
                "checks.ssh.window_seconds", sh.get("window_seconds", 60)
            )),
            block_duration_seconds=int(_nonneg_number(
                "checks.ssh.block_duration_seconds", sh.get("block_duration_seconds", 3600)
            )),
            never_block=_str_list("checks.ssh.never_block", sh.get("never_block", [])),
        )

    return cfg


def load(path: str) -> Config:
    if not os.path.exists(path):
        raise ConfigError(f"config file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config file is not valid JSON: {exc}") from exc
    return from_dict(data)
