import tempfile
import unittest
from pathlib import Path

from agentpulse_backend.store import Store, StoreError, normalize_checkin_payload

PAYLOAD = {
    "agent_id": "host-1",
    "hostname": "host-1.example",
    "status": "ok",
    "observations": 3,
    "breaches": 0,
    "actions": 0,
    "queued": 0,
    "alerts": 0,
    "anomalies": 0,
    "escalations": 0,
    "blocked": 0,
    "errors": 0,
    "timestamp": "2026-07-07T00:00:00Z",
    "version": "0.1.0",
}


class StoreTests(unittest.TestCase):
    def make_store(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        store = Store(str(Path(tempdir.name) / "backend.db"))
        store.init_db()
        return store

    def test_api_key_round_trip(self):
        store = self.make_store()
        token = store.create_api_key(org_id="org-1", label="agent")

        principal = store.authenticate_api_key(token)

        self.assertIsNotNone(principal)
        self.assertEqual(principal.org_id, "org-1")
        self.assertEqual(principal.label, "agent")
        self.assertIsNone(store.authenticate_api_key("wrong"))

    def test_record_checkin_upserts_agent_and_appends_history(self):
        store = self.make_store()

        first = store.record_checkin(org_id="org-1", payload=PAYLOAD)
        second_payload = dict(PAYLOAD, status="attention", breaches=1)
        second = store.record_checkin(org_id="org-1", payload=second_payload)

        self.assertEqual(first["agent_id"], "host-1")
        self.assertEqual(second["status"], "attention")
        agents = store.list_agents(org_id="org-1")
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]["status"], "attention")
        history = store.list_checkins(org_id="org-1", agent_id="host-1")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["status"], "attention")

    def test_normalize_rejects_bad_payload(self):
        with self.assertRaises(StoreError):
            normalize_checkin_payload({"agent_id": "host"})
        bad = dict(PAYLOAD, status="weird")
        with self.assertRaises(StoreError):
            normalize_checkin_payload(bad)
        bad_count = dict(PAYLOAD, breaches=-1)
        with self.assertRaises(StoreError):
            normalize_checkin_payload(bad_count)

    def test_license_round_trip_and_agent_limit(self):
        store = self.make_store()
        license_key = store.create_license(org_id="org-1", plan="pro", max_agents=1)

        ok = store.verify_license(license_key=license_key, agent_id="host-1")
        self.assertTrue(ok.active)
        self.assertEqual(ok.plan, "pro")

        store.record_checkin(org_id="org-1", payload=PAYLOAD)
        over = store.verify_license(license_key=license_key, agent_id="host-2")
        self.assertFalse(over.active)
        self.assertEqual(over.reason, "agent limit reached")

    def test_license_rejects_unknown_key(self):
        store = self.make_store()
        result = store.verify_license(license_key="apl_missing", agent_id="host-1")
        self.assertFalse(result.active)
        self.assertEqual(result.reason, "license not found")


if __name__ == "__main__":
    unittest.main()
