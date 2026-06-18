"""Battle-test harness: thousands of randomized scenarios asserting the safety
invariants that matter for software that deletes files and restarts services on
its own.

Invariants under test:
  I1  A process is NEVER auto-executed (no auto-kill), under any mode.
  I2  Non-breached / 'off' observations never produce an action.
  I3  The cleanup glob guard never approves a filesystem-root sweep.
  I4  Real cleanup deletes ONLY regular files, older than the cutoff, inside the
      configured globs — never new files, never files outside the globs, never
      directories or symlinks — and never raises.
  I5  Service restart refuses any name containing shell/injection characters.

Total randomized iterations are asserted to exceed 3000.
"""

import os
import random
import string
import time

from agentpulse import policy, remediation
from agentpulse.models import Decision, Observation

ITER_POLICY = 1400
ITER_GLOB = 1200
ITER_FS = 700
ITER_SERVICE = 800

MODES = ["off", "alert", "ask", "auto"]
CHECKS = ["disk", "service", "process"]

FORBIDDEN_BASES = ["/", "/etc", "/usr", "/bin", "/sbin", "/lib", "/boot",
                   "/dev", "/proc", "/sys", "/root", "/home", "/var"]


def _rand_name(n=6):
    return "".join(random.choice(string.ascii_lowercase) for _ in range(n))


def test_I1_I2_policy_invariants():
    random.seed(1)
    count = 0
    for _ in range(ITER_POLICY):
        check = random.choice(CHECKS)
        mode = random.choice(MODES)
        breached = random.random() < 0.7
        obs = Observation(check=check, target=_rand_name(), breached=breached, detail="d")
        d = policy.decide(check, mode, obs)
        count += 1
        # I2: nothing happens when not breached or mode off
        if not breached or mode == "off":
            assert d is None
            continue
        assert d is not None
        # I1: process never auto-executes
        if check == "process":
            assert d.execute is False
        # auto on non-process executes; ask never executes; alert never executes
        if d.mode_effective == "auto":
            assert d.execute is True and d.requires_approval is False
        if d.mode_effective == "ask":
            assert d.execute is False and d.requires_approval is True
        if d.mode_effective == "alert":
            assert d.execute is False and d.requires_approval is False
    assert count == ITER_POLICY


def test_I3_glob_guard_never_allows_root_sweep():
    random.seed(2)
    count = 0
    for _ in range(ITER_GLOB):
        count += 1
        # Build adversarial patterns rooted at forbidden bases.
        base = random.choice(FORBIDDEN_BASES)
        suffix = random.choice(["/*", "/**", "/*.log", "", "/" + _rand_name() + "/*"])
        pattern = base + suffix
        allowed = remediation._is_safe_cleanup_glob(pattern)
        # Anything whose fixed base is a forbidden root must be refused.
        fixed_base = os.path.normpath(remediation._glob_base_dir(pattern))
        if fixed_base in FORBIDDEN_BASES or fixed_base == "/":
            assert allowed is False, pattern
        # Relative patterns always refused.
        if not pattern.startswith("/"):
            assert allowed is False, pattern
    assert count == ITER_GLOB


def test_I4_cleanup_only_old_files_in_globs(tmp_path):
    random.seed(3)
    count = 0
    for i in range(ITER_FS):
        d = tmp_path / f"run{i}"
        d.mkdir()
        target_dir = d / "clean"
        target_dir.mkdir()
        outside_dir = d / "keep"
        outside_dir.mkdir()

        now = time.time()
        expected_deleted = set()
        must_survive = set()

        # files inside the cleanup glob
        for _ in range(random.randint(0, 5)):
            f = target_dir / (_rand_name() + ".log")
            f.write_text("x" * random.randint(1, 50))
            age_days = random.choice([0, 0.5, 1, 5, 30])
            os.utime(f, (now - age_days * 86400, now - age_days * 86400))
            if age_days > 3:
                expected_deleted.add(str(f))
            else:
                must_survive.add(str(f))

        # a directory matching the glob (must never be deleted)
        gdir = target_dir / (_rand_name())
        gdir.mkdir()
        os.utime(gdir, (now - 100 * 86400, now - 100 * 86400))
        must_survive.add(str(gdir))

        # a symlink matching the glob (must never be followed/deleted target)
        real = outside_dir / "real.txt"
        real.write_text("important")
        link = target_dir / (_rand_name() + ".log")
        os.symlink(real, link)
        must_survive.add(str(real))

        # canary outside the glob
        canary = outside_dir / "canary.log"
        canary.write_text("do not touch")
        must_survive.add(str(canary))

        obs = Observation(
            check="disk", target="/", breached=True,
            metadata={"cleanup_globs": [str(target_dir / "*.log")], "cleanup_older_than_days": 3},
        )
        dec = Decision(action="disk_cleanup", target="/", mode_effective="auto",
                       execute=True, requires_approval=False, reason="r", observation=obs)
        # must never raise
        res = remediation.disk_cleanup(dec)

        for p in expected_deleted:
            assert not os.path.exists(p), f"old in-glob file should be gone: {p}"
        for p in must_survive:
            assert os.path.exists(p), f"protected path was wrongly removed: {p}"
        count += 1
    assert count == ITER_FS


def test_I5_service_name_injection_refused():
    random.seed(4)
    count = 0
    injection_bits = [";", "|", "&", "$(", "`", " ", "\n", "../", ">", "<", "rm -rf"]
    for _ in range(ITER_SERVICE):
        count += 1
        name = _rand_name(random.randint(1, 8))
        if random.random() < 0.5:
            name += random.choice(injection_bits) + _rand_name(3)
            obs = Observation(check="service", target=name, breached=True, metadata={"service": name})
            dec = Decision(action="service_restart", target=name, mode_effective="auto",
                           execute=True, requires_approval=False, reason="r", observation=obs)
            res = remediation.service_restart(dec, run_fn=lambda argv: (0, ""))
            assert res.performed is False and res.error is not None, name
    assert count == ITER_SERVICE


def test_total_iterations_exceed_3000():
    assert ITER_POLICY + ITER_GLOB + ITER_FS + ITER_SERVICE >= 3000
