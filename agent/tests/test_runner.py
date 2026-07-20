import copy
import os
import time
from unittest.mock import patch

from agentpulse import control_plane, runner
from agentpulse.checkin import CheckinDeliveryError
from agentpulse.config import Config
from agentpulse.models import Observation
from agentpulse.notify import Notifier
from agentpulse.retry import CredentialRecoveryRequired
from agentpulse.spool import Spool, SpoolFull
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


def test_run_once_dry_run_does_not_mutate_or_persist_state(tmp_path):
    cfg = Config()
    cfg.service.mode = "ask"
    state = make_state(tmp_path)
    before = copy.deepcopy(state.data)
    observations = [
        Observation(
            check="service",
            target="nginx",
            breached=True,
            detail="inactive",
        )
    ]

    runner.run_once(
        cfg,
        state,
        FakeNotifier(),
        dry_run=True,
        gather_fn=lambda _cfg: observations,
    )

    assert state.data == before
    assert not (tmp_path / "state.json").exists()


def test_backend_checkin_spool_filesystem_failure_is_non_fatal(tmp_path):
    cfg = Config(hostname="agent-1")
    cfg.checkin.endpoint_url = "https://backend.example/check-in"
    cfg.checkin.credential_file = str(tmp_path / "credential")
    notifier = FakeNotifier()

    with patch("agentpulse.spool.Spool", side_effect=OSError("read-only filesystem")):
        assert not runner.send_backend_checkin(
            cfg, runner.CycleSummary(), notifier
        )

    assert any("check-in failed" in title for title, _ in notifier.sent)


def test_control_plane_spool_filesystem_failure_is_non_fatal(tmp_path):
    cfg = Config(hostname="agent-1")
    cfg.control_plane.enabled = True
    cfg.control_plane.spool_directory = str(tmp_path / "control-plane-spool")
    notifier = FakeNotifier()

    with patch.object(runner, "Spool", side_effect=OSError("read-only filesystem")):
        assert not runner.send_control_plane_heartbeat(
            cfg, make_state(tmp_path), runner.CycleSummary(), notifier
        )

    assert any("spool failed" in title for title, _ in notifier.sent)


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


def test_backend_checkin_replays_spool_before_current_event(tmp_path):
    cfg = Config(hostname="agent-1")
    cfg.checkin.endpoint_url = "https://api.example.com"
    cfg.checkin.identity_file = str(tmp_path / "identity.json")
    cfg.checkin.credential_file = str(tmp_path / "credential")
    cfg.checkin.spool_directory = str(tmp_path / "spool")
    events = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def replay(self, max_events=2):
            assert max_events == 2
            events.append("replay")
            return 1

        def send(self, payload):
            events.append("send")
            return 202

    with patch.object(runner, "CheckinClient", FakeClient):
        assert runner.send_backend_checkin(cfg, runner.CycleSummary(), FakeNotifier())

    assert events == ["replay", "send"]


def test_backend_checkin_full_spool_notifies_without_crashing(tmp_path):
    cfg = Config(hostname="agent-1")
    cfg.checkin.endpoint_url = "https://api.example.com"
    cfg.checkin.identity_file = str(tmp_path / "identity.json")
    cfg.checkin.credential_file = str(tmp_path / "credential")
    cfg.checkin.spool_directory = str(tmp_path / "spool")
    notifier = FakeNotifier()

    class FullSpoolClient:
        def __init__(self, *args, **kwargs):
            pass

        def replay(self, max_events=2):
            assert max_events == 2
            return 0

        def send(self, payload):
            raise SpoolFull("spool capacity reached")

    with patch.object(runner, "CheckinClient", FullSpoolClient):
        result = runner.send_backend_checkin(
            cfg, runner.CycleSummary(), notifier
        )

    assert result is False
    assert any(title == "backend check-in failed" for title, _ in notifier.sent)


def test_backend_failed_oldest_queues_current_without_overtaking(tmp_path):
    cfg = Config(hostname="agent-1")
    cfg.checkin.endpoint_url = "https://api.example.com"
    cfg.checkin.identity_file = str(tmp_path / "identity.json")
    cfg.checkin.credential_file = str(tmp_path / "credential")
    cfg.checkin.spool_directory = str(tmp_path / "spool")
    spool = Spool(cfg.checkin.spool_directory)
    first_id = spool.enqueue("check_in", {"sequence": 1})
    events = []

    class OfflineClient:
        def __init__(self, identity, client_spool, **kwargs):
            self.spool = client_spool

        def replay(self, max_events=2):
            assert max_events == 2
            events.append("replay-oldest")
            return 0

        def queue(self, payload):
            events.append("queue-current")
            return self.spool.enqueue("check_in", payload)

        def send(self, payload):
            raise AssertionError("current event must not overtake backlog")

    with patch.object(runner, "CheckinClient", OfflineClient):
        assert not runner.send_backend_checkin(
            cfg, runner.CycleSummary(), FakeNotifier()
        )

    pending = spool.list_pending()
    assert events == ["replay-oldest", "queue-current"]
    assert len(pending) == 2
    assert pending[0]["event_id"] == first_id


