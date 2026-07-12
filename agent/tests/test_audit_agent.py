import json

from agentpulse.audit import AuditLog


def test_audit_entry_contains_required_fields(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    audit.append(
        agent_id="agent-uuid",
        event_type="remediation.completed",
        correlation_id="corr-uuid",
        actor="agent",
        reason="systemd service failed",
        policy={"mode": "auto"},
        evidence_before={"active": False},
        action={"service": "demo"},
        result={"exit_code": 0},
        evidence_after={"active": True},
        agent_version="0.1.0",
        config_version="config-hash",
    )
    entry = json.loads((tmp_path / "audit.jsonl").read_text().strip())
    assert set(entry) == {
        "event_id", "timestamp", "agent_id", "event_type", "correlation_id",
        "actor", "reason", "policy", "evidence_before", "action", "result",
        "evidence_after", "agent_version", "config_version",
    }


def test_audit_entry_contains_no_secrets(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    audit.append(
        agent_id="agent-uuid",
        event_type="checkin.failed",
        correlation_id="corr",
        actor="agent",
        reason="Authorization: Bearer super-secret",
        policy={"Api_Key": "key-secret"},
        evidence_before={"url": "https://user:pass@example.test?token=tok-secret"},
        action={"output": "TOKEN=token-secret"},
        result={}, evidence_after={}, agent_version="0.1", config_version="hash",
    )
    raw = (tmp_path / "audit.jsonl").read_text()
    assert "super-secret" not in raw
    assert "key-secret" not in raw
    assert "tok-secret" not in raw
    assert "token-secret" not in raw


def test_audit_is_append_only_structured_jsonl(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    for index in range(2):
        audit.append(
            agent_id="a", event_type="event", correlation_id=str(index), actor="agent",
            reason="reason", policy={}, evidence_before={}, action={}, result={},
            evidence_after={}, agent_version="v", config_version="c",
        )
    assert len((tmp_path / "audit.jsonl").read_text().splitlines()) == 2
    assert len(audit.read()) == 2


def test_audit_directory_and_file_permissions(tmp_path):
    audit = AuditLog(tmp_path / "nested" / "audit.jsonl")
    audit.append(
        agent_id="a", event_type="event", correlation_id="c", actor="agent",
        reason="r", policy={}, evidence_before={}, action={}, result={},
        evidence_after={}, agent_version="v", config_version="c",
    )
    assert oct((tmp_path / "nested").stat().st_mode & 0o777) == "0o700"
    assert oct((tmp_path / "nested" / "audit.jsonl").stat().st_mode & 0o777) == "0o600"


def test_audit_event_id_is_unique(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    kwargs = dict(agent_id="a", event_type="event", correlation_id="c", actor="agent", reason="r", policy={}, evidence_before={}, action={}, result={}, evidence_after={}, agent_version="v", config_version="c")
    first = audit.append(**kwargs)
    second = audit.append(**kwargs)
    assert first["event_id"] != second["event_id"]


def test_audit_redacts_nested_values_before_serialization(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    audit.append(
        agent_id="a", event_type="event", correlation_id="c", actor="agent", reason="r",
        policy={"nested": [{"password": "hidden"}]}, evidence_before={}, action={}, result={},
        evidence_after={}, agent_version="v", config_version="c",
    )
    entry = audit.read()[0]
    assert entry["policy"]["nested"][0]["password"] == "[REDACTED]"


def test_audit_read_skips_malformed_tail(tmp_path):
    path = tmp_path / "audit.jsonl"
    audit = AuditLog(path)
    audit.append(agent_id="a", event_type="event", correlation_id="c", actor="agent", reason="r", policy={}, evidence_before={}, action={}, result={}, evidence_after={}, agent_version="v", config_version="c")
    with path.open("a") as handle:
        handle.write("not json\n")
    assert len(audit.read()) == 1


def test_audit_timestamp_is_rfc3339(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    entry = audit.append(agent_id="a", event_type="event", correlation_id="c", actor="agent", reason="r", policy={}, evidence_before={}, action={}, result={}, evidence_after={}, agent_version="v", config_version="c")
    assert entry["timestamp"].endswith("Z")
