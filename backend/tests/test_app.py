import tempfile
import unittest
from pathlib import Path

from agentpulse_backend.app import create_app
from agentpulse_backend.store import Store
from fastapi.testclient import TestClient

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


class AppTests(unittest.TestCase):
    def make_client(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        db_path = str(Path(tempdir.name) / "backend.db")
        store = Store(db_path)
        store.init_db()
        token = store.create_api_key(org_id="org-1", label="test")
        license_key = store.create_license(org_id="org-1", plan="pro", max_agents=5)
        client = TestClient(create_app(db_path=db_path))
        return client, token, license_key

    def test_health(self):
        client, _token, _license = self.make_client()
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_checkin_requires_bearer_token(self):
        client, _token, _license = self.make_client()
        response = client.post("/api/agent/checkin", json=PAYLOAD)
        self.assertEqual(response.status_code, 401)

    def test_checkin_records_agent_and_history(self):
        client, token, _license = self.make_client()
        headers = {"Authorization": f"Bearer {token}"}

        response = client.post("/api/agent/checkin", json=PAYLOAD, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["agent_id"], "host-1")

        agents = client.get("/api/agents", headers=headers)
        self.assertEqual(agents.status_code, 200)
        self.assertEqual(agents.json()["agents"][0]["agent_id"], "host-1")

        history = client.get("/api/agents/host-1/checkins", headers=headers)
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.json()["checkins"]), 1)

    def test_checkin_rejects_invalid_status(self):
        client, token, _license = self.make_client()
        response = client.post(
            "/api/agent/checkin",
            json=dict(PAYLOAD, status="weird"),
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 422)

    def test_checkin_rejects_negative_counter(self):
        client, token, _license = self.make_client()
        headers = {"Authorization": f"Bearer {token}"}
        for counter in (
            "observations",
            "breaches",
            "actions",
            "queued",
            "alerts",
            "anomalies",
            "escalations",
            "blocked",
            "errors",
        ):
            with self.subTest(counter=counter):
                response = client.post(
                    "/api/agent/checkin",
                    json=dict(PAYLOAD, **{counter: -1}),
                    headers=headers,
                )
                self.assertEqual(response.status_code, 422)

    def test_checkin_rejects_empty_required_string(self):
        client, token, _license = self.make_client()
        headers = {"Authorization": f"Bearer {token}"}
        for field in ("agent_id", "hostname", "timestamp", "version"):
            with self.subTest(field=field):
                response = client.post(
                    "/api/agent/checkin",
                    json=dict(PAYLOAD, **{field: "  "}),
                    headers=headers,
                )
                self.assertEqual(response.status_code, 422)

    def test_checkin_openapi_publishes_request_schema(self):
        client, _token, _license = self.make_client()

        openapi = client.get("/openapi.json").json()
        schema = openapi["paths"]["/api/agent/checkin"]["post"]["requestBody"][
            "content"
        ]["application/json"]["schema"]
        self.assertEqual(schema, {"$ref": "#/components/schemas/CheckinRequest"})

        checkin = openapi["components"]["schemas"]["CheckinRequest"]
        self.assertEqual(
            checkin["required"],
            [
                "agent_id",
                "hostname",
                "status",
                "timestamp",
                "version",
            ],
        )
        self.assertEqual(
            checkin["properties"]["status"]["enum"], ["ok", "attention", "error"]
        )
        self.assertEqual(checkin["properties"]["breaches"]["minimum"], 0)

    def test_license_verify(self):
        client, _token, license_key = self.make_client()
        response = client.post(
            "/api/license/verify",
            json={"license_key": license_key, "agent_id": "host-1"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["active"])
        self.assertEqual(body["plan"], "pro")


if __name__ == "__main__":
    unittest.main()
