import os
import time

from agentpulse import decision_loop
from agentpulse.models import Decision, Observation


def _disk_decision(globs, days=3):
    obs = Observation(
        check="disk",
        target="/",
        breached=True,
        metadata={"cleanup_globs": globs, "cleanup_older_than_days": days},
    )
    return Decision(
        action="disk_cleanup",
        target="/",
        mode_effective="auto",
        execute=True,
        requires_approval=False,
        reason="r",
        observation=obs,
    )


def _service_decision(name):
    obs = Observation(
        check="service", target=name, breached=True, metadata={"service": name}
    )
    return Decision(
        action="service_restart",
        target=name,
        mode_effective="auto",
        execute=True,
        requires_approval=False,
        reason="r",
        observation=obs,
    )


def _process_decision():
    obs = Observation(
        check="process", target="pid:1 (init)", breached=True, metadata={"pid": 1}
    )
    return Decision(
        action="process_alert",
        target="pid:1",
        mode_effective="ask",
        execute=True,
        requires_approval=False,
        reason="r",
        observation=obs,
    )


def test_cycle_simulates_before_executing(tmp_path):
    f = tmp_path / "old.log"
    f.write_text("x" * 100)
    now = time.time()
    os.utime(f, (now - 10 * 86400, now - 10 * 86400))
    dec = _disk_decision([str(tmp_path / "*.log")])
    rec = decision_loop.run_cycle(dec, verify_fn=lambda d: True)
    assert rec.simulation is not None and rec.simulation.ok
    assert rec.gate_allowed
    assert rec.outcome == "succeeded"
    assert not f.exists()


def test_force_dry_run_makes_no_changes(tmp_path):
    f = tmp_path / "old.log"
    f.write_text("x" * 100)
    now = time.time()
    os.utime(f, (now - 10 * 86400, now - 10 * 86400))
    dec = _disk_decision([str(tmp_path / "*.log")])
    rec = decision_loop.run_cycle(dec, verify_fn=lambda d: True, force_dry_run=True)
    assert rec.outcome == "simulated_only"
    assert f.exists(), "dry-run cycle must not delete"


def test_gate_blocks_unsafe_glob():
    dec = _disk_decision(["/etc/*"])  # guard refuses -> simulation error -> gate blocks
    rec = decision_loop.run_cycle(dec, verify_fn=lambda d: True)
    assert rec.outcome == "blocked"
    assert rec.gate_allowed is False
    assert rec.execution is None


def test_gate_blocks_process_action():
    dec = _process_decision()
    rec = decision_loop.run_cycle(dec, verify_fn=lambda d: True)
    assert rec.outcome == "blocked"
    assert rec.execution is None


def test_failed_verification_escalates():
    # service restart "succeeds" but verification says still down -> escalate.
    dec = _service_decision("nginx")
    rec = decision_loop.run_cycle(
        dec, verify_fn=lambda d: False, run_fn=lambda argv: (0, "")
    )
    assert rec.execution is not None and rec.execution.performed is True
    assert rec.verified is False
    assert rec.outcome == "escalated"
    assert any("escalat" in n.lower() for n in rec.notes)


def test_execution_failure_reported():
    dec = _service_decision("nginx")
    rec = decision_loop.run_cycle(
        dec, verify_fn=lambda d: True, run_fn=lambda argv: (1, "boom")
    )
    assert rec.outcome == "failed"


def test_record_is_serializable():
    dec = _service_decision("nginx")
    rec = decision_loop.run_cycle(
        dec, verify_fn=lambda d: True, run_fn=lambda argv: (0, "")
    )
    d = rec.as_dict()
    assert d["action"] == "service_restart"
    assert d["outcome"] in ("succeeded", "executed_unverified")
    # The gate fields the runner relies on for notifications must be present.
    assert "gate_allowed" in d and "gate_reasons" in d
    assert d["gate_reasons"], "gate_reasons must explain the decision"


def _unknown_decision(action):
    obs = Observation(
        check="disk",
        target="x",
        breached=True,
        metadata={
            "cleanup_globs": ["/tmp/agentpulse-test/*"],
            "cleanup_older_than_days": 3,
        },
    )
    return Decision(
        action=action,
        target="x",
        mode_effective="auto",
        execute=True,
        requires_approval=False,
        reason="r",
        observation=obs,
    )


def test_gate_default_denies_unknown_action():
    # A clean simulation must NOT be enough for an action the gate doesn't
    # explicitly allow-list — the gate fails closed.
    sim = decision_loop.RemediationResult(
        action="network_block", target="x", performed=False, dry_run=True
    )
    allowed, reasons = decision_loop.safety_gate(
        _unknown_decision("network_block"), sim
    )
    assert allowed is False
    assert reasons and "allowlist" in "; ".join(reasons)


def test_gate_allows_known_action_with_clean_simulation():
    sim = decision_loop.RemediationResult(
        action="service_restart", target="nginx", performed=False, dry_run=True
    )
    allowed, reasons = decision_loop.safety_gate(_service_decision("nginx"), sim)
    assert allowed is True
    assert reasons  # never empty


def test_noop_execution_escalates_instead_of_false_success():
    # Disk cleanup that matches zero eligible files performs nothing; the breach
    # can't have cleared, so the cycle must escalate rather than report success.
    dec = _disk_decision([str("/tmp/agentpulse-nonexistent-dir/*.log")])
    rec = decision_loop.run_cycle(
        dec, verify_fn=lambda d: True, run_fn=lambda argv: (0, "")
    )
    assert rec.execution is not None and rec.execution.ok
    assert rec.execution.performed is False
    assert rec.outcome == "escalated"
    assert rec.verified is False
