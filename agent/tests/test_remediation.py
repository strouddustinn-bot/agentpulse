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


def test_double_slash_globs_refused():
    # POSIX normpath keeps '//etc' as-is, but glob('//etc/*') expands into the
    # real /etc — the guard must see through the doubled leading slash.
    for bad in ["//etc/*", "//usr/*", "//var/*", "//*", "//"]:
        assert remediation._is_safe_cleanup_glob(bad) is False, bad


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


def test_cleanup_never_escapes_through_symlinked_dir(tmp_path):
    # A symlinked directory inside the cleanup path must not let the glob
    # reach files outside it: the matched file is a regular file (not a
    # symlink), so only realpath containment can catch the escape.
    victim_dir = tmp_path / "victim"
    victim_dir.mkdir()
    victim = victim_dir / "important.log"
    victim.write_text("keep me")
    now = time.time()
    os.utime(victim, (now - 30 * 86400, now - 30 * 86400))

    clean = tmp_path / "clean"
    clean.mkdir()
    os.symlink(victim_dir, clean / "sub")

    # An honest subdirectory whose old file SHOULD still be cleaned, proving
    # the containment check doesn't over-block.
    real_sub = clean / "realsub"
    real_sub.mkdir()
    doomed = real_sub / "old.log"
    doomed.write_text("x")
    os.utime(doomed, (now - 30 * 86400, now - 30 * 86400))

    d = _decision_cleanup([str(clean / "*" / "*.log")], days=3)
    res = remediation.disk_cleanup(d)
    assert victim.exists(), "must never delete through a symlinked directory"
    assert not doomed.exists(), "genuine in-tree old file should still be cleaned"
    assert any("resolves outside the cleanup base" in line for line in res.details)


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
