import json

import pytest

from agentpulse import __version__
from agentpulse.checkin import CheckinDeliveryError, build_checkin_payload, payload_to_json, send_checkin_payload, status_from_summary
from agentpulse.config import Config
from agentpulse.runner import CycleSummary


def test_status_from_summary_ok():
    summary = CycleSummary(observations=1)
    assert status_from_summary(summary) == "ok"


def test_status_from_summary_attention():
    summary = CycleSummary(observations=1, breaches=1)
    assert status_from_summary(summary) == "attention"


def test_status_from_summary_error_wins():
    summary = CycleSummary(observations=1, breaches=1)
    summary.errors.append("boom")
    assert status_from_summary(summary) == "error"


def test_build_checkin_payload_counts_summary_lists():
    cfg = Config(hostname="local-dev")
    summary = CycleSummary(observations=3, breaches=1)
    summary.actions_taken.append("disk_cleanup:/")
    summary.queued.append("service_restart:nginx")
    summary.alerts.append("process:pid:123")
    summary.anomalies.append("mem")
    summary.escalations.append("disk_cleanup:/")
    summary.blocked.append("process:pid:1")

    payload = build_checkin_payload(cfg, summary, timestamp="2026-07-06T00:00:00Z")

    assert payload == {
        "agent_id": "local-dev",
        "hostname": "local-dev",
        "status": "attention",
        "observations": 3,
        "breaches": 1,
        "actions": 1,
        "queued": 1,
        "alerts": 1,
        "anomalies": 1,
        "escalations": 1,
        "blocked": 1,
        "errors": 0,
        "timestamp": "2026-07-06T00:00:00Z",
        "version": __version__,
    }


def test_payload_to_json_outputs_valid_json():
    cfg = Config(hostname="local-dev")
    summary = CycleSummary(observations=1)
    payload = build_checkin_payload(cfg, summary, timestamp="2026-07-06T00:00:00Z")

    encoded = payload_to_json(payload)

    assert json.loads(encoded) == payload


class FakeResponse:
    status = 202

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class CapturingOpener:
    def __init__(self):
        self.req = None
        self.timeout = None

    def __call__(self, req, timeout=10):
        self.req = req
        self.timeout = timeout
        return FakeResponse()


def test_send_checkin_payload_requires_endpoint():
    cfg = Config(hostname="local-dev")
    with pytest.raises(CheckinDeliveryError):
        send_checkin_payload(cfg, {"ok": True})


def test_send_checkin_payload_posts_json_with_auth_header():
    cfg = Config(hostname="local-dev")
    cfg.checkin.endpoint_url = "https://api.example.com/api/agent/checkin"
    cfg.checkin.auth_token = "secret-token"
    cfg.checkin.timeout_seconds = 3

    opener = CapturingOpener()
    status = send_checkin_payload(cfg, {"ok": True}, opener=opener)

    assert status == 202
    assert opener.timeout == 3
    assert opener.req.full_url == "https://api.example.com/api/agent/checkin"
    assert opener.req.get_method() == "POST"
    assert opener.req.headers["Content-type"] == "application/json"
    assert opener.req.headers["Authorization"] == "Bearer secret-token"
    assert json.loads(opener.req.data.decode("utf-8")) == {"ok": True}
