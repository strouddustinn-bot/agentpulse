import json

import pytest

from agentpulse.audit import AuditLog
from agentpulse.checkin import CheckinClient, CheckinHTTPError
from agentpulse.identity import IdentityManager
from agentpulse.retry import CredentialRecoveryRequired
from agentpulse.spool import Spool


class Response:
    def __init__(self, status=202, payload=None, headers=None):
        self.status = status
        self._body = json.dumps(payload or {}).encode()
        self.headers = headers or {}

    def read(self, limit=-1):
        return self._body[:limit] if limit >= 0 else self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def setup_client(tmp_path, opener, audit=None):
    identity = IdentityManager(tmp_path / "identity.json", tmp_path / "credential")
    identity.ensure_agent_id(hostname="host-1")
    identity.store_credential("credential-secret")
    return CheckinClient(identity, Spool(tmp_path / "spool"), opener=opener, audit=audit)


def test_authenticated_checkin_uses_stable_identity_and_idempotency(tmp_path):
    captured = {}

    def opener(request, timeout):
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data.decode())
        return Response()

    client = setup_client(tmp_path, opener)
    assert client.send({"status": "ok"}) == 202
    assert captured["headers"]["Authorization"] == "Bearer credential-secret"
    assert captured["headers"]["X-idempotency-key"]
    assert captured["body"]["agent_id"] == client.identity.ensure_agent_id()


def test_failed_checkin_is_spooled_and_replayed(tmp_path):
    calls = []

    def failing(request, timeout):
        calls.append("failed")
        raise OSError("offline")

    client = setup_client(tmp_path, failing)
    assert client.send({"token": "do-not-store"}) is None
    assert len(client.spool.list_pending()) == 1
    assert "do-not-store" not in next((tmp_path / "spool").glob("*.json")).read_text()

    def healthy(request, timeout):
        calls.append("healthy")
        return Response()

    client.opener = healthy
    assert client.replay() == 1
    assert client.spool.list_pending() == []


def test_401_triggers_credential_recovery_without_retry_loop(tmp_path):
    calls = []

    def unauthorized(request, timeout):
        calls.append(1)
        raise CheckinHTTPError(401, "invalid")

    client = setup_client(tmp_path, unauthorized)
    with pytest.raises(CredentialRecoveryRequired):
        client.send({"status": "ok"})
    assert len(calls) == 1


def test_replayed_401_propagates_credential_recovery(tmp_path):
    def offline(request, timeout):
        raise OSError("offline")

    client = setup_client(tmp_path, offline)
    assert client.send({"status": "queued"}) is None
    queued = client.spool.list_pending()[0]

    def unauthorized(request, timeout):
        raise CheckinHTTPError(401, "invalid")

    client.opener = unauthorized
    with pytest.raises(CredentialRecoveryRequired):
        client.replay(max_events=1)

    pending = client.spool.list_pending()
    assert len(pending) == 1
    assert pending[0]["event_id"] == queued["event_id"]
    assert pending[0]["attempts"] == queued["attempts"]


def test_replay_preserves_event_id_for_exactly_once_dedupe(tmp_path):
    captured = []

    def offline(request, timeout):
        raise OSError("offline")

    client = setup_client(tmp_path, offline)
    client.send({"sequence": 1})
    event_id = client.spool.list_pending()[0]["event_id"]

    def online(request, timeout):
        captured.append(request.headers["X-idempotency-key"])
        return Response()

    client.opener = online
    assert client.replay() == 1
    assert captured == [event_id]


def test_redaction_before_transmission(tmp_path):
    captured = {}

    def opener(request, timeout):
        captured["body"] = request.data.decode()
        return Response()

    client = setup_client(tmp_path, opener)
    client.send({"Password": "secret-value", "safe": "visible"})
    assert "secret-value" not in captured["body"]
    assert "visible" in captured["body"]


def test_checkin_writes_redacted_audit_event(tmp_path):
    captured = {}

    def opener(request, timeout):
        captured["body"] = request.data.decode()
        return Response()

    audit = AuditLog(tmp_path / "audit.jsonl")
    client = setup_client(tmp_path, opener, audit=audit)
    client.send({"Password": "secret-value", "safe": "visible"})
    raw = (tmp_path / "audit.jsonl").read_text()
    assert "secret-value" not in raw
    assert audit.read()[0]["event_type"] == "checkin.acknowledged"