def test_backend_replay_credential_recovery_queues_current_without_loss(tmp_path):
    cfg = Config(hostname="agent-1")
    cfg.checkin.endpoint_url = "https://api.example.com"
    cfg.checkin.identity_file = str(tmp_path / "identity.json")
    cfg.checkin.credential_file = str(tmp_path / "credential")
    cfg.checkin.spool_directory = str(tmp_path / "spool")
    spool = Spool(cfg.checkin.spool_directory)
    first_id = spool.enqueue("check_in", {"sequence": 1})
    notifier = FakeNotifier()

    class RecoverCredentialClient:
        def __init__(self, identity, client_spool, **kwargs):
            self.spool = client_spool

        def replay(self, max_events=2):
            raise CredentialRecoveryRequired("credential rejected")

        def queue(self, payload):
            return self.spool.enqueue("check_in", payload)

        def send(self, payload):
            raise AssertionError("current event must not overtake backlog")

    with patch.object(runner, "CheckinClient", RecoverCredentialClient):
        assert not runner.send_backend_checkin(
            cfg, runner.CycleSummary(), notifier
        )

    pending = spool.list_pending()
    assert len(pending) == 2
    assert pending[0]["event_id"] == first_id
    assert any("credential recovery" in title for title, _ in notifier.sent)


def test_backend_missing_credential_is_non_fatal(tmp_path):
    cfg = Config(hostname="agent-1")
    cfg.checkin.endpoint_url = "https://api.example.com"
    cfg.checkin.identity_file = str(tmp_path / "identity.json")
    cfg.checkin.credential_file = str(tmp_path / "missing-credential")
    cfg.checkin.spool_directory = str(tmp_path / "spool")
    notifier = FakeNotifier()

    assert not runner.send_backend_checkin(
        cfg, runner.CycleSummary(), notifier
    )

    assert len(Spool(cfg.checkin.spool_directory).list_pending()) == 1
    assert any("check-in failed" in title for title, _ in notifier.sent)


def test_backend_replay_budget_converges_multi_event_backlog(tmp_path):
    cfg = Config(hostname="agent-1")
    cfg.checkin.endpoint_url = "https://api.example.com"
    cfg.checkin.identity_file = str(tmp_path / "identity.json")
    cfg.checkin.credential_file = str(tmp_path / "credential")
    cfg.checkin.spool_directory = str(tmp_path / "spool")
    spool = Spool(cfg.checkin.spool_directory)
    for sequence in range(3):
        spool.enqueue("check_in", {"sequence": sequence})
    replay_budgets = []

    class RecoveringClient:
        def __init__(self, identity, client_spool, **kwargs):
            self.spool = client_spool

        def replay(self, max_events=2):
            replay_budgets.append(max_events)
            return self.spool.replay(lambda event: True, max_events=max_events)

        def queue(self, payload):
            return self.spool.enqueue("check_in", payload)

        def send(self, payload):
            return 202

    with patch.object(runner, "CheckinClient", RecoveringClient):
        assert not runner.send_backend_checkin(
            cfg, runner.CycleSummary(), FakeNotifier()
        )
        assert len(spool.list_pending()) == 2
        assert runner.send_backend_checkin(
            cfg, runner.CycleSummary(), FakeNotifier()
        )

    assert spool.list_pending() == []
    assert replay_budgets == [2, 2]


