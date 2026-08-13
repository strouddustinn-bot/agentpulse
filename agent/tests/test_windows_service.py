from __future__ import annotations

import hashlib
import subprocess
import sys
import xml.etree.ElementTree as ET

from agentpulse import windows_service


def _fixture_files(tmp_path):
    wrapper = tmp_path / "WinSW-x64.exe"
    wrapper.write_bytes(b"fixture-winsw")
    agent = tmp_path / "agentpulse.exe"
    agent.write_bytes(b"fixture-agent")
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")
    digest = hashlib.sha256(wrapper.read_bytes()).hexdigest()
    return wrapper, agent, config, digest


def _completed(argv, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr=stderr)


def test_install_fails_before_filesystem_or_commands_off_windows(tmp_path):
    wrapper, agent, config, digest = _fixture_files(tmp_path)
    install_dir = tmp_path / "service"
    calls = []

    try:
        windows_service.install_windows_service(
            winsw_bin=str(wrapper),
            winsw_sha256=digest,
            agent_bin=str(agent),
            config_path=str(config),
            install_dir=str(install_dir),
            run_fn=lambda argv: calls.append(argv) or _completed(argv),
        )
    except windows_service.WindowsServiceError as exc:
        assert str(exc) == "Windows service management is supported only on Windows"
    else:
        raise AssertionError("non-Windows install did not fail closed")

    assert calls == []
    assert not install_dir.exists()


def test_install_dry_run_verifies_inputs_without_mutation(tmp_path):
    wrapper, agent, config, digest = _fixture_files(tmp_path)
    install_dir = tmp_path / "service"
    calls = []
    original_platform = sys.platform
    try:
        sys.platform = "win32"
        result = windows_service.install_windows_service(
            winsw_bin=str(wrapper),
            winsw_sha256=digest,
            service_id="AgentPulseCI",
            agent_bin=str(agent),
            config_path=str(config),
            install_dir=str(install_dir),
            dry_run=True,
            run_fn=lambda argv: calls.append(argv) or _completed(argv),
            admin_fn=lambda: False,
        )
    finally:
        sys.platform = original_platform

    assert result.dry_run is True
    assert result.service_id == "AgentPulseCI"
    assert calls == []
    assert not install_dir.exists()


def test_install_rejects_wrapper_hash_mismatch_before_mutation(tmp_path):
    wrapper, agent, config, _digest = _fixture_files(tmp_path)
    install_dir = tmp_path / "service"
    original_platform = sys.platform
    try:
        sys.platform = "win32"
        try:
            windows_service.install_windows_service(
                winsw_bin=str(wrapper),
                winsw_sha256="0" * 64,
                agent_bin=str(agent),
                config_path=str(config),
                install_dir=str(install_dir),
                admin_fn=lambda: True,
            )
        except windows_service.WindowsServiceError as exc:
            assert "SHA-256 mismatch" in str(exc)
        else:
            raise AssertionError("mismatched wrapper hash was accepted")
    finally:
        sys.platform = original_platform

    assert not install_dir.exists()


def test_install_writes_bounded_xml_and_calls_winsw_without_shell(tmp_path):
    wrapper, agent, config, digest = _fixture_files(tmp_path)
    install_dir = tmp_path / "service folder"
    log_dir = tmp_path / "logs"
    calls = []

    def fake_run(argv):
        calls.append(argv)
        if argv[0] == "powershell.exe":
            return _completed(argv, stdout="Running")
        return _completed(argv)

    original_platform = sys.platform
    try:
        sys.platform = "win32"
        result = windows_service.install_windows_service(
            winsw_bin=str(wrapper),
            winsw_sha256=digest,
            service_id="AgentPulseCI",
            display_name="AgentPulse CI",
            agent_bin=str(agent),
            config_path=str(config),
            install_dir=str(install_dir),
            log_dir=str(log_dir),
            run_fn=fake_run,
            admin_fn=lambda: True,
        )
    finally:
        sys.platform = original_platform

    copied = install_dir / "AgentPulseService.exe"
    xml_path = install_dir / "AgentPulseService.xml"
    assert copied.read_bytes() == wrapper.read_bytes()
    root = ET.parse(xml_path).getroot()
    assert root.findtext("id") == "AgentPulseCI"
    assert root.findtext("name") == "AgentPulse CI"
    assert root.findtext("executable") == str(agent.resolve())
    assert root.findtext("arguments") == subprocess.list2cmdline(
        ["run", str(config.resolve())]
    )
    assert root.findtext("startmode") == "Automatic"
    assert root.findtext("logpath") == str(log_dir.resolve())
    assert calls == [
        [result.wrapper_path, "install", "--no-elevate"],
        [result.wrapper_path, "start", "--no-elevate"],
        windows_service.windows_service_command("AgentPulseCI", "query"),
    ]


