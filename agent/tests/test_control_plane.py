"""AgentPulse SaaS control-plane client contracts."""

import json
import os
import stat

import pytest

from agentpulse import config


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status = status
        self._payload = json.dumps(payload or {}).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit=-1):
        return self._payload if limit < 0 else self._payload[:limit]


def test_control_plane_defaults_disabled_and_credential_outside_json():
    cfg = config.from_dict({})
    assert not cfg.control_plane.enabled
    assert cfg.control_plane.credential_file == "/etc/agentpulse/agent.credential"
    assert not hasattr(cfg.control_plane, "secret")


def test_enabled_control_plane_requires_https():
    with pytest.raises(config.ConfigError):
        config.from_dict({"control_plane": {"enabled": True, "base_url": "http://example.com"}})


def test_localhost_http_is_allowed_for_development():
    cfg = config.from_dict({"control_plane": {"enabled": True, "base_url": "http://127.0.0.1:8787"}})
    assert cfg.control_plane.enabled


def test_write_and_read_credential_mode_0600(tmp_path):
    from agentpulse import control_plane

    path = str(tmp_path / "credential")
    control_plane.write_credential(path, "ap_agent_secret")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert control_plane.read_credential(path) == "ap_agent_secret"


def test_rejects_symlink_and_permissive_mode(tmp_path):
    from agentpulse import control_plane

    target = tmp_path / "target"
    target.write_text("ap_agent_secret\n", encoding="utf-8")
    os.chmod(str(target), 0o644)
    with pytest.raises(control_plane.CredentialError):
        control_plane.read_credential(str(target))
    link = tmp_path / "link"
    os.symlink(str(target), str(link))
    with pytest.raises(control_plane.CredentialError):
        control_plane.read_credential(str(link))


def test_enrollment_exchanges_token_and_persists_only_agent_credential(tmp_path):
    from agentpulse import control_plane

    captured = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse(201, {"agent_id": "id-1", "agent_credential": "ap_agent_unique", "agent_key": "node-1"})

    credential_file = str(tmp_path / "credential")
    result = control_plane.enroll(
        base_url="https://control.example",
        enrollment_token="ap_enroll_once",
        agent_key="node-1",
        hostname="host-1",
        local_policy_ceiling="alert",
        credential_file=credential_file,
        opener=opener,
    )
    assert result["agent_id"] == "id-1"
    assert captured["url"] == "https://control.example/v1/agents/enroll"
    assert captured["authorization"] == "Bearer ap_enroll_once"
    assert "ap_enroll_once" not in json.dumps(captured["body"])
    assert control_plane.read_credential(credential_file) == "ap_agent_unique"


def test_heartbeat_is_bounded_idempotent_and_authenticated(tmp_path):
    from agentpulse import control_plane

    credential_file = str(tmp_path / "credential")
    control_plane.write_credential(credential_file, "ap_agent_unique")
    captured = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(202, {"ok": True, "duplicate": False})

    state = {
        "last_run": 1234.5,
        "history": [{"action": "disk_cleanup", "outcome": "succeeded"}] * 100,
        "pending": {str(i): {"action": "service_restart"} for i in range(100)},
    }
    result = control_plane.push_heartbeat(
        base_url="https://control.example",
        credential_file=credential_file,
        state=state,
        summary={"observations": 3, "breaches": 1, "errors": []},
        cycle_id="cycle-1",
        opener=opener,
    )
    assert result.ok
    assert captured["url"] == "https://control.example/v1/agents/heartbeat"
    assert captured["authorization"] == "Bearer ap_agent_unique"
    assert captured["body"]["idempotency_key"] == "cycle-1"
    assert len(captured["body"]["incidents"]) <= 50
    assert "ap_agent_unique" not in json.dumps(captured["body"])


def test_subscription_failure_does_not_raise(tmp_path):
    from agentpulse import control_plane

    credential_file = str(tmp_path / "credential")
    control_plane.write_credential(credential_file, "ap_agent_unique")

    def payment_required(_request, _timeout):
        return FakeResponse(402, {"error": {"code": "subscription_inactive"}})

    result = control_plane.push_heartbeat(
        base_url="https://control.example",
        credential_file=credential_file,
        state={},
        summary={},
        cycle_id="cycle-2",
        opener=payment_required,
    )
    assert not result.ok
    assert result.status == 402
    assert result.error == "subscription_inactive"


def test_remote_policy_is_narrowed_again_on_host(tmp_path):
    from agentpulse import control_plane

    credential_file = str(tmp_path / "credential")
    control_plane.write_credential(credential_file, "ap_agent_unique")

    def opener(_request, _timeout):
        return FakeResponse(200, {"version": 1, "policy": {"checks": {"disk": {"mode": "auto"}}}})

    result = control_plane.fetch_policy(
        base_url="https://control.example",
        credential_file=credential_file,
        local_ceiling="ask",
        opener=opener,
    )
    assert result["policy"]["checks"]["disk"]["mode"] == "ask"
