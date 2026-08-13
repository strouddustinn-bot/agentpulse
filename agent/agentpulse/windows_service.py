"""Safe Windows service installation and control for AgentPulse.

WinSW provides the actual Windows Service Control Manager process. AgentPulse
generates a bounded configuration beside a checksum-verified WinSW executable;
it never builds an ``sc create`` shell command around user-controlled text.
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

WINSW_VERSION = "2.12.0"
WINSW_X64_URL = (
    "https://github.com/winsw/winsw/releases/download/"
    f"v{WINSW_VERSION}/WinSW-x64.exe"
)
WINSW_X64_SHA256 = "05b82d46ad331cc16bdc00de5c6332c1ef818df8ceefcd49c726553209b3a0da"

DEFAULT_SERVICE_ID = "AgentPulse"
DEFAULT_DISPLAY_NAME = "AgentPulse Agent"
_SERVICE_ID_RE = re.compile(r"^[A-Za-z0-9]+$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")

CompletedRun = subprocess.CompletedProcess[str]
RunFn = Callable[[List[str]], CompletedRun]
AdminFn = Callable[[], bool]


class WindowsServiceError(RuntimeError):
    """Raised when Windows service lifecycle work cannot complete safely."""


@dataclass
class WindowsServiceInstallResult:
    service_id: str
    display_name: str
    agent_bin: str
    config_path: str
    wrapper_path: str
    wrapper_config_path: str
    log_dir: str
    dry_run: bool
    steps: List[str] = field(default_factory=list)


def _default_run(argv: List[str]) -> CompletedRun:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):  # pragma: no cover - Windows environment
        return False


def _require_windows() -> None:
    if not sys.platform.startswith("win"):
        raise WindowsServiceError(
            "Windows service management is supported only on Windows"
        )


def _validate_service_id(service_id: str) -> str:
    if not service_id or not _SERVICE_ID_RE.fullmatch(service_id):
        raise WindowsServiceError(
            "service ID must contain only ASCII letters and numbers"
        )
    return service_id


def _validate_display_name(display_name: str) -> str:
    if not display_name or len(display_name) > 256:
        raise WindowsServiceError("display name must contain between 1 and 256 characters")
    if any(ord(character) < 32 for character in display_name):
        raise WindowsServiceError("display name must not contain control characters")
    return display_name


def _validate_sha256(value: str) -> str:
    if not _SHA256_RE.fullmatch(value):
        raise WindowsServiceError("WinSW SHA-256 must be exactly 64 hexadecimal characters")
    return value.lower()


def _program_data_root() -> Path:
    return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "AgentPulse"


def _resolve_existing_file(value: Optional[str], *, name: str, fallback: Optional[str] = None) -> Path:
    candidate = value or fallback
    if not candidate:
        raise WindowsServiceError(f"{name} was not found; pass an explicit path")
    path = Path(candidate).expanduser().resolve()
    if not path.is_file():
        raise WindowsServiceError(f"{name} does not exist or is not a file: {path}")
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _atomic_copy(source: Path, destination: Path) -> None:
    with source.open("rb") as handle:
        _atomic_write(destination, handle.read())


def _winsw_xml(
    *,
    service_id: str,
    display_name: str,
    agent_bin: Path,
    config_path: Path,
    install_dir: Path,
    log_dir: Path,
) -> bytes:
    root = ET.Element("service")
    entries = (
        ("id", service_id),
        ("name", display_name),
        (
            "description",
            "AgentPulse monitoring and policy-gated remediation agent",
        ),
        ("executable", str(agent_bin)),
        ("arguments", subprocess.list2cmdline(["run", str(config_path)])),
        ("workingdirectory", str(install_dir)),
        ("startmode", "Automatic"),
        ("delayedAutoStart", "true"),
        ("stoptimeout", "30 sec"),
        ("resetfailure", "1 hour"),
        ("logpath", str(log_dir)),
    )
    for tag, value in entries:
        ET.SubElement(root, tag).text = value
    ET.SubElement(root, "onfailure", {"action": "restart", "delay": "10 sec"})
    log = ET.SubElement(root, "log", {"mode": "roll-by-size"})
    ET.SubElement(log, "sizeThreshold").text = "10240"
    ET.SubElement(log, "keepFiles").text = "8"
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _command_error(command: str, completed: CompletedRun) -> WindowsServiceError:
    detail = (completed.stderr or completed.stdout or "unknown error").strip()
    return WindowsServiceError(
        f"WinSW {command} failed with exit code {completed.returncode}: {detail}"
    )


def install_windows_service(
    *,
    winsw_bin: str,
    winsw_sha256: str = WINSW_X64_SHA256,
    service_id: str = DEFAULT_SERVICE_ID,
    display_name: str = DEFAULT_DISPLAY_NAME,
    agent_bin: Optional[str] = None,
    config_path: str,
    install_dir: Optional[str] = None,
    log_dir: Optional[str] = None,
    dry_run: bool = False,
    run_fn: RunFn = _default_run,
    admin_fn: AdminFn = _is_admin,
) -> WindowsServiceInstallResult:
    """Install and start AgentPulse through a checksum-verified WinSW host."""
    _require_windows()
    service_id = _validate_service_id(service_id)
    display_name = _validate_display_name(display_name)
    expected_sha = _validate_sha256(winsw_sha256)
    wrapper_source = _resolve_existing_file(winsw_bin, name="WinSW executable")
    agent_fallback = None if agent_bin else shutil.which("agentpulse")
    resolved_agent = _resolve_existing_file(
        agent_bin,
        name="agentpulse executable",
        fallback=agent_fallback,
    )
    resolved_config = _resolve_existing_file(config_path, name="AgentPulse config")

    actual_sha = _sha256_file(wrapper_source)
    if actual_sha != expected_sha:
        raise WindowsServiceError(
            f"WinSW SHA-256 mismatch: expected {expected_sha}, got {actual_sha}"
        )

    root = Path(install_dir).expanduser().resolve() if install_dir else _program_data_root() / "service"
    logs = Path(log_dir).expanduser().resolve() if log_dir else _program_data_root() / "logs"
    wrapper_path = root / "AgentPulseService.exe"
    wrapper_config_path = root / "AgentPulseService.xml"
    steps = [
        f"create service directory {root}",
        f"create log directory {logs}",
        f"copy checksum-verified WinSW to {wrapper_path}",
        f"write WinSW configuration {wrapper_config_path}",
        f"install Windows service {service_id}",
        f"start Windows service {service_id}",
        f"verify Windows service {service_id} is Running",
    ]
    result = WindowsServiceInstallResult(
        service_id=service_id,
        display_name=display_name,
        agent_bin=str(resolved_agent),
        config_path=str(resolved_config),
        wrapper_path=str(wrapper_path),
        wrapper_config_path=str(wrapper_config_path),
        log_dir=str(logs),
        dry_run=dry_run,
        steps=steps,
    )
    if dry_run:
        return result
    if not admin_fn():
        raise WindowsServiceError(
            "Administrator privileges are required; run from an elevated PowerShell"
        )
    if wrapper_path.exists() or wrapper_config_path.exists():
        raise WindowsServiceError(
            "refusing to overwrite an existing AgentPulse service wrapper"
        )

    root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    installed = False
    try:
        _atomic_copy(wrapper_source, wrapper_path)
        _atomic_write(
            wrapper_config_path,
            _winsw_xml(
                service_id=service_id,
                display_name=display_name,
                agent_bin=resolved_agent,
                config_path=resolved_config,
                install_dir=root,
                log_dir=logs,
            ),
        )
        completed = run_fn([str(wrapper_path), "install", "--no-elevate"])
        if completed.returncode != 0:
            raise _command_error("install", completed)
        installed = True
        completed = run_fn([str(wrapper_path), "start", "--no-elevate"])
        if completed.returncode != 0:
            raise _command_error("start", completed)
        completed = run_fn(windows_service_command(service_id, "query"))
        if completed.returncode != 0 or completed.stdout.strip().casefold() != "running":
            raise _command_error("status verification", completed)
        return result
    except Exception as exc:
        if installed:
            rollback = run_fn([str(wrapper_path), "uninstall", "--no-elevate"])
            if rollback.returncode != 0:
                detail = (rollback.stderr or rollback.stdout or "unknown error").strip()
                raise WindowsServiceError(
                    f"{exc}; rollback uninstall failed: {detail}; "
                    "generated wrapper files were preserved for manual recovery"
                ) from exc
        wrapper_config_path.unlink(missing_ok=True)
        wrapper_path.unlink(missing_ok=True)
        raise


def uninstall_windows_service(
    *,
    service_id: str = DEFAULT_SERVICE_ID,
    install_dir: Optional[str] = None,
    remove_files: bool = False,
    dry_run: bool = False,
    run_fn: RunFn = _default_run,
    admin_fn: AdminFn = _is_admin,
) -> List[str]:
    """Stop and uninstall the configured WinSW service without broad deletion."""
    _require_windows()
    service_id = _validate_service_id(service_id)
    root = Path(install_dir).expanduser().resolve() if install_dir else _program_data_root() / "service"
    wrapper_path = root / "AgentPulseService.exe"
    wrapper_config_path = root / "AgentPulseService.xml"
    steps = [f"stop Windows service {service_id}", f"uninstall Windows service {service_id}"]
    if remove_files:
        steps.append(f"remove only {wrapper_path} and {wrapper_config_path}")
    if dry_run:
        return steps
    if not admin_fn():
        raise WindowsServiceError(
            "Administrator privileges are required; run from an elevated PowerShell"
        )
    if not wrapper_path.is_file() or not wrapper_config_path.is_file():
        raise WindowsServiceError(
            f"AgentPulse WinSW files were not found together in {root}"
        )
    try:
        configured_id = ET.parse(wrapper_config_path).getroot().findtext("id")
    except (ET.ParseError, OSError) as exc:
        raise WindowsServiceError(f"could not read WinSW configuration: {exc}") from exc
    if configured_id != service_id:
        raise WindowsServiceError(
            f"service ID mismatch: wrapper config contains {configured_id!r}"
        )

    # A non-zero stop is acceptable when the service is already stopped. The
    # uninstall result is authoritative and must still succeed.
    run_fn([str(wrapper_path), "stop", "--no-elevate"])
    completed = run_fn([str(wrapper_path), "uninstall", "--no-elevate"])
    if completed.returncode != 0:
        raise _command_error("uninstall", completed)
    if remove_files:
        wrapper_config_path.unlink(missing_ok=True)
        wrapper_path.unlink(missing_ok=True)
    return steps


def _encoded_service_script(service_name: str, operation: str) -> str:
    """Build a fixed PowerShell program with only a base64-encoded service ID."""
    encoded = base64.b64encode(service_name.encode("utf-16-le")).decode("ascii")
    prefix = (
        "$ErrorActionPreference='Stop';"
        f"$n=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{encoded}'));"
        "$s=Get-Service -Name $n -ErrorAction Stop;"
    )
    if operation == "query":
        return prefix + "[Console]::Out.Write($s.Status.ToString())"
    if operation == "restart":
        return (
            prefix
            + "Restart-Service -InputObject $s -ErrorAction Stop;"
            + "$s.WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Running,"
            + "[TimeSpan]::FromSeconds(30));$s.Refresh();"
            + "if($s.Status -ne [System.ServiceProcess.ServiceControllerStatus]::Running)"
            + "{throw 'service did not reach Running'};"
            + "[Console]::Out.Write($s.Status.ToString())"
        )
    raise ValueError(f"unsupported Windows service operation: {operation}")


def windows_service_command(service_name: str, operation: str) -> List[str]:
    """Return a shell-free PowerShell command for an allowlisted service name."""
    if not service_name or not re.fullmatch(r"[A-Za-z0-9_.@-]+", service_name):
        raise WindowsServiceError(f"invalid Windows service name: {service_name!r}")
    return [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        _encoded_service_script(service_name, operation),
    ]


def query_windows_service(service_name: str, run_fn: Callable[[List[str]], tuple[int, str]]) -> tuple[bool, str]:
    """Return whether a Windows service is exactly Running and its observed state."""
    rc, output = run_fn(windows_service_command(service_name, "query"))
    state = output.strip()
    return rc == 0 and state.casefold() == "running", state or "query failed"


def restart_windows_service(service_name: str, run_fn: Callable[[List[str]], tuple[int, str]]) -> tuple[bool, str]:
    """Restart a Windows service and wait up to 30 seconds for Running."""
    rc, output = run_fn(windows_service_command(service_name, "restart"))
    state = output.strip()
    return rc == 0 and state.casefold() == "running", state or "restart failed"
