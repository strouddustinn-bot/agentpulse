import json

from agentpulse import __version__
from agentpulse.checkin import build_checkin_payload, payload_to_json, status_from_summary
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
