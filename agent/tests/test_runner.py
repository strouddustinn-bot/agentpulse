import os
import time

from agentpulse import runner
from agentpulse.checkin import CheckinDeliveryError
from agentpulse.config import Config
from agentpulse.models import Observation
from agentpulse.notify import Notifier
from agentpulse.state import State


class FakeNotifier(Notifier):
    def __init__(self):
        self.sent = []

    def send(self, title, body):
        self.sent.append((title, body))
        return True


def make_state(tmp_path):
    return State.load(str(tmp_path / "state.json"))


def test_alert_only_notifies(tmp_path):
    cfg = Config()
    cfg.disk.mode = "alert"
    obs = [Observation(check="disk", target="/", breached=True, detail="disk 99%")]
    n = FakeNotifier()
    summary = runner.run_once(cfg, make_state(tmp_path), n, gather_fn=lambda c: obs)
    assert summary.alerts and not summary.actions_taken
    assert any("alert" in t for t, _ in n.sent)


def test_run_once_sends_backend_checkin_when_configured(tmp_path):
    cfg = Config(hostname="agent-1")
    cfg.checkin.endpoint_url = "https://api.example.com/api/agent/checkin"
    cfg.checkin.auth_token = "token"
    calls = []

    def fake_sender(sent_cfg, payload):
        calls.append((sent_cfg, payload))
        return 202

    summary = runner.run_once(
        cfg,
        make_state(tmp_path),
        FakeNotifier(),
        gather_fn=lambda c: [],
        checkin_sender=fake_sender,
    )

    assert summary.observations == 0
    assert len(calls) == 1
    assert calls[0][0] is cfg
    assert calls[0][1]["agent_id"] == "agent-1"
    assert calls[0][1]["status"] == "ok"


def test_run_once_skips_backend_checkin_during_dry_run(tmp_path):
    cfg = Config(hostname="agent-1")
    cfg.checkin.endpoint_url = "https://api.example.com/api/agent/checkin"
    calls = []

    runner.run_once(
        cfg,
        make_state(tmp_path),
        FakeNotifier(),
        dry_run=True,
        gather_fn=lambda c: [],
        checkin_sender=lambda sent_cfg, payload: calls.append(payload),
    )

    assert calls == []


def test_run_once_backend_checkin_failure_notifies_but_does_not_crash(tmp_path):
    cfg = Config(hostname="agent-1")
    cfg.checkin.endpoint_url = "https://api.example.com/api/agent/checkin"
    notifier = FakeNotifier()

    def failing_sender(sent_cfg, payload):
        raise CheckinDeliveryError("backend down")

    summary = runner.run_once(
        cfg,
        make_state(tmp_path),
        notifier,
        gather_fn=lambda c: [],
        checkin_sender=failing_sender,
    )

    assert summary.errors == []
    assert any(title == "backend check-in failed" for title, _ in notifier.sent)


def test_ask_queues_pending(tmp_path):
    cfg = Config()
    cfg.service.mode = "ask"
    obs = [
        Observation(
            check="service",
            target="nginx",
            breached=True,
            detail="nginx failed",
            metadata={"service": "nginx"},
        )
    ]
    n = FakeNotifier()
    state = make_state(tmp_path)
    summary = runner.run_once(cfg, state, n, gather_fn=lambda c: obs)
    assert summary.queued
    assert len(state.list_pending()) == 1


def test_auto_disk_cleanup_acts(tmp_path):
    old = tmp_path / "old.log"
    old.write_text("x" * 200)
    now = time.time()
    os.utime(old, (now - 10 * 86400, now - 10 * 86400))

    cfg = Config()
    cfg.disk.mode = "auto"
    obs = [
        Observation(
            check="disk",
            target="/",
            breached=True,
            detail="disk 99%",
            metadata={
                "cleanup_globs": [str(tmp_path / "*.log")],
                "cleanup_older_than_days": 3,
            },
        )
    ]
    n = FakeNotifier()
    summary = runner.run_once(cfg, make_state(tmp_path), n, gather_fn=lambda c: obs)
    # Either verified-success or escalated (if the sandbox root is itself full),
    # but the cleanup must have happened and been recorded one way or the other.
    assert summary.actions_taken or summary.escalations
    assert not old.exists()


