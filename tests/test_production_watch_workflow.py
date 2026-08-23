from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "production-watch.yml"


class ProductionWatchWorkflowTests(unittest.TestCase):
    def test_watch_is_read_only_bounded_and_durable(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("schedule:", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("simulate_failure:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("issues: write", workflow)
        self.assertIn("cancel-in-progress: false", workflow)

        self.assertIn("EXPECTED_VERSION: 0.2.0b6", workflow)
        self.assertIn(
            "EXPECTED_SOURCE_SHA: 9d128c054ba9c5c6e985610fe725e7b8069f3e1b",
            workflow,
        )
        self.assertIn("RELEASE_REF: v0.2.0-beta.8", workflow)
        self.assertIn("python scripts/production-smoke.py", workflow)
        self.assertIn("https://agentpulse.ca/", workflow)

        for probe in (
            "probe_checkout enterprise 422",
            "probe_checkout pro 404",
            "probe_checkout business 404",
        ):
            self.assertIn(probe, workflow)

        self.assertNotIn("probe_checkout starter", workflow)
        self.assertNotIn('\\"plan\\":\\"starter\\"', workflow)

        for provider_secret in (
            "CLOUDFLARE_API_TOKEN",
            "CLOUDFLARE_ACCOUNT_ID",
            "STRIPE_API_KEY",
            "STRIPE_WEBHOOK_SECRET",
        ):
            self.assertNotIn(provider_secret, workflow)

        self.assertIn("[ops] AgentPulse production synthetic alert", workflow)
        self.assertIn("gh issue create", workflow)
        self.assertIn("gh issue comment", workflow)
        self.assertIn("gh issue close", workflow)
        self.assertIn("Fail visibly after incident recording", workflow)


if __name__ == "__main__":
    unittest.main()
