import pytest

from agentpulse import policy
from agentpulse.models import Observation


def obs(check="disk", breached=True):
    return Observation(check=check, target="t", breached=breached, detail="d")


def test_not_breached_returns_none():
    assert policy.decide("disk", "auto", obs(breached=False)) is None


def test_off_returns_none():
    assert policy.decide("disk", "off", obs()) is None


def test_alert_notifies_only():
    d = policy.decide("disk", "alert", obs())
    assert d.execute is False and d.requires_approval is False


def test_ask_requires_approval():
    d = policy.decide("service", "ask", obs("service"))
    assert d.requires_approval is True and d.execute is False


def test_auto_executes():
    d = policy.decide("disk", "auto", obs())
    assert d.execute is True and d.requires_approval is False


def test_process_auto_produces_execute():
    # Process in auto mode now produces execute=True at the policy layer.
    # Safety gates (kill_eligible, PID checks) enforce safety in the decision loop.
    d = policy.decide("process", "auto", obs("process"))
    assert d.execute is True
    assert d.requires_approval is False
    assert d.action == "process_kill"


def test_process_ask_requires_approval():
    d = policy.decide("process", "ask", obs("process"))
    assert d.execute is False
    assert d.requires_approval is True


@pytest.mark.parametrize("check", ["disk", "service", "process", "ssh"])
@pytest.mark.parametrize("mode", ["off", "alert", "ask", "auto"])
def test_mode_invariants(check, mode):
    d = policy.decide(check, mode, obs(check))
    if mode == "off":
        assert d is None
    elif mode == "alert":
        assert d is not None and d.execute is False and d.requires_approval is False
    elif mode == "ask":
        assert d is not None and d.execute is False and d.requires_approval is True
    elif mode == "auto":
        assert d is not None and d.execute is True and d.requires_approval is False
