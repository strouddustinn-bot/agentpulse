import json
import os
import stat

import pytest

from agentpulse.identity import IdentityManager


def test_identity_persists_across_restart(tmp_path):
    first = IdentityManager(tmp_path / "identity.json", tmp_path / "credential")
    agent_id = first.ensure_agent_id()
    second = IdentityManager(tmp_path / "identity.json", tmp_path / "credential")
    assert second.ensure_agent_id() == agent_id
    assert len(agent_id) == 36


def test_identity_not_based_only_on_hostname(tmp_path):
    a = IdentityManager(tmp_path / "a.json", tmp_path / "a.cred")
    b = IdentityManager(tmp_path / "b.json", tmp_path / "b.cred")
    assert a.ensure_agent_id() != b.ensure_agent_id()


def test_credentials_written_with_secure_permissions(tmp_path):
    manager = IdentityManager(tmp_path / "nested" / "identity.json", tmp_path / "nested" / "credential")
    manager.store_credential("credential-value")
    assert stat.S_IMODE(os.stat(tmp_path / "nested").st_mode) == 0o700
    assert stat.S_IMODE(os.stat(tmp_path / "nested" / "credential").st_mode) == 0o600
    assert manager.read_credential() == "credential-value"


def test_credential_rotation_is_atomic(tmp_path):
    manager = IdentityManager(tmp_path / "identity.json", tmp_path / "credential")
    manager.store_credential("old")
    manager.rotate_credential("new")
    assert manager.read_credential() == "new"


def test_status_never_prints_credentials(tmp_path):
    manager = IdentityManager(tmp_path / "identity.json", tmp_path / "credential")
    manager.store_credential("do-not-leak")
    status = manager.status()
    assert "do-not-leak" not in json.dumps(status)
    assert "credential" not in status


def test_enrollment_persists_agent_id_and_credential(tmp_path):
    manager = IdentityManager(tmp_path / "identity.json", tmp_path / "credential")
    response = {"agent_id": "agent-uuid", "auth_token": "enrolled-secret"}

    class Response:
        status = 201
        def read(self, _limit=-1):
            return json.dumps(response).encode()
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False

    def opener(request, timeout):
        assert request.get_method() == "POST"
        assert request.headers["Content-type"] == "application/json"
        return Response()

    result = manager.enroll("http://localhost:8088", "enrollment-token-123456", "host", opener=opener)
    assert result["agent_id"] == "agent-uuid"
    assert manager.ensure_agent_id() == "agent-uuid"
    assert manager.read_credential() == "enrolled-secret"


def test_missing_identity_is_created_with_uuid(tmp_path):
    manager = IdentityManager(tmp_path / "identity.json", tmp_path / "credential")
    assert manager.ensure_agent_id()
    assert (tmp_path / "identity.json").exists()
    assert stat.S_IMODE(os.stat(tmp_path / "identity.json").st_mode) == 0o600


def test_invalid_credential_is_rejected(tmp_path):
    manager = IdentityManager(tmp_path / "identity.json", tmp_path / "credential")
    with pytest.raises(ValueError):
        manager.store_credential("bad\ncredential")


def test_hostname_is_metadata_not_identity(tmp_path):
    manager = IdentityManager(tmp_path / "identity.json", tmp_path / "credential")
    manager.ensure_agent_id(hostname="host-a")
    assert manager.status()["hostname"] == "host-a"
    assert manager.ensure_agent_id(hostname="host-b") == manager.status()["agent_id"]
    assert manager.status()["hostname"] == "host-b"


def test_identity_file_does_not_contain_credential(tmp_path):
    manager = IdentityManager(tmp_path / "identity.json", tmp_path / "credential")
    manager.ensure_agent_id()
    manager.store_credential("secret-value")
    assert "secret-value" not in (tmp_path / "identity.json").read_text()
