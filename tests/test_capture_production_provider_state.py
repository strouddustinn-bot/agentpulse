"""Tests for fail-closed production provider-state capture."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "capture-production-provider-state.py"


def load_module():
    spec = importlib.util.spec_from_file_location("capture_production_provider_state", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProviderStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.capture = load_module()

    def test_script_is_executable(self) -> None:
        self.assertTrue(SCRIPT.stat().st_mode & 0o111)

    def response(self, result, *, status=200, success=True, errors=None):
        return self.capture.ApiResponse(
            status,
            {
                "success": success,
                "errors": [] if errors is None else errors,
                "messages": [],
                "result": result,
            },
        )

    def requester(self, workers, deployments):
        def request(url, _account_id, _api_token):
            if url.endswith("/workers/scripts"):
                return self.response(workers)
            self.assertIn("/deployments?env=production&page=1&per_page=1", url)
            return self.response(deployments)

        return request

    def test_empty_worker_and_pages_state_authorizes_first_deploy(self) -> None:
        state = self.capture.capture_state(
            "account",
            "token",
            "agentpulse-control-plane-production",
            "agentpulse-production-app",
            requester=self.requester([{"id": "another-worker"}], []),
        )
        self.assertEqual(
            state,
            {
                "schema_version": 1,
                "worker_name": "agentpulse-control-plane-production",
                "worker_present": False,
                "pages_project": "agentpulse-production-app",
                "production_pages_deployment_present": False,
                "bootstrap_allowed": True,
            },
        )

    def test_partial_worker_upload_keeps_bootstrap_recovery_open(self) -> None:
        state = self.capture.capture_state(
            "account",
            "token",
            "agentpulse-control-plane-production",
            "agentpulse-production-app",
            requester=self.requester(
                [{"id": "agentpulse-control-plane-production"}],
                [],
            ),
        )
        self.assertTrue(state["worker_present"])
        self.assertFalse(state["production_pages_deployment_present"])
        self.assertTrue(state["bootstrap_allowed"])

    def test_existing_production_pages_deployment_disables_bootstrap(self) -> None:
        deployments = [
            {
                "id": "deployment-id",
                "project_name": "agentpulse-production-app",
                "environment": "production",
            }
        ]
        for workers in (
            [],
            [{"id": "agentpulse-control-plane-production"}],
        ):
            with self.subTest(workers=workers):
                state = self.capture.capture_state(
                    "account",
                    "token",
                    "agentpulse-control-plane-production",
                    "agentpulse-production-app",
                    requester=self.requester(workers, deployments),
                )
                self.assertFalse(state["bootstrap_allowed"])

    def test_provider_and_schema_failures_block_instead_of_becoming_empty_state(self) -> None:
        invalid_responses = (
            self.response([], status=401),
            self.response([], success=False, errors=[{"code": 1000}]),
            self.capture.ApiResponse(200, {"success": True, "errors": [], "result": {}}),
        )
        for invalid in invalid_responses:
            with self.subTest(response=invalid):
                def request(_url, _account_id, _api_token):
                    return invalid

                with self.assertRaises(self.capture.CaptureError):
                    self.capture.capture_state(
                        "account",
                        "token",
                        "agentpulse-control-plane-production",
                        "agentpulse-production-app",
                        requester=request,
                    )

    def test_unrelated_or_malformed_entries_block(self) -> None:
        cases = (
            ([{}], []),
            (
                [],
                [
                    {
                        "id": "deployment-id",
                        "project_name": "wrong-project",
                        "environment": "production",
                    }
                ],
            ),
            (
                [],
                [
                    {
                        "id": "deployment-id",
                        "project_name": "agentpulse-production-app",
                        "environment": "preview",
                    }
                ],
            ),
        )
        for workers, deployments in cases:
            with self.subTest(workers=workers, deployments=deployments):
                with self.assertRaises(self.capture.CaptureError):
                    self.capture.capture_state(
                        "account",
                        "token",
                        "agentpulse-control-plane-production",
                        "agentpulse-production-app",
                        requester=self.requester(workers, deployments),
                    )


if __name__ == "__main__":
    unittest.main()
