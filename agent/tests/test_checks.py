from agentpulse import checks
from agentpulse.config import DiskCheckConfig, ProcessCheckConfig, ServiceCheckConfig


def test_disk_breach():
    cfg = DiskCheckConfig(mode="alert", threshold_percent=90, paths=["/data"])

    def fake_disk_usage(path):
        # Always report 95% used regardless of path.
        return 100, 95, 5

    out = checks.check_disk(cfg, disk_usage_fn=fake_disk_usage)
    assert out[0].breached is True
    assert out[0].value == 95.0


def test_disk_under_threshold():
    cfg = DiskCheckConfig(threshold_percent=90, paths=["/"])
    out = checks.check_disk(cfg, disk_usage_fn=lambda p: (100, 50, 50))
    assert out[0].breached is False


def test_service_active():
    cfg = ServiceCheckConfig(services=["nginx"])
    out = checks.check_services(cfg, run_fn=lambda argv: (0, "active"))
    assert out[0].breached is False


def test_service_failed():
    cfg = ServiceCheckConfig(services=["nginx"])
    out = checks.check_services(cfg, run_fn=lambda argv: (3, "failed"))
    assert out[0].breached is True


def test_service_check_uses_launchctl_on_macos():
    cfg = ServiceCheckConfig(services=["com.example.agent"])
    calls = []
    original_platform = checks.sys.platform

    def fake_run(argv):
        calls.append(argv)
        return 0, ""

    try:
        checks.sys.platform = "darwin"
        out = checks.check_services(cfg, run_fn=fake_run)
    finally:
        checks.sys.platform = original_platform

    assert calls == [["launchctl", "list", "com.example.agent"]]
    assert out[0].breached is False


def test_service_check_uses_systemctl_off_macos():
    cfg = ServiceCheckConfig(services=["nginx"])
    calls = []
    original_platform = checks.sys.platform

    def fake_run(argv):
        calls.append(argv)
        return 0, "active"

    try:
        checks.sys.platform = "linux"
        out = checks.check_services(cfg, run_fn=fake_run)
    finally:
        checks.sys.platform = original_platform

    assert calls == [["systemctl", "is-active", "nginx"]]
    assert out[0].breached is False


def _make_fake_proc(tmp_path, mem_total_kb, procs):
    """procs: list of (pid, name, rss_kb)."""
    (tmp_path / "meminfo").write_text(f"MemTotal:   {mem_total_kb} kB\n")
    for pid, name, rss in procs:
        d = tmp_path / str(pid)
        d.mkdir()
        (d / "status").write_text(f"Name:\t{name}\nVmRSS:\t{rss} kB\n")
    return str(tmp_path)


def test_process_runaway_flagged(tmp_path):
    proc_root = _make_fake_proc(tmp_path, 1000, [(101, "java", 900), (102, "bash", 10)])
    cfg = ProcessCheckConfig(mode="alert", mem_percent_threshold=85)
    out = checks.check_processes(cfg, proc_root=proc_root)
    assert len(out) == 1
    assert out[0].metadata["pid"] == 101
    assert out[0].value == 90.0


def test_process_under_threshold(tmp_path):
    proc_root = _make_fake_proc(tmp_path, 1000, [(101, "java", 100)])
    cfg = ProcessCheckConfig(mem_percent_threshold=85)
    assert checks.check_processes(cfg, proc_root=proc_root) == []


def test_process_runaway_flagged_on_macos():
    cfg = ProcessCheckConfig(mode="alert", mem_percent_threshold=85)
    original_platform = checks.sys.platform
    calls = []

    def fake_run(argv):
        calls.append(argv)
        if argv == ["sysctl", "-n", "hw.memsize"]:
            return 0, "1024000"  # 1000 KiB
        if argv == ["ps", "-axo", "pid=,comm=,rss="]:
            return (
                0,
                "101 /Applications/App.app/Contents/MacOS/App 900\n102 /bin/zsh 10",
            )
        return 1, "unexpected command"

    try:
        checks.sys.platform = "darwin"
        out = checks.check_processes(cfg, run_fn=fake_run)
    finally:
        checks.sys.platform = original_platform

    assert calls == [
        ["sysctl", "-n", "hw.memsize"],
        ["ps", "-axo", "pid=,comm=,rss="],
    ]
    assert len(out) == 1
    assert out[0].metadata["pid"] == 101
    assert out[0].metadata["name"] == "/Applications/App.app/Contents/MacOS/App"
    assert out[0].value == 90.0
