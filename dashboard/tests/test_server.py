"""Unit tests for the AgentPulse dashboard backend (pulse_server).

Stdlib unittest per repo convention. Uses temp dirs for DB and state files;
never touches the real agent state. Subprocess calls are always mocked.
"""

import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pulse_server.db import Db
from pulse_server.ingest import MetricSampler, StateWatcher


# ---------------------------------------------------------------------------
# db.py
# ---------------------------------------------------------------------------

class TestDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Db(os.path.join(self.tmp.name, "pulse.db"))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_history_dedupe(self):
        e = {"ts": 123.0, "action": "disk_cleanup", "target": "/tmp/x",
             "outcome": "succeeded"}
        self.assertTrue(self.db.record_history(e))
        self.assertFalse(self.db.record_history(e))
        self.assertEqual(len(self.db.history()), 1)

    def test_history_pagination(self):
        for i in range(1, 6):
            self.db.record_history(
                {"ts": float(i), "action": "a%d" % i, "target": "t",
                 "outcome": "succeeded"})
        page1 = self.db.history(limit=2)
        self.assertEqual([r["ts"] for r in page1], [5.0, 4.0])
        page2 = self.db.history(limit=2, before_ts=4.0)
        self.assertEqual([r["ts"] for r in page2], [3.0, 2.0])

    def test_samples_roundtrip(self):
        self.db.record_sample("mem", 41.5, ts=100.0)
        self.db.record_sample("mem", 43.0, ts=200.0)
        got = self.db.samples("mem", since=150.0)
        self.assertEqual(got, [{"ts": 200.0, "value": 43.0}])

    def test_metrics_names(self):
        self.db.record_sample("mem", 1.0, ts=1.0)
        self.db.record_sample("load1", 2.0, ts=1.0)
        self.db.record_sample("mem", 3.0, ts=2.0)
        self.assertEqual(sorted(self.db.metrics()), ["load1", "mem"])

    def test_events_recorded(self):
        self.db.record_event("ingest_error", "boom")
        evs = self.db.events(limit=10)
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["kind"], "ingest_error")
        self.assertEqual(evs[0]["detail"], "boom")

    def test_prune_removes_old_samples_and_events(self):
        old = time.time() - 100 * 86400
        self.db.record_sample("mem", 1.0, ts=old)
        self.db.record_sample("mem", 2.0)  # now
        self.db._conn.execute(  # backdate an event
            "INSERT INTO events (ts, kind, detail) VALUES (?, ?, ?)",
            (old, "old", "x"))
        self.db._conn.commit()
        self.db.record_event("new", "y")
        self.db.prune(keep_days=90)
        self.assertEqual(len(self.db.samples("mem", since=0)), 1)
        evs = self.db.events(limit=10)
        self.assertEqual([e["kind"] for e in evs], ["new"])

    def test_history_never_pruned(self):
        old = time.time() - 100 * 86400
        self.db.record_history({"ts": old, "action": "a", "target": "t",
                                "outcome": "succeeded"})
        self.db.prune(keep_days=90)
        self.assertEqual(len(self.db.history()), 1)

    def test_creates_parent_dirs(self):
        path = os.path.join(self.tmp.name, "deep", "nested", "pulse.db")
        db2 = Db(path)
        try:
            self.assertTrue(os.path.isfile(path))
        finally:
            db2.close()

    def test_close_is_idempotent(self):
        db2 = Db(os.path.join(self.tmp.name, "c.db"))
        db2.close()
        db2.close()  # must not raise

    def test_fleet_agent_upsert_is_persistent_and_replaces_state(self):
        self.db.upsert_agent("node-1", "web-01", {"last_run": 1.0})
        first = self.db.fleet_agents()
        self.assertEqual(first["node-1"]["hostname"], "web-01")
        self.assertEqual(first["node-1"]["state"]["last_run"], 1.0)

        self.db.upsert_agent("node-1", "web-01", {"last_run": 2.0})
        second = self.db.fleet_agents()
        self.assertEqual(len(second), 1)
        self.assertEqual(second["node-1"]["state"]["last_run"], 2.0)


