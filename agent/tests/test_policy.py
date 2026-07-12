import pytest  # type: ignore
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
    assert d is not None
    assert d.execute is False and d.requires_approval is False


def test_ask_requires_approval():
    d = policy.decide("service", "ask", obs("service"))
    assert d is not None
    assert d.requires_approval is True and d.execute is False


def test_auto_executes():
    d = policy.decide("disk", "auto", obs())
    assert d is not None
    assert d.execute is True and d.requires_approval is False


def test_process_auto_is_clamped_to_ask():
    d = policy.decide("process", "auto", obs("process"))
    assert d is not None
    assert d.execute is False
    assert d.requires_approval is True
    assert d.clamped_from == "auto"
    assert "never auto-killed" in d.reason


@pytest.mark.parametrize("check", ["disk", "service", "process"])
@pytest.mark.parametrize("mode", ["off", "alert", "ask", "auto"])
def test_process_never_auto_executes(check, mode):
    d = policy.decide(check, mode, obs(check))
    if check == "process" and d is not None:
        assert d.execute is False, "process must never auto-execute"
