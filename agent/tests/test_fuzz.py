"""Battle-test harness: thousands of randomized scenarios asserting the safety
invariants that matter for software that deletes files and restarts services on
its own.

Invariants under test:
  I1  Process remediation is never executable in v1, even after approval.
  I2  Non-breached / 'off' observations never produce an action.
  I3  The cleanup glob guard never approves a filesystem-root sweep — including
      patterns hiding behind a doubled leading slash ('//etc/*').
  I4  Real cleanup deletes ONLY regular files, older than the cutoff, inside the
      configured globs — never new files, never files outside the globs, never
      directories or symlinks, and never through a symlinked directory that
      resolves outside the cleanup base — and never raises.
  I5  Service restart refuses any name containing shell/injection characters.
  I6  Baseline learning never flags an anomaly during warmup.
  I7  The decision-loop safety gate fails closed: it never allows an action
      without a successful simulation, and never allows an action outside the
      executable allowlist (unknown/alert-only actions are always refused), and
      always returns a non-empty reason.

Total randomized iterations are asserted to exceed 3000.
"""

import os
import random
import string
import time

from agentpulse import decision_loop, policy, remediation
from agentpulse.models import Decision, Observation

ITER_POLICY = 1400
ITER_GLOB = 1200
ITER_FS = 700
ITER_SERVICE = 800
ITER_BASELINE = 1000
ITER_LOOP = 1200

MODES = ["off", "alert", "ask", "auto"]
CHECKS = ["disk", "service", "process", "ssh"]

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
        # Mode invariants hold across all check types.
        if d.mode_effective == "auto":
            assert d.execute is True and d.requires_approval is False
        if d.mode_effective == "ask":
            assert d.execute is False and d.requires_approval is True
        if d.mode_effective == "alert":
            assert d.execute is False and d.requires_approval is False
    assert count == ITER_POLICY


def test_I1_process_actions_are_never_executable():
    """I1: the decision loop default-denies all process actions in v1."""
    random.seed(11)
    count = 0
    for _ in range(500):
        count += 1
        obs = Observation(
            check="process", target="pid:1234 (myapp)", breached=True,
            metadata={"pid": 1234, "name": "myapp"},
        )
        dec = Decision(action="process_alert", target="pid:1234 (myapp)",
                       mode_effective="auto", execute=True, requires_approval=False,
                       reason="r", observation=obs)
        sim = remediation.RemediationResult(
            action="process_alert", target="pid:1234 (myapp)",
            performed=False, dry_run=True, error=None,
        )
        allowed, reasons = decision_loop.safety_gate(dec, sim)
        assert allowed is False, "process actions must be blocked in v1"
        assert reasons
    assert count == 500