# ---------------------------------------------------------------------------
# ingest.py — StateWatcher
# ---------------------------------------------------------------------------

class TestStateWatcher(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Db(os.path.join(self.tmp.name, "pulse.db"))
        self.state_path = os.path.join(self.tmp.name, "state.json")
        self.events = []

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def _write_state(self, data):
        with open(self.state_path, "w") as fh:
            json.dump(data, fh)

    def _watcher(self, path=None):
        return StateWatcher(path or self.state_path, self.db,
                            emit=self.events.append)

    def test_detects_new_history_and_emits(self):
        self._write_state({
            "last_run": 111.0,
            "pending": {},
            "history": [{"ts": 1.0, "action": "a", "target": "t",
                         "outcome": "succeeded"}],
            "blocked_ips": {},
        })
        w = self._watcher()
        w.poll_once()
        self.assertEqual(len(self.db.history()), 1)
        kinds = [e["type"] for e in self.events]
        self.assertIn("state", kinds)
        self.assertIn("history", kinds)

    def test_missing_file_is_quiet(self):
        w = self._watcher(os.path.join(self.tmp.name, "nope.json"))
        w.poll_once()  # must not raise
        self.assertEqual(self.db.history(), [])
        self.assertEqual(self.events, [])

    def test_invalid_json_never_crashes(self):
        with open(self.state_path, "w") as fh:
            fh.write("{not json!!")
        w = self._watcher()
        w.poll_once()  # must not raise
        self.assertEqual(self.db.history(), [])
        kinds = [e["kind"] for e in self.db.events(limit=10)]
        self.assertIn("ingest_error", kinds)

    def test_non_dict_json_never_crashes(self):
        with open(self.state_path, "w") as fh:
            fh.write("[1, 2, 3]")
        w = self._watcher()
        w.poll_once()  # must not raise
        self.assertEqual(self.db.history(), [])

    def test_pending_dict_or_list_normalized(self):
        self._write_state({"pending": {"abc123": {"id": "abc123"}},
                           "history": [], "blocked_ips": {}})
        w = self._watcher()
        w.poll_once()
        state_ev = [e for e in self.events if e["type"] == "state"][-1]
        self.assertEqual(state_ev["data"]["pending"], [{"id": "abc123"}])

        self.events.clear()
        self._write_state({"pending": [{"id": "def456"}],
                           "history": [], "blocked_ips": [{"ip": "1.2.3.4"}]})
        w.force_refresh()
        state_ev = [e for e in self.events if e["type"] == "state"][-1]
        self.assertEqual(state_ev["data"]["pending"], [{"id": "def456"}])
        self.assertEqual(state_ev["data"]["blocked_ips"], [{"ip": "1.2.3.4"}])

    def test_unchanged_file_not_reemitted(self):
        self._write_state({"pending": {}, "history": [], "blocked_ips": {}})
        w = self._watcher()
        w.poll_once()
        n = len(self.events)
        w.poll_once()  # same mtime_ns/size — no new events
        self.assertEqual(len(self.events), n)

    def test_force_refresh_bypasses_change_detection(self):
        self._write_state({"pending": {}, "history": [], "blocked_ips": {}})
        w = self._watcher()
        w.poll_once()
        n = len(self.events)
        w.force_refresh()  # unchanged mtime, must still re-read + emit
        self.assertGreater(len(self.events), n)


# ---------------------------------------------------------------------------
# ingest.py — MetricSampler
# ---------------------------------------------------------------------------

class TestMetricSampler(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Db(os.path.join(self.tmp.name, "pulse.db"))
        self.events = []

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_sample_once_records_and_emits(self):
        s = MetricSampler(self.db, disk_paths=["/"], emit=self.events.append)
        s.sample_once()
        names = self.db.metrics()
        self.assertIn("mem", names)      # /proc/meminfo exists on Linux
        self.assertIn("load1", names)
        self.assertIn("disk:/", names)
        self.assertEqual(self.events[-1]["type"], "metrics")
        self.assertIn("values", self.events[-1]["data"])

    def test_bad_disk_path_is_skipped(self):
        s = MetricSampler(self.db, disk_paths=["/definitely/not/here"],
                          emit=self.events.append)
        s.sample_once()  # must not raise
        self.assertNotIn("disk:/definitely/not/here", self.db.metrics())


# ---------------------------------------------------------------------------
# actions.py
# ---------------------------------------------------------------------------

class TestActions(unittest.TestCase):
    def setUp(self):
        from pulse_server import actions
        self.actions = actions
        self.tmp = tempfile.TemporaryDirectory()
        self.agent_dir = self.tmp.name
        self.config = os.path.join(self.tmp.name, "config.json")
        with open(self.config, "w") as fh:
            fh.write("{}")

    def tearDown(self):
        self.tmp.cleanup()

    def _no_subprocess(self):
        return mock.patch.object(
            self.actions.subprocess, "run",
            side_effect=AssertionError("subprocess must not be called"))

    def test_malicious_ids_rejected_without_subprocess(self):
        bad = ["", "ABC123", "abc12", "a" * 13, "abc-123", "../../etc",
               "abc123; rm -rf /", "$(reboot)", "abc 123", "aBc123",
               "1234567890abcdefg"]
        with self._no_subprocess():
            for pid in bad:
                ok, msg = self.actions.approve(self.agent_dir, self.config, pid)
                self.assertFalse(ok, pid)
                self.assertIn("invalid pending id", msg)

    def test_invalid_verb_rejected(self):
        with self._no_subprocess():
            ok, msg = self.actions._run_agent(
                self.agent_dir, self.config, "execute", "abc123")
        self.assertFalse(ok)
        self.assertIn("invalid verb", msg)

    def test_missing_agent_dir_rejected_without_subprocess(self):
        with self._no_subprocess():
            ok, msg = self.actions.approve("/nope/agent", self.config, "abc123")
        self.assertFalse(ok)
        self.assertIn("agent dir", msg)

    def test_missing_config_rejected_without_subprocess(self):
        with self._no_subprocess():
            ok, msg = self.actions.approve(
                self.agent_dir, "/nope/config.json", "abc123")
        self.assertFalse(ok)
        self.assertIn("config", msg)

    def test_success_uses_argv_list_never_shell(self):
        completed = mock.Mock(returncode=0, stdout="approved: x\n", stderr="")
        with mock.patch.object(self.actions.subprocess, "run",
                               return_value=completed) as run:
            ok, out = self.actions.approve(self.agent_dir, self.config, "abc123")
        self.assertTrue(ok)
        self.assertEqual(out, "approved: x")
        args, kwargs = run.call_args
        cmd = args[0]
        self.assertIsInstance(cmd, list)
        self.assertEqual(cmd[1:4], ["-m", "agentpulse", "approve"])
        self.assertEqual(cmd[-1], "abc123")
        self.assertNotIn("shell", kwargs)  # never shell=True
        self.assertIn("timeout", kwargs)

    def test_nonzero_exit_is_failure(self):
        completed = mock.Mock(returncode=2, stdout="", stderr="no pending\n")
        with mock.patch.object(self.actions.subprocess, "run",
                               return_value=completed):
            ok, out = self.actions.deny(self.agent_dir, self.config, "abc123")
        self.assertFalse(ok)
        self.assertIn("no pending", out)

    def test_timeout_handled(self):
        exc = self.actions.subprocess.TimeoutExpired(cmd="x", timeout=1)
        with mock.patch.object(self.actions.subprocess, "run", side_effect=exc):
            ok, msg = self.actions.approve(self.agent_dir, self.config, "abc123")
        self.assertFalse(ok)
        self.assertIn("timed out", msg)

    def test_oserror_handled(self):
        with mock.patch.object(self.actions.subprocess, "run",
                               side_effect=OSError("exec failed")):
            ok, msg = self.actions.approve(self.agent_dir, self.config, "abc123")
        self.assertFalse(ok)
        self.assertIn("exec failed", msg)


# ---------------------------------------------------------------------------
# main.py — app factory, routes, auth, SSE plumbing
# ---------------------------------------------------------------------------

class TestApp(unittest.TestCase):
    TOKEN = "secr3t-token"

    def setUp(self):
        from fastapi.testclient import TestClient
        from pulse_server.main import Settings, create_app

        self.tmp = tempfile.TemporaryDirectory()
        self.state_path = os.path.join(self.tmp.name, "state.json")
        with open(self.state_path, "w") as fh:
            json.dump({
                "last_run": 999.0,
                "pending": {"abc123": {"id": "abc123", "action": "service_restart"}},
                "history": [{"ts": 5.0, "action": "a", "target": "t",
                             "outcome": "succeeded"}],
                "blocked_ips": {},
            }, fh)
        self.agent_dir = self.tmp.name
        self.config = os.path.join(self.tmp.name, "config.json")
        with open(self.config, "w") as fh:
            fh.write("{}")

        self.settings = Settings(
            state_file=self.state_path,
            agent_dir=self.agent_dir,
            agent_config=self.config,
            db_path=os.path.join(self.tmp.name, "pulse.db"),
            token=self.TOKEN,
            disk_paths=["/"],
            web_dist=os.path.join(self.tmp.name, "no-dist"),
            enable_background=False,
        )
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        self.client.__enter__()  # run lifespan (primes watcher snapshot)

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def _auth(self, token=None):
        return {"Authorization": f"Bearer {token or self.TOKEN}"}

    def test_health(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["last_run"], 999.0)

    def test_state(self):
        r = self.client.get("/api/state")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["last_run"], 999.0)
        self.assertEqual(body["pending"][0]["id"], "abc123")

    def test_history_endpoint_and_limit_bounds(self):
        r = self.client.get("/api/history")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["history"]), 1)
        self.assertEqual(self.client.get("/api/history?limit=0").status_code, 422)
        self.assertEqual(self.client.get("/api/history?limit=501").status_code, 422)
        self.assertEqual(self.client.get("/api/history?limit=500").status_code, 200)

    def test_metrics_endpoint_and_hours_bounds(self):
        r = self.client.get("/api/metrics")
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), dict)
        self.assertEqual(self.client.get("/api/metrics?hours=0").status_code, 422)
        self.assertEqual(self.client.get("/api/metrics?hours=-1").status_code, 422)
        self.assertEqual(self.client.get("/api/metrics?hours=10000").status_code, 422)

    def test_mutation_requires_token(self):
        r = self.client.post("/api/pending/abc123/approve")
        self.assertEqual(r.status_code, 401)
        r = self.client.post("/api/pending/abc123/approve",
                             headers=self._auth("wrong-token"))
        self.assertEqual(r.status_code, 401)

    def test_empty_token_fails_closed(self):
        from fastapi.testclient import TestClient
        from pulse_server.main import Settings, create_app
        import dataclasses
        settings = dataclasses.replace(self.settings, token="",
                                       db_path=os.path.join(self.tmp.name, "p2.db"))
        app = create_app(settings)
        with TestClient(app) as client:
            r = client.post("/api/pending/abc123/approve",
                            headers={"Authorization": "Bearer "})
            self.assertEqual(r.status_code, 401)
            r = client.post("/api/pending/abc123/approve")
            self.assertEqual(r.status_code, 401)

    def test_heartbeat_requires_ingest_token_and_populates_fleet(self):
        from fastapi.testclient import TestClient
        from pulse_server.main import create_app
        import dataclasses

        settings = dataclasses.replace(
            self.settings,
            ingest_token="ingest-secret",
            db_path=os.path.join(self.tmp.name, "fleet.db"),
        )
        app = create_app(settings)
        payload = {
            "agent_id": "node-1",
            "hostname": "web-01",
            "state": {"last_run": 123.0, "pending": [], "history": []},
        }
        with TestClient(app) as client:
            self.assertEqual(client.post("/fleet/heartbeat", json=payload).status_code,
                             401)
            r = client.post(
                "/fleet/heartbeat",
                json=payload,
                headers={"Authorization": "Bearer ingest-secret"},
            )
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json()["ok"])
            fleet = client.get("/api/state").json()["fleet"]
            self.assertEqual(fleet["node-1"]["hostname"], "web-01")
            self.assertEqual(fleet["node-1"]["state"]["last_run"], 123.0)

    def test_heartbeat_rejects_invalid_agent_id(self):
        from fastapi.testclient import TestClient
        from pulse_server.main import create_app
        import dataclasses

        settings = dataclasses.replace(
            self.settings,
            ingest_token="ingest-secret",
            db_path=os.path.join(self.tmp.name, "invalid-fleet.db"),
        )
        app = create_app(settings)
        with TestClient(app) as client:
            r = client.post(
                "/fleet/heartbeat",
                json={"agent_id": "../../etc", "hostname": "bad", "state": {}},
                headers={"Authorization": "Bearer ingest-secret"},
            )
            self.assertEqual(r.status_code, 422)

    def test_read_password_protects_dashboard_but_not_health(self):
        from fastapi.testclient import TestClient
        from pulse_server.main import create_app
        import dataclasses

        settings = dataclasses.replace(
            self.settings,
            read_password="read-secret",
            db_path=os.path.join(self.tmp.name, "protected.db"),
        )
        app = create_app(settings)
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/health").status_code, 200)
            denied = client.get("/api/state")
            self.assertEqual(denied.status_code, 401)
            self.assertIn("Basic", denied.headers["www-authenticate"])
            self.assertEqual(
                client.get("/api/state", auth=("agentpulse", "wrong")).status_code,
                401,
            )
            self.assertEqual(
                client.get("/api/state", auth=("agentpulse", "read-secret")).status_code,
                200,
            )

    def test_approve_with_token_calls_action_and_refreshes(self):
        from pulse_server import main as main_mod
        with mock.patch.object(main_mod.actions, "approve",
                               return_value=(True, "approved: x")) as ap, \
             mock.patch.object(self.app.state.watcher, "force_refresh") as fr:
            r = self.client.post("/api/pending/abc123/approve",
                                 headers=self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        ap.assert_called_once_with(self.agent_dir, self.config, "abc123")
        fr.assert_called_once()

    def test_deny_failure_maps_to_409(self):
        from pulse_server import main as main_mod
        with mock.patch.object(main_mod.actions, "deny",
                               return_value=(False, "no pending action")):
            r = self.client.post("/api/pending/abc123/deny",
                                 headers=self._auth())
        self.assertEqual(r.status_code, 409)

    def test_malicious_id_rejected_via_api(self):
        r = self.client.post("/api/pending/%24%28reboot%29/approve",
                             headers=self._auth())
        self.assertIn(r.status_code, (400, 409))

    def test_sse_event_formatting(self):
        from pulse_server.main import format_sse
        out = format_sse({"type": "state", "data": {"x": 1}})
        self.assertTrue(out.startswith("data: "))
        self.assertTrue(out.endswith("\n\n"))
        self.assertEqual(json.loads(out[len("data: "):]),
                         {"type": "state", "data": {"x": 1}})

    def test_broker_subscribe_publish_unsubscribe(self):
        from pulse_server.main import EventBroker
        broker = EventBroker(max_subscribers=2)
        q1 = broker.subscribe()
        q2 = broker.subscribe()
        with self.assertRaises(RuntimeError):
            broker.subscribe()  # bounded
        broker.publish({"type": "x"})
        self.assertEqual(q1.get_nowait(), {"type": "x"})
        self.assertEqual(q2.get_nowait(), {"type": "x"})
        broker.unsubscribe(q1)
        broker.unsubscribe(q1)  # idempotent
        broker.publish({"type": "y"})
        self.assertTrue(q1.empty())
        self.assertEqual(q2.get_nowait(), {"type": "y"})

    def test_version(self):
        import pulse_server
        self.assertEqual(pulse_server.__version__, "0.1.0")


if __name__ == "__main__":
    unittest.main()
