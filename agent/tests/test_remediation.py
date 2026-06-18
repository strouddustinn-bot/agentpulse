import os
import time

from agentpulse import remediation
from agentpulse.models import Decision, Observation


def _decision_cleanup(globs, days=3, target="/"):
    obs = Observation(
        check="disk",
        target=target,
        breached=True,
        metadata={"cleanup_globs": globs, "cleanup_older_than_days": days},
    )
    return Decision(
        action="disk_cleanup", target=target, mode_effective="auto",
        execute=True, requires_approval=False, reason="r", observation=obs,
    )


def _decision_service(name):
    obs = Observation(check="service", target=name, breached=True, metadata={"service": name})
    return Decision(
        action="service_restart", target=name, mode_effective="auto",
        execute=True, requires_approval=False, reason="r", observation=obs,
    )


# ---- safety guard on globs -------------------------------------------------

def test_unsafe_root_globs_refused():
    for bad in ["/", "/*", "/etc/*", "/usr/*", "/bin/*", "relative/*", ""]:
        assert remediation._is_safe_cleanup_glob(bad) is False, bad


def test_safe_globs_allowed():
    for good in ["/tmp/*", "/var/tmp/*", "/var/log/myapp/*.log", "/srv/app/cache/*"]:
        assert remediation._is_safe_cleanup_glob(good) is True, good


def test_cleanup_refuses_when_all_globs_unsafe(tmp_path):
    d = _decision_cleanup(["/etc/*", "/*"])
    res = remediation.disk_cleanup(d)
    assert res.performed is False
    assert res.error is not None


# ---- real filesystem behavior ---------------------------------------------

def test_cleanup_deletes_only_old_files(tmp_path):
    old = tmp_path / "old.log"
    new = tmp_path / "new.log"
    old.write_text("x" * 100)
    new.write_text("y" * 100)
    now = time.time()
    os.utime(old, (now - 10 * 86400, now - 10 * 86400))  # 10 days old
    os.utime(new, (now, now))

    d = _decision_cleanup([str(tmp_path / "*.log")], days=3)
    res = remediation.disk_cleanup(d)
    assert res.ok
    assert not old.exists(), "old file should be deleted"
    assert new.exists(), "new file must be preserved"


def test_cleanup_dry_run_deletes_nothing(tmp_path):
    f = tmp_path / "old.log"
    f.write_text("x" * 50)
    now = time.time()
    os.utime(f, (now - 10 * 86400, now - 10 * 86400))
    d = _decision_cleanup([str(tmp_path / "*.log")], days=3)
    res = remediation.disk_cleanup(d, dry_run=True)
    assert f.exists(), "dry-run must not delete"
    assert any("WOULD remove" in line for line in res.details)


def test_cleanup_never_touches_directories_or_symlinks(tmp_path):
    subdir = tmp_path / "olddir"
    subdir.mkdir()
    now = time.time()
    os.utime(subdir, (now - 30 * 86400, now - 30 * 86400))

    target = tmp_path / "real.txt"
    target.write_text("keep me")
    link = tmp_path / "old_link"
    os.symlink(target, link)
    os.utime(link, (now - 30 * 86400, now - 30 * 86400), follow_symlinks=False)

    d = _decision_cleanup([str(tmp_path / "*")], days=1)
    remediation.disk_cleanup(d)
    assert subdir.exists(), "directories must never be deleted"
    assert target.exists(), "symlink target must be untouched"


# ---- service name validation ----------------------------------------------

def test_service_restart_rejects_injection():
    for bad in ["nginx; rm -rf /", "a b", "$(reboot)", "x|y", ""]:
        res = remediation.service_restart(_decision_service(bad))
        assert res.performed is False
        assert res.error is not None, bad


def test_service_restart_dry_run():
    res = remediation.service_restart(_decision_service("nginx"), dry_run=True)
    assert res.ok and res.performed is False
    assert any("WOULD run" in d for d in res.details)


def test_service_restart_success():
    res = remediation.service_restart(_decision_service("nginx"), run_fn=lambda argv: (0, ""))
    assert res.performed is True


def test_service_restart_failure():
    res = remediation.service_restart(_decision_service("nginx"), run_fn=lambda argv: (1, "boom"))
    assert res.performed is False and res.error is not None
