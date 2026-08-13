"""Regression tests for idempotent production Pages bootstrap."""

from __future__ import annotations

import importlib.util
import io
import json
import urllib.error
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ensure-pages-project.py"


def load_module():
    spec = importlib.util.spec_from_file_location("ensure_pages_project", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def response(project: dict) -> Response:
    return Response(json.dumps({"success": True, "result": project}).encode("utf-8"))


class EnsurePagesProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()

    @staticmethod
    def project(branch: str = "production") -> dict:
        return {"name": "agentpulse-production-app", "production_branch": branch}

    def test_existing_project_is_reused_without_post(self) -> None:
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return response(self.project())

        disposition = self.module.ensure_pages_project(
            "account-id",
            "secret-token",
            "agentpulse-production-app",
            "production",
            opener=opener,
        )

        self.assertEqual(disposition, "reused")
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0][0].get_method(), "GET")
        self.assertNotIn("secret-token", requests[0][0].full_url)

    def test_missing_project_is_created_with_approved_identity(self) -> None:
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            if len(requests) == 1:
                raise urllib.error.HTTPError(request.full_url, 404, "not found", {}, None)
            return response(self.project())

        disposition = self.module.ensure_pages_project(
            "account-id",
            "secret-token",
            "agentpulse-production-app",
            "production",
            opener=opener,
        )

        self.assertEqual(disposition, "created")
        self.assertEqual([item[0].get_method() for item in requests], ["GET", "POST"])
        self.assertEqual(
            json.loads(requests[1][0].data),
            {"name": "agentpulse-production-app", "production_branch": "production"},
        )

    def test_existing_project_with_wrong_branch_fails_closed(self) -> None:
        def opener(_request, timeout):
            self.assertEqual(timeout, 30)
            return response(self.project("master"))

        with self.assertRaisesRegex(RuntimeError, "branch is invalid"):
            self.module.ensure_pages_project(
                "account-id",
                "secret-token",
                "agentpulse-production-app",
                "production",
                opener=opener,
            )


if __name__ == "__main__":
    unittest.main()