def test_start_failure_uninstalls_and_removes_generated_files(tmp_path):
    wrapper, agent, config, digest = _fixture_files(tmp_path)
    install_dir = tmp_path / "service"
    calls = []

    def fake_run(argv):
        calls.append(argv)
        if argv[1] == "start":
            return _completed(argv, 1, stderr="start failed")
        return _completed(argv)

    original_platform = sys.platform
    try:
        sys.platform = "win32"
        try:
            windows_service.install_windows_service(
                winsw_bin=str(wrapper),
                winsw_sha256=digest,
                agent_bin=str(agent),
                config_path=str(config),
                install_dir=str(install_dir),
                run_fn=fake_run,
                admin_fn=lambda: True,
            )
        except windows_service.WindowsServiceError as exc:
            assert "WinSW start failed" in str(exc)
        else:
            raise AssertionError("start failure was accepted")
    finally:
        sys.platform = original_platform

    assert [call[1] for call in calls] == ["install", "start", "uninstall"]
    assert not (install_dir / "AgentPulseService.exe").exists()
    assert not (install_dir / "AgentPulseService.xml").exists()


def test_uninstall_removes_only_generated_files_when_requested(tmp_path):
    install_dir = tmp_path / "service"
    install_dir.mkdir()
    wrapper = install_dir / "AgentPulseService.exe"
    config = install_dir / "AgentPulseService.xml"
    keep = install_dir / "keep.log"
    wrapper.write_bytes(b"wrapper")
    config.write_text("<service><id>AgentPulseCI</id></service>", encoding="utf-8")
    keep.write_text("keep", encoding="utf-8")
    calls = []

    def fake_run(argv):
        calls.append(argv)
        return _completed(argv)

    original_platform = sys.platform
    try:
        sys.platform = "win32"
        windows_service.uninstall_windows_service(
            service_id="AgentPulseCI",
            install_dir=str(install_dir),
            remove_files=True,
            run_fn=fake_run,
            admin_fn=lambda: True,
        )
    finally:
        sys.platform = original_platform

    assert [call[1] for call in calls] == ["stop", "uninstall"]
    assert not wrapper.exists()
    assert not config.exists()
    assert keep.read_text(encoding="utf-8") == "keep"


def test_uninstall_rejects_mismatched_service_id_without_commands(tmp_path):
    install_dir = tmp_path / "service"
    install_dir.mkdir()
    (install_dir / "AgentPulseService.exe").write_bytes(b"wrapper")
    (install_dir / "AgentPulseService.xml").write_text(
        "<service><id>DifferentService</id></service>", encoding="utf-8"
    )
    calls = []
    original_platform = sys.platform
    try:
        sys.platform = "win32"
        try:
            windows_service.uninstall_windows_service(
                service_id="AgentPulseCI",
                install_dir=str(install_dir),
                run_fn=lambda argv: calls.append(argv) or _completed(argv),
                admin_fn=lambda: True,
            )
        except windows_service.WindowsServiceError as exc:
            assert "service ID mismatch" in str(exc)
        else:
            raise AssertionError("mismatched service ID was accepted")
    finally:
        sys.platform = original_platform

    assert calls == []


def test_service_control_command_does_not_interpolate_service_name():
    command = windows_service.windows_service_command("AgentPulse-CI", "restart")
    assert command[:5] == [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
    ]
    assert "AgentPulse-CI" not in command[5]


def test_query_and_restart_require_exact_running_state():
    query = windows_service.query_windows_service(
        "AgentPulseCI", lambda _argv: (0, "Running")
    )
    pending = windows_service.query_windows_service(
        "AgentPulseCI", lambda _argv: (0, "StartPending")
    )
    failed = windows_service.restart_windows_service(
        "AgentPulseCI", lambda _argv: (1, "Access denied")
    )
    assert query == (True, "Running")
    assert pending == (False, "StartPending")
    assert failed == (False, "Access denied")