def test_approve_executes_pending(tmp_path):
    old = tmp_path / "old.log"
    old.write_text("x" * 200)
    now = time.time()
    os.utime(old, (now - 10 * 86400, now - 10 * 86400))

    cfg = Config()
    cfg.disk.mode = "ask"
    obs = [
        Observation(
            check="disk",
            target="/",
            breached=True,
            detail="disk 99%",
            metadata={
                "cleanup_globs": [str(tmp_path / "*.log")],
                "cleanup_older_than_days": 3,
            },
        )
    ]
    state = make_state(tmp_path)
    runner.run_once(cfg, state, FakeNotifier(), gather_fn=lambda c: obs)
    pending = state.list_pending()
    assert len(pending) == 1
    assert old.exists(), "ask-first must NOT act before approval"

    rec_opt = runner.approve(cfg, state, pending[0]["id"])
    assert rec_opt is not None
    rec = rec_opt
    # Approval runs the full decision loop, so the cleanup either verified-clear
    # or escalated (if the sandbox root is itself full) — but either way it ran
    # the action through the gate and actually removed the file.
    assert rec.outcome in ("succeeded", "escalated")
    assert rec.gate_allowed is True
    assert not old.exists(), "approval should execute the cleanup"
    assert len(state.list_pending()) == 0


def test_approve_runs_through_safety_gate(tmp_path):
    # An approved process action must still be blocked by the gate — human
    # approval is NOT a bypass of the hard safety invariants.
    cfg = Config()
    cfg.process.mode = "ask"
    obs = [
        Observation(
            check="process",
            target="pid:1 (init)",
            breached=True,
            detail="mem 99%",
            metadata={"pid": 1},
        )
    ]
    state = make_state(tmp_path)
    runner.run_once(cfg, state, FakeNotifier(), gather_fn=lambda c: obs)
    pending = state.list_pending()
    assert len(pending) == 1

    rec_opt = runner.approve(cfg, state, pending[0]["id"])
    assert rec_opt is not None
    rec = rec_opt
    assert rec.outcome == "blocked", (
        "process actions must never execute, even when approved"
    )
    assert rec.gate_allowed is False
    assert rec.execution is None


def test_approve_dry_run_previews_without_consuming(tmp_path):
    old = tmp_path / "old.log"
    old.write_text("x" * 200)
    now = time.time()
    os.utime(old, (now - 10 * 86400, now - 10 * 86400))

    cfg = Config()
    cfg.disk.mode = "ask"
    obs = [
        Observation(
            check="disk",
            target="/",
            breached=True,
            detail="disk 99%",
            metadata={
                "cleanup_globs": [str(tmp_path / "*.log")],
                "cleanup_older_than_days": 3,
            },
        )
    ]
    state = make_state(tmp_path)
    runner.run_once(cfg, state, FakeNotifier(), gather_fn=lambda c: obs)
    pid = state.list_pending()[0]["id"]

    # A dry-run approval previews the action but must NOT delete anything or
    # consume the pending entry.
    rec_opt = runner.approve(cfg, state, pid, dry_run=True)
    assert rec_opt is not None
    rec = rec_opt
    assert rec.outcome == "simulated_only"
    assert old.exists(), "dry-run approval must not delete anything"
    assert len(state.list_pending()) == 1, (
        "dry-run approval must not consume the pending entry"
    )

    # The entry survives reload from disk too (dry-run did not persist a pop).
    reloaded = State.load(str(tmp_path / "state.json"))
    assert len(reloaded.list_pending()) == 1

    # A real approval afterward still finds and consumes the entry.
    rec2_opt = runner.approve(cfg, state, pid)
    assert rec2_opt is not None
    rec2 = rec2_opt
    assert rec2.outcome in ("succeeded", "escalated")
    assert not old.exists(), "real approval should execute the cleanup"
    assert len(state.list_pending()) == 0
