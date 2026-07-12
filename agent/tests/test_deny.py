from agentpulse import runner
from agentpulse.models import Decision, Observation
from agentpulse.state import State


def make_state(tmp_path):
    return State.load(str(tmp_path / "state.json"))


def queue_service_restart(state):
    decision = Decision(
        action="service_restart",
        target="nginx",
        mode_effective="ask",
        execute=False,
        requires_approval=True,
        reason="crashed",
        observation=Observation(check="service", target="nginx", breached=True),
    )
    return state.queue_pending(decision)


def test_deny_removes_pending_and_records_history(tmp_path):
    state = make_state(tmp_path)
    pid = queue_service_restart(state)
    assert len(state.list_pending()) == 1

    entry = runner.deny(state, pid)
    assert entry is not None
    assert len(state.list_pending()) == 0

    history = state.list_history()
    assert len(history) == 1
    assert history[0]["outcome"] == "denied"
    assert history[0]["action"] == "service_restart"

    # Denial persists to disk.
    reloaded = State.load(str(tmp_path / "state.json"))
    assert len(reloaded.list_pending()) == 0
    assert reloaded.list_history()[0]["outcome"] == "denied"


def test_deny_unknown_id_returns_none(tmp_path):
    state = make_state(tmp_path)
    queue_service_restart(state)

    result = runner.deny(state, "bogus-id")
    assert result is None
    assert len(state.list_pending()) == 1
    assert state.list_history() == []
