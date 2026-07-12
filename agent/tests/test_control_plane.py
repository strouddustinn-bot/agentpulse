"""RED contract for the AgentPulse SaaS control-plane client."""

import json
import os
import stat
import tempfile
import unittest
from unittest import mock

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


class TestControlPlaneConfig(unittest.TestCase):
    def test_defaults_disabled_and_credential_outside_json(self):
        cfg = config.from_dict({})
        self.assertFalse(cfg.control_plane.enabled)
        self.assertEqual(cfg.control_plane.credential_file, "/etc/agentpulse/agent.credential")
        self.assertFalse(hasattr(cfg.control_plane, "secret"))

    def test_enabled_control_plane_requires_https(self):
        with self.assertRaises(config.ConfigError):
            config.from_dict({"control_plane": {"enabled": True, "base_url": "http://example.com"}})

    def test_localhost_http_is_allowed_for_development(self):
        cfg = config.from_dict({"control_plane": {"enabled": True, "base_url": "http://127.0.0.1:8787"}})
        self.assertTrue(cfg.control_plane.enabled)


class TestCredentialFile(unittest.TestCase):
    def setUp(self):
        from agentpulse import control_plane
        self.control_plane = control_plane
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "credential")

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_and_read_credential_mode_0600(self):
        self.control_plane.write_credential(self.path, "ap_agent_secret")
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
        self.assertEqual(self.control_plane.read_credential(self.path), "ap_agent_secret")

    def test_rejects_symlink_and_permissive_mode(self):
        target = os.path.join(self.tmp.name, "target")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("ap_agent_secret\n")
        os.chmod(target, 0o644)
        with self.assertRaises(self.control_plane.CredentialError):
            self.control_plane.read_credential(target)
        link = os.path.join(self.tmp.name, "link")
        os.symlink(target, link)
        with self.assertRaises(self.control_plane.CredentialError):
            self.control_plane.read_credential(link)


class TestEnrollmentAndHeartbeat(unittest.TestCase):
    def setUp(self):
        from agentpulse import control_plane
        self.control_plane = control_plane
        self.tmp = tempfile.TemporaryDirectory()
        self.credential_file = os.path.join(self.tmp.name, "credential")

    def tearDown(self):
        self.tmp.cleanup()

    def test_enrollment_exchanges_token_and_persists_only_agent_credential(self):
        captured = {}

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["authorization"] = request.headers.get("Authorization")
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse(201, {"agent_id": "id-1", "agent_credential": "ap_agent_unique", "agent_key": "node-1"})

        result = self.control_plane.enroll(
            base_url="https://control.example",
            enrollment_token="ap_enroll_once",
            agent_key="node-1",
            hostname="host-1",
            local_policy_ceiling="alert",
            credential_file=self.credential_file,
            opener=opener,
        )
        self.assertEqual(result["agent_id"], "id-1")
        self.assertEqual(captured["url"], "https://control.example/v1/agents/enroll")
        self.assertEqual(captured["authorization"], "Bearer ap_enroll_once")
        self.assertNotIn("ap_enroll_once", json.dumps(captured["body"]))
        self.assertEqual(self.control_plane.read_credential(self.credential_file), "ap_agent_unique")

    def test_heartbeat_is_bounded_idempotent_and_authenticated(self):
        self.control_plane.write_credential(self.credential_file, "ap_agent_unique")
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
        result = self.control_plane.push_heartbeat(
            base_url="https://control.example",
            credential_file=self.credential_file,
            state=state,
            summary={"observations": 3, "breaches": 1, "errors": []},
            cycle_id="cycle-1",
            opener=opener,
        )
        self.assertTrue(result.ok)
        self.assertEqual(captured["url"], "https://control.example/v1/agents/heartbeat")
        self.assertEqual(captured["authorization"], "Bearer ap_agent_unique")
        self.assertEqual(captured["body"]["idempotency_key"], "cycle-1")
        self.assertLessEqual(len(captured["body"]["incidents"]), 50)
        self.assertNotIn("ap_agent_unique", json.dumps(captured["body"]))

    def test_network_and_subscription_failures_do_not_raise(self):
        self.control_plane.write_credential(self.credential_file, "ap_agent_unique")

        def payment_required(_request, _timeout):
            return FakeResponse(402, {"error": {"code": "subscription_inactive"}})

        result = self.control_plane.push_heartbeat(
            base_url="https://control.example",
            credential_file=self.credential_file,
            state={},
            summary={},
            cycle_id="cycle-2",
            opener=payment_required,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.status, 402)
        self.assertEqual(result.error, "subscription_inactive")

    def test_remote_policy_is_narrowed_again_on_host(self):
        self.control_plane.write_credential(self.credential_file, "ap_agent_unique")

        def opener(_request, _timeout):
            return FakeResponse(200, {"version": 1, "policy": {"checks": {"disk": {"mode": "auto"}}}})

        result = self.control_plane.fetch_policy(
            base_url="https://control.example",
            credential_file=self.credential_file,
            local_ceiling="ask",
            opener=opener,
        )
        self.assertEqual(result["policy"]["checks"]["disk"]["mode"], "ask")


if __name__ == "__main__":
    unittest.main()