def test_control_plane_heartbeat_spools_and_replays_before_current(tmp_path):
    cfg = Config(hostname="agent-1")
    cfg.control_plane.enabled = True
    cfg.control_plane.base_url = "https://control.example"
    cfg.control_plane.credential_file = str(tmp_path / "credential")
    cfg.control_plane.spool_directory = str(tmp_path / "control-plane-spool")
    state = make_state(tmp_path)
    summary = runner.CycleSummary(observations=1)
    calls = []
    outcomes = [False, True, True]

    def fake_push(base_url, credential_file, payload, timeout=10):
        calls.append(payload["idempotency_key"])
        ok = outcomes.pop(0)
        return control_plane.PushResult(
            ok=ok,
            status=202 if ok else 0,
            error="" if ok else "offline",
        )

    with patch.object(control_plane, "push_heartbeat_payload", fake_push):
        assert not runner.send_control_plane_heartbeat(
            cfg, state, summary, FakeNotifier()
        )
        queued = Spool(cfg.control_plane.spool_directory).list_pending()
        assert len(queued) == 1

        assert runner.send_control_plane_heartbeat(
            cfg, state, summary, FakeNotifier()
        )

    assert Spool(cfg.control_plane.spool_directory).list_pending() == []
    assert calls[1] == calls[0]
    assert calls[2] != calls[0]


def test_control_plane_failed_oldest_queues_current_without_overtaking(tmp_path):
    cfg = Config(hostname="agent-1")
    cfg.control_plane.enabled = True
    cfg.control_plane.base_url = "https://control.example"
    cfg.control_plane.credential_file = str(tmp_path / "credential")
    cfg.control_plane.spool_directory = str(tmp_path / "control-plane-spool")
    state = make_state(tmp_path)
    summary = runner.CycleSummary(observations=1)
    calls = []

    def always_offline(base_url, credential_file, payload, timeout=10):
        calls.append(payload["idempotency_key"])
        return control_plane.PushResult(ok=False, status=0, error="offline")

    with patch.object(control_plane, "push_heartbeat_payload", always_offline):
        assert not runner.send_control_plane_heartbeat(
            cfg, state, summary, FakeNotifier()
        )
        first_id = calls[0]
        assert not runner.send_control_plane_heartbeat(
            cfg, state, summary, FakeNotifier()
        )

    pending = Spool(cfg.control_plane.spool_directory).list_pending()
    assert calls == [first_id, first_id]
    assert len(pending) == 2
    assert pending[0]["event_id"] == first_id


def test_control_plane_permanent_rejection_dead_letters_without_blocking(tmp_path):
    cfg = Config(hostname="agent-1")
    cfg.control_plane.enabled = True
    cfg.control_plane.base_url = "https://control.example"
    cfg.control_plane.credential_file = str(tmp_path / "credential")
    cfg.control_plane.spool_directory = str(tmp_path / "control-plane-spool")
    spool = Spool(cfg.control_plane.spool_directory)
    old_id = spool.enqueue(
        "control_plane_heartbeat",
        {"idempotency_key": "old", "summary": {}, "incidents": []},
        event_id="old",
    )
    calls = []
    notifier = FakeNotifier()

    def rejected(base_url, credential_file, payload, timeout=10):
        calls.append(payload["idempotency_key"])
        return control_plane.PushResult(ok=False, status=400, error="invalid_payload")

    with patch.object(control_plane, "push_heartbeat_payload", rejected):
        assert not runner.send_control_plane_heartbeat(
            cfg, make_state(tmp_path), runner.CycleSummary(), notifier
        )

    assert calls[0] == old_id
    assert len(calls) == 2
    assert spool.list_pending() == []
    assert len(list(spool.quarantine.glob("*.json"))) == 1
    assert any("rejected" in title for title, _ in notifier.sent)


def test_control_plane_401_preserves_backlog_and_requests_recovery(tmp_path):
    cfg = Config(hostname="agent-1")
    cfg.control_plane.enabled = True
    cfg.control_plane.base_url = "https://control.example"
    cfg.control_plane.credential_file = str(tmp_path / "credential")
    cfg.control_plane.spool_directory = str(tmp_path / "control-plane-spool")
    spool = Spool(cfg.control_plane.spool_directory)
    old_id = spool.enqueue(
        "control_plane_heartbeat",
        {"idempotency_key": "old", "summary": {}, "incidents": []},
        event_id="old",
    )
    calls = []
    notifier = FakeNotifier()

    def unauthorized(base_url, credential_file, payload, timeout=10):
        calls.append(payload["idempotency_key"])
        return control_plane.PushResult(ok=False, status=401, error="unauthorized")

    with patch.object(control_plane, "push_heartbeat_payload", unauthorized):
        assert not runner.send_control_plane_heartbeat(
            cfg, make_state(tmp_path), runner.CycleSummary(), notifier
        )

    assert calls == [old_id]
    pending_ids = [event["event_id"] for event in spool.list_pending()]
    assert len(pending_ids) == 2
    assert pending_ids[0] == old_id
    assert any("credential recovery" in title for title, _ in notifier.sent)


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