def test_I3_glob_guard_never_allows_root_sweep():
    random.seed(2)
    count = 0
    for _ in range(ITER_GLOB):
        count += 1
        # Build adversarial patterns rooted at forbidden bases.
        base = random.choice(FORBIDDEN_BASES)
        suffix = random.choice(["/*", "/**", "/*.log", "", "/" + _rand_name() + "/*"])
        pattern = base + suffix
        if random.random() < 0.25:
            # '//etc/*' — POSIX normpath preserves the doubled slash, but glob
            # still expands it into the real /etc. Must still be refused.
            pattern = "/" + pattern
        allowed = remediation._is_safe_cleanup_glob(pattern)
        # Anything whose fixed base is a forbidden root must be refused.
        fixed_base = os.path.normpath(remediation._glob_base_dir(pattern))
        if fixed_base.startswith("//"):
            fixed_base = "/" + fixed_base.lstrip("/")
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

        # a symlinked directory inside the glob path: the second glob matches
        # regular files *through* it, which resolve outside the cleanup base
        # and must survive
        victim = outside_dir / "victim.log"
        victim.write_text("reachable only through the symlinked dir")
        os.utime(victim, (now - 100 * 86400, now - 100 * 86400))
        os.symlink(outside_dir, target_dir / "sneaky")
        must_survive.add(str(victim))

        # an honest subdirectory whose old file SHOULD be cleaned by the
        # second glob, proving containment doesn't over-block
        real_sub = target_dir / "realsub"
        real_sub.mkdir()
        doomed = real_sub / "doomed.log"
        doomed.write_text("x")
        os.utime(doomed, (now - 100 * 86400, now - 100 * 86400))
        expected_deleted.add(str(doomed))

        obs = Observation(
            check="disk", target="/", breached=True,
            metadata={
                "cleanup_globs": [
                    str(target_dir / "*.log"),
                    str(target_dir / "*" / "*.log"),
                ],
                "cleanup_older_than_days": 3,
            },
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


def test_I6_baseline_never_raises_or_flags_in_warmup():
    from agentpulse import baseline
    from agentpulse.config import BaselineConfig

    random.seed(6)
    count = 0
    for _ in range(ITER_BASELINE):
        count += 1
        cfg = BaselineConfig(
            min_samples=random.randint(5, 40),
            z_threshold=random.choice([2.0, 3.0, 4.0]),
            min_abs_deviation=random.choice([1.0, 2.0, 5.0]),
        )
        store = {}
        n = random.randint(0, cfg.min_samples - 1)  # always still in warmup
        flagged = False
        for _ in range(n):
            val = random.uniform(0, 100)  # arbitrary, even wild
            a, _r = baseline.observe(store, "k", val, cfg)
            flagged = flagged or a
        # Within warmup, nothing may be flagged regardless of values.
        assert flagged is False
    assert count == ITER_BASELINE


_EXECUTABLE_ACTIONS = frozenset({"disk_cleanup", "service_restart"})


def test_I7_safety_gate_fails_closed():
    random.seed(7)
    count = 0
    actions = ["disk_cleanup", "service_restart", "process_alert", "none", "", _rand_name()]
    for _ in range(ITER_LOOP):
        count += 1
        action = random.choice(actions)
        sim_ok = random.random() < 0.7
        sim = remediation.RemediationResult(
            action=action, target="t", performed=random.random() < 0.5,
            dry_run=True, error=None if sim_ok else "simulated failure",
        )
        obs = Observation(check="x", target="t", breached=True)
        dec = Decision(action=action, target="t", mode_effective="auto",
                       execute=True, requires_approval=False, reason="r", observation=obs)
        allowed, reasons = decision_loop.safety_gate(dec, sim)
        # Never allow without a successful simulation.
        if not sim.ok:
            assert allowed is False, action
        # Never allow an action outside the executable allowlist, even when the
        # simulation is clean. process_alert / unknown / alert-only actions fail closed.
        if action not in _EXECUTABLE_ACTIONS:
            assert allowed is False, action
        # The runner builds its notification body from these; never empty.
        assert reasons, action
    assert count == ITER_LOOP


def test_I7_run_cycle_never_executes_blocked_actions():
    random.seed(8)
    count = 0
    # Non-executable actions that must always be blocked before the Act step.
    blocked_actions = ["process_alert", "none", _rand_name()]
    for _ in range(ITER_LOOP):
        count += 1
        action = random.choice(blocked_actions)
        obs = Observation(check="process", target="pid:1", breached=True, metadata={"pid": 1})
        dec = Decision(action=action, target="pid:1", mode_effective="auto",
                       execute=True, requires_approval=False, reason="r", observation=obs)
        rec = decision_loop.run_cycle(
            dec, verify_fn=lambda d: True, run_fn=lambda argv: (0, ""),
        )
        assert rec.outcome == "blocked", (action, rec.outcome)
        assert rec.gate_allowed is False
        assert rec.execution is None, "a blocked action must never reach the Act step"
    assert count == ITER_LOOP


def test_total_iterations_exceed_3000():
    total = (
        ITER_POLICY + ITER_GLOB + ITER_FS + ITER_SERVICE + ITER_BASELINE + 2 * ITER_LOOP
    )
    assert total >= 3000
