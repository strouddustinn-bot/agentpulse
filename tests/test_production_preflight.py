"""Tests for the fail-closed Tier 4 production readiness preflight."""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "production-preflight.py"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "production-deploy.yml"


def load_module():
    spec = importlib.util.spec_from_file_location("production_preflight", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProductionPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.preflight = load_module()
        self.tmpdir = tempfile.TemporaryDirectory(prefix="agentpulse-production-preflight-")
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)

    def write_config(self, production: dict) -> Path:
        path = self.root / "wrangler.jsonc"
        path.write_text(
            json.dumps({"env": {"production": production}}, indent=2),
            encoding="utf-8",
        )
        return path

    def write_provider_state(self, **overrides) -> Path:
        payload = {
            "schema_version": 1,
            "worker_name": "agentpulse-control-plane-production",
            "worker_present": False,
            "pages_project": "agentpulse-production-app",
            "production_pages_deployment_present": False,
            "bootstrap_allowed": True,
        }
        payload.update(overrides)
        path = self.root / "provider-state.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    @staticmethod
    def valid_production_config() -> dict:
        return {
            "name": "agentpulse-control-plane-production",
            "routes": [{"pattern": "api.agentpulse.ca", "custom_domain": True}],
            "vars": {
                "ENVIRONMENT": "production",
                "PUBLIC_BASE_URL": "https://api.agentpulse.ca",
                "APP_BASE_URL": "https://app.agentpulse.ca",
                "AGENTPULSE_VERSION": "0.3.0",
                "CHECKOUT_MODE": "starter",
                "STRIPE_PORTAL_URL": "https://billing.stripe.com/p/login/6oU28rbSBgPS8Qa5CB7N600",
                "STRIPE_PRICE_STARTER": "price_1ProductionStarterABC",
                "STRIPE_PRICE_PRO": "price_1ProductionProABCDE",
                "STRIPE_PRICE_BUSINESS": "price_1ProductionBusinessA",
            },
            "d1_databases": [
                {
                    "binding": "DB",
                    "database_name": "agentpulse-production",
                    "database_id": "ab4f112d-24e0-4b5b-af9a-bafa8166304f",
                    "migrations_dir": "migrations",
                }
            ],
        }

    def test_current_production_configuration_passes_static_checks(self) -> None:
        findings = self.preflight.check_production_config(ROOT / "control-plane" / "wrangler.jsonc")
        self.assertEqual(findings, [])

    def portal_evidence(self) -> dict:
        return {
            "object": "list",
            "url": "/v1/billing_portal/configurations",
            "has_more": False,
            "data": [{
                "id": "bpc_fixture",
                "object": "billing_portal.configuration",
                "active": True,
                "livemode": True,
                "login_page": {
                    "enabled": True,
                    "url": self.valid_production_config()["vars"]["STRIPE_PORTAL_URL"],
                },
                "default_return_url": "https://app.agentpulse.ca/account",
                "features": {
                    "subscription_update": {"enabled": False},
                    "subscription_cancel": {
                        "enabled": True,
                        "mode": "at_period_end",
                        "proration_behavior": "none",
                    },
                    "payment_method_update": {"enabled": True},
                    "invoice_history": {"enabled": True},
                },
            }],
        }

    def portal_codes(self, evidence: object) -> set[str]:
        findings = self.preflight.check_stripe_portal_configuration(
            self.write_config(self.valid_production_config()),
            "fixture-key",
            fetcher=lambda _key: evidence,
        )
        return {finding.code for finding in findings}

    def test_portal_requires_the_exact_configured_live_login_not_the_default(self) -> None:
        evidence = self.portal_evidence()
        unrelated = copy.deepcopy(evidence["data"][0])
        unrelated["id"] = "bpc_unrelated"
        unrelated["is_default"] = True
        unrelated["login_page"]["url"] = "https://billing.stripe.com/p/login/otherbusiness"
        unrelated["features"]["subscription_update"]["enabled"] = True
        evidence["data"].insert(0, unrelated)
        self.assertEqual(self.portal_codes(evidence), set())
        evidence["data"].pop()
        self.assertEqual(self.portal_codes(evidence), {"stripe_portal_login_unmatched"})

    def test_portal_rejects_unsafe_or_missing_customer_controls(self) -> None:
        cases = [
            (("features", "subscription_update", "enabled"), True, "plan_changes"),
            (("features", "subscription_update", "enabled"), "false", "plan_changes"),
            (("features", "subscription_update"), {}, "plan_changes"),
            (("features", "subscription_cancel", "enabled"), False, "cancellation"),
            (("features", "subscription_cancel", "mode"), "immediately", "cancellation"),
            (("features", "subscription_cancel", "proration_behavior"), "always_invoice", "cancellation"),
            (("features", "payment_method_update", "enabled"), False, "payment_method"),
            (("features", "invoice_history", "enabled"), False, "invoice_history"),
            (("default_return_url",), "https://untrusted.example/account", "return_url"),
            (("default_return_url",), None, "return_url"),
        ]
        for fields, value, code in cases:
            with self.subTest(fields=fields, value=value):
                evidence = self.portal_evidence()
                target = evidence["data"][0]
                for field in fields[:-1]:
                    target = target[field]
                target[fields[-1]] = value
                self.assertIn(f"stripe_portal_{code}_invalid", self.portal_codes(evidence))

    def test_portal_rejects_test_disabled_or_malformed_configuration(self) -> None:
        for field, value in [("active", False), ("livemode", False), ("id", "wrong_object"), ("object", "customer")]:
            with self.subTest(field=field):
                evidence = self.portal_evidence()
                evidence["data"][0][field] = value
                self.assertEqual(self.portal_codes(evidence), {"stripe_portal_configuration_invalid"})
        evidence = self.portal_evidence()
        evidence["data"][0]["login_page"]["enabled"] = False
        self.assertEqual(self.portal_codes(evidence), {"stripe_portal_configuration_invalid"})
        evidence = self.portal_evidence()
        evidence["data"][0]["features"] = None
        self.assertEqual(self.portal_codes(evidence), {"stripe_portal_features_unverified"})

    def test_portal_requires_complete_unambiguous_provider_evidence(self) -> None:
        for field, value in [("has_more", True), ("has_more", 0), ("object", "configuration"), ("data", [None])]:
            with self.subTest(field=field, value=value):
                evidence = self.portal_evidence()
                evidence[field] = value
                self.assertEqual(self.portal_codes(evidence), {"stripe_portal_list_incomplete"})
        evidence = self.portal_evidence()
        evidence["data"].append(copy.deepcopy(evidence["data"][0]))
        self.assertEqual(self.portal_codes(evidence), {"stripe_portal_login_unmatched"})
        self.assertEqual(self.portal_codes(None), {"stripe_portal_list_incomplete"})

    def test_portal_access_failures_are_sanitized_and_fail_closed(self) -> None:
        config = self.write_config(self.valid_production_config())
        self.assertEqual(
            [item.code for item in self.preflight.check_stripe_portal_configuration(config, "")],
            ["stripe_portal_key_missing"],
        )
        for error in [
            self.preflight.StripeAPIError("permission"),
            self.preflight.StripeAPIError("sensitive-provider-response"),
            ValueError("sensitive-provider-response"),
        ]:
            with self.subTest(error=type(error).__name__):
                findings = self.preflight.check_stripe_portal_configuration(
                    config, "private-fixture-key", fetcher=mock.Mock(side_effect=error)
                )
                self.assertTrue(findings)
                self.assertNotIn("sensitive-provider-response", str(findings))
                self.assertNotIn("private-fixture-key", str(findings))

    def test_portal_provider_transport_is_read_only_and_bounded(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(self.portal_evidence()).encode()
        with mock.patch.object(self.preflight.urllib.request, "urlopen", return_value=response) as fetch:
            self.preflight._fetch_stripe_portal_configurations("fixture-key")
        request = fetch.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, "https://api.stripe.com/v1/billing_portal/configurations?active=true&limit=100")
        self.assertEqual(fetch.call_args.kwargs["timeout"], 15)
        response.read.assert_called_once_with(1_048_577)
        response.read.return_value = b"x" * 1_048_577
        with mock.patch.object(self.preflight.urllib.request, "urlopen", return_value=response):
            with self.assertRaises(ValueError):
                self.preflight._fetch_stripe_portal_configurations("fixture-key")

    def test_live_preflight_cannot_skip_portal_evidence_or_claim_it_from_static_checks(self) -> None:
        for static_only, blocked in [(False, True), (False, False), (True, False)]:
            with self.subTest(static_only=static_only, blocked=blocked), ExitStack() as stack:
                for name in [
                    "check_production_config", "check_release_ref", "check_release_ref_exists",
                    "check_phase5a_artifacts", "check_github_environment", "check_dns", "check_stripe_prices",
                ]:
                    stack.enter_context(mock.patch.object(self.preflight, name, return_value=[]))
                stack.enter_context(mock.patch.object(self.preflight, "check_bootstrap_provider_state", return_value=(False, [])))
                portal = stack.enter_context(mock.patch.object(
                    self.preflight, "check_stripe_portal_configuration",
                    return_value=[self.preflight.Finding("portal_fixture_block", "unverified")] if blocked else [],
                ))
                output = io.StringIO()
                stack.enter_context(redirect_stdout(output))
                args = ["--release-ref", "4c716664c40891971e9e6277e58f092523bf98d2"]
                if static_only:
                    args.append("--static-only")
                result = self.preflight.main(args)
                self.assertEqual(result, 1 if blocked else 0)
                self.assertEqual("stripe_live_portal=verified" in output.getvalue(), not static_only and not blocked)
                if static_only:
                    portal.assert_not_called()
                else:
                    portal.assert_called_once()

    def test_phase5a_artifacts_pass_static_checks(self) -> None:
        self.assertEqual(self.preflight.check_phase5a_artifacts(ROOT), [])

    def test_controlled_pilot_workflow_is_exact_tag_protected_and_fail_closed(self) -> None:
        text = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("- 'v0.2.0-beta.6'", text)
        self.assertNotIn("workflow_dispatch:", text)
        self.assertIn("environment: production", text)
        self.assertIn("permissions:\n  contents: read", text)
        self.assertIn("python scripts/production-preflight.py \\", text)
        self.assertIn('--release-ref "$RELEASE_REF"', text)
        self.assertIn("wrangler d1 export DB --env production --remote", text)
        self.assertIn("wrangler d1 migrations apply DB --env production --remote", text)
        self.assertIn("wrangler deploy --env production --strict", text)
        self.assertIn("--secrets-file \"$SECRETS_FILE\"", text)
        self.assertIn("wrangler pages deploy ../dashboard/dist", text)
        self.assertIn("python scripts/production-smoke.py", text)
        self.assertIn("starter_checkout=bounded", text)
        self.assertIn("probe_checkout enterprise 422", text)
        self.assertIn("probe_checkout pro 404", text)
        self.assertIn("probe_checkout business 404", text)
        self.assertNotIn('--data \'{"plan":"starter"}\'', text)
        self.assertIn("--only-verified --exclude-detectors=Lob", text)
        self.assertIn("python agent/tools/run_tests.py", text)
        self.assertIn("python scripts/validate-contracts.py", text)
        self.assertIn("python -m unittest tests.test_packaging -v", text)
        self.assertIn("npm audit --audit-level=high", text)
        self.assertIn("id: d1_export", text)
        self.assertIn(
            "if: ${{ !cancelled() && steps.d1_export.outcome == 'success' }}",
            text,
        )
        self.assertIn("d1_disposable_restore=pass", text)
        self.assertIn("wrangler versions deploy", text)
        self.assertIn("stripe_live_prices=verified", text)
        self.assertIn("python scripts/capture-production-provider-state.py", text)
        self.assertIn('--bootstrap-provider-state "$RUNNER_TEMP/provider-state.json"', text)
        self.assertIn("--attempts 12", text)
        self.assertNotIn("echo \"$STRIPE", text)

    def test_live_stripe_prices_require_exact_active_live_monthly_products(self) -> None:
        production = self.valid_production_config()
        config = self.write_config(production)
        expected_amounts = {"STARTER": 2900, "PRO": 9900, "BUSINESS": 29900}
        price_to_amount = {
            production["vars"][f"STRIPE_PRICE_{tier}"]: amount
            for tier, amount in expected_amounts.items()
        }

        def valid_fetcher(price_id: str, api_key: str):
            self.assertEqual(api_key, "sk_live_fixture")
            return {
                "id": price_id,
                "object": "price",
                "active": True,
                "livemode": True,
                "currency": "cad",
                "type": "recurring",
                "unit_amount": price_to_amount[price_id],
                "recurring": {"interval": "month", "interval_count": 1},
                "product": {"object": "product", "active": True, "livemode": True},
            }

        self.assertEqual(
            self.preflight.check_stripe_prices(
                config, "sk_live_fixture", fetcher=valid_fetcher
            ),
            [],
        )

        def test_mode_fetcher(price_id: str, api_key: str):
            payload = valid_fetcher(price_id, api_key)
            payload["livemode"] = False
            return payload

        findings = self.preflight.check_stripe_prices(
            config, "sk_live_fixture", fetcher=test_mode_fetcher
        )
        self.assertEqual(
            {finding.code for finding in findings},
            {
                "stripe_starter_price_mismatch",
                "stripe_pro_price_mismatch",
                "stripe_business_price_mismatch",
            },
        )

    def test_live_stripe_verification_fails_closed_for_missing_key_and_api_error(self) -> None:
        config = self.write_config(self.valid_production_config())
        self.assertEqual(
            [finding.code for finding in self.preflight.check_stripe_prices(config, "")],
            ["stripe_api_key_missing"],
        )

    def test_live_stripe_failures_are_safely_classified(self) -> None:
        config = self.write_config(self.valid_production_config())
        categories = {
            "authentication": "stripe_api_authentication_failed",
            "permission": "stripe_api_permission_denied",
            "rate_limited": "stripe_api_rate_limited",
            "unavailable": "stripe_api_unavailable",
        }
        for category, expected_code in categories.items():
            with self.subTest(category=category):
                def fail(*_args):
                    raise self.preflight.StripeAPIError(category)

                findings = self.preflight.check_stripe_prices(
                    config,
                    "sk_live_fixture",
                    fetcher=fail,
                )
                self.assertEqual([finding.code for finding in findings], [expected_code])

        findings = self.preflight.check_stripe_prices(
            config,
            "sk_live_fixture",
            fetcher=lambda *_: (_ for _ in ()).throw(
                self.preflight.StripeAPIError("unexpected")
            ),
        )
        self.assertEqual([finding.code for finding in findings], ["stripe_api_unavailable"])

        findings = self.preflight.check_stripe_prices(
            config,
            "sk_live_fixture",
            fetcher=lambda *_: (_ for _ in ()).throw(
                self.preflight.StripeAPIError("missing")
            ),
        )
        self.assertEqual(
            {finding.code for finding in findings},
            {
                "stripe_starter_price_missing",
                "stripe_pro_price_missing",
                "stripe_business_price_missing",
            },
        )

        findings = self.preflight.check_stripe_prices(
            config,
            "sk_live_fixture",
            fetcher=lambda *_: (_ for _ in ()).throw(TimeoutError()),
        )
        self.assertEqual(
            {finding.code for finding in findings},
            {
                "stripe_starter_price_unverified",
                "stripe_pro_price_unverified",
                "stripe_business_price_unverified",
            },
        )

    def test_live_stripe_price_ids_must_be_unique(self) -> None:
        production = self.valid_production_config()
        production["vars"]["STRIPE_PRICE_PRO"] = production["vars"]["STRIPE_PRICE_STARTER"]
        config = self.write_config(production)
        findings = self.preflight.check_stripe_prices(
            config,
            "sk_live_fixture",
            fetcher=lambda price_id, _api_key: {
                "id": price_id,
                "object": "price",
                "active": True,
                "livemode": True,
                "currency": "cad",
                "type": "recurring",
                "unit_amount": 2900,
                "recurring": {"interval": "month", "interval_count": 1},
                "product": {"object": "product", "active": True, "livemode": True},
            },
        )
        self.assertIn("stripe_price_ids_not_unique", {finding.code for finding in findings})

    def test_missing_failure_safe_recovery_upload_is_release_blocking(self) -> None:
        repository = self.root / "unsafe-recovery-workflow"
        for relative_path in self.preflight.PHASE5A_ARTIFACTS:
            source = ROOT / relative_path
            target = repository / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

        deploy = repository / ".github/workflows/production-deploy.yml"
        deploy.write_text(
            deploy.read_text(encoding="utf-8").replace(
                "if: ${{ !cancelled() && steps.d1_export.outcome == 'success' }}",
                "if: ${{ success() }}",
            ),
            encoding="utf-8",
        )

        findings = self.preflight.check_phase5a_artifacts(repository)
        self.assertIn(
            "production_deploy_workflow_missing_failure_safe_recovery_upload",
            {finding.code for finding in findings},
        )

    def test_phase5a_artifact_marker_missing_or_unsafe_deploy_stub_fails_closed(self) -> None:
        repository = self.root / "phase5a-fixture"
        (repository / ".github/workflows").mkdir(parents=True)
        (repository / "docs/runbooks").mkdir(parents=True)
        (repository / ".github/workflows/release.yml").write_text(
            """
name: Release
on:
  push:
    tags: ['v*']
  workflow_dispatch:
jobs:
  release-control-plane:
    environment: production
    steps:
      - run: echo deploy --env production
""".strip()
            + "\n",
            encoding="utf-8",
        )
        (repository / "docs/runbooks/production-readiness-preflight.md").write_text(
            "Phase 5A migration status and redacted preflight Worker/console rollback receipt\n",
            encoding="utf-8",
        )
        (repository / "docs/runbooks/production-smoke.md").write_text(
            "read-only, fail-closed post-deploy verifier\ndeployment.json\nNo billing, credential, migration, DNS, deployment, or provider mutation was performed.\n",
            encoding="utf-8",
        )
        findings = self.preflight.check_phase5a_artifacts(repository)
        self.assertIn(
            "production_release_workflow_missing_immutable_tag_gate",
            {finding.code for finding in findings},
        )
        self.assertIn(
            "production_release_workflow_contains_unsafe_production_deploy",
            {finding.code for finding in findings},
        )

    def test_complete_production_configuration_passes_static_checks(self) -> None:
        path = self.write_config(self.valid_production_config())
        self.assertEqual(self.preflight.check_production_config(path), [])

    def test_non_starter_production_checkout_modes_fail_closed(self) -> None:
        for mode in ("closed", "public"):
            with self.subTest(mode=mode):
                production = self.valid_production_config()
                production["vars"]["CHECKOUT_MODE"] = mode
                findings = self.preflight.check_production_config(
                    self.write_config(production)
                )
                self.assertIn(
                    "production_checkout_mode_invalid",
                    {finding.code for finding in findings},
                )

    def test_shaped_resource_placeholders_fail_closed(self) -> None:
        production = self.valid_production_config()
        production["d1_databases"][0]["database_id"] = "00000000-0000-0000-0000-000000000000"
        production["vars"].update(
            {
                "STRIPE_PRICE_STARTER": "price_",
                "STRIPE_PRICE_PRO": "price_REPLACE_ME",
                "STRIPE_PRICE_BUSINESS": "price_fake000000000000",
            }
        )
        findings = self.preflight.check_production_config(self.write_config(production))
        self.assertEqual(
            {finding.code for finding in findings},
            {
                "production_d1_placeholder",
                "production_price_starter_missing",
                "production_price_pro_missing",
                "production_price_business_missing",
            },
        )

    def test_low_entropy_shaped_resources_fail_closed(self) -> None:
        production = self.valid_production_config()
        production["d1_databases"][0]["database_id"] = "01234567-89ab-4def-8123-456789abcdef"
        production["vars"].update(
            {
                "STRIPE_PRICE_STARTER": "price_0123456789ABCDEF0123456789ABCDEF",
                "STRIPE_PRICE_PRO": "price_ABCDEF0123456789ABCDEF0123456789",
                "STRIPE_PRICE_BUSINESS": "price_9876543210FEDCBA9876543210FEDCBA",
            }
        )
        findings = self.preflight.check_production_config(self.write_config(production))
        self.assertEqual(
            {finding.code for finding in findings},
            {
                "production_d1_placeholder",
                "production_price_starter_missing",
                "production_price_pro_missing",
                "production_price_business_missing",
            },
        )

    def test_malformed_configuration_returns_structured_blocker(self) -> None:
        malformed_values = (
            [],
            {"env": "production"},
            {"env": {"production": "invalid"}},
            {"env": {"production": {"vars": [], "routes": "api.agentpulse.ca"}}},
        )
        for value in malformed_values:
            with self.subTest(value=value):
                path = self.root / "malformed.jsonc"
                path.write_text(json.dumps(value), encoding="utf-8")
                findings = self.preflight.check_production_config(path)
                self.assertIn("production_config_invalid", {finding.code for finding in findings})

        production = self.valid_production_config()
        production["d1_databases"].append("MALFORMED")
        production["routes"].append(42)
        findings = self.preflight.check_production_config(self.write_config(production))
        self.assertIn("production_config_invalid", {finding.code for finding in findings})

    def test_jsonc_parser_preserves_https_urls_while_removing_comments(self) -> None:
        path = self.root / "commented.jsonc"
        path.write_text(
            '{\n  // comment\n  "url": "https://api.agentpulse.ca", /* block */\n  "ok": true\n}\n',
            encoding="utf-8",
        )
        self.assertEqual(
            self.preflight.load_jsonc(path),
            {"url": "https://api.agentpulse.ca", "ok": True},
        )

    def test_jsonc_parser_rejects_unterminated_block_comment(self) -> None:
        path = self.root / "unterminated.jsonc"
        path.write_text('{"name":"ok" /* never closes', encoding="utf-8")
        with self.assertRaises(ValueError):
            self.preflight.load_jsonc(path)

    def test_jsonc_parser_rejects_nonstandard_constants_and_duplicate_keys(self) -> None:
        for content in (
            '{"head_sampling_rate": NaN}',
            '{"name": "first", "name": "second"}',
        ):
            with self.subTest(content=content):
                path = self.root / "strict.jsonc"
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.preflight.load_jsonc(path)

    def test_release_ref_requires_version_tag_or_full_commit_sha(self) -> None:
        accepted = ("v1.2.3", "v0.2.0-beta.2", "a" * 40)
        rejected = ("", "master", "main", "c8ee079", "release/latest", "vnext")
        for value in accepted:
            with self.subTest(accepted=value):
                self.assertEqual(self.preflight.check_release_ref(value), [])
        for value in rejected:
            with self.subTest(rejected=value):
                findings = self.preflight.check_release_ref(value)
                self.assertEqual([finding.code for finding in findings], ["release_ref_not_immutable"])

    def test_release_ref_must_resolve_to_the_checked_out_commit(self) -> None:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        parent = subprocess.run(
            ["git", "rev-parse", "HEAD^"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        self.assertEqual(self.preflight.check_release_ref_exists(head, ROOT), [])
        self.assertEqual(
            [finding.code for finding in self.preflight.check_release_ref_exists(parent, ROOT)],
            ["release_ref_not_checkout"],
        )

        findings = self.preflight.check_release_ref_exists("0" * 40, ROOT)
        self.assertEqual([finding.code for finding in findings], ["release_ref_missing"])

    def test_version_shaped_branch_is_not_an_immutable_tag(self) -> None:
        repository = self.root / "tag-check"
        repository.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "--allow-empty", "-m", "init", "-q"],
            cwd=repository,
            check=True,
        )
        subprocess.run(["git", "checkout", "-q", "-b", "v1.2.3"], cwd=repository, check=True)
        findings = self.preflight.check_release_ref_exists("v1.2.3", repository)
        self.assertEqual([finding.code for finding in findings], ["release_ref_not_tag"])

    def test_missing_production_environment_is_a_blocker(self) -> None:
        result = SimpleNamespace(returncode=1, stdout="", stderr="HTTP 404: Not Found")
        findings = self.preflight.check_github_environment(
            "strouddustinn-bot/agentpulse",
            runner=lambda *args, **kwargs: result,
        )
        self.assertEqual([finding.code for finding in findings], ["production_environment_missing"])

    def test_environment_requires_named_reviewers_and_branch_policy(self) -> None:
        payload = {
            "name": "production",
            "protection_rules": [],
            "deployment_branch_policy": None,
        }
        result = SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        findings = self.preflight.check_github_environment(
            "strouddustinn-bot/agentpulse",
            runner=lambda *args, **kwargs: result,
        )
        self.assertEqual(
            {finding.code for finding in findings},
            {"production_environment_reviewers_missing", "production_environment_branch_policy_missing"},
        )

    def test_environment_with_named_reviewer_and_branch_policy_passes(self) -> None:
        payload = {
            "name": "production",
            "protection_rules": [
                {
                    "type": "required_reviewers",
                    "reviewers": [{"type": "User", "reviewer": {"login": "release-owner"}}],
                }
            ],
            "deployment_branch_policy": {
                "protected_branches": True,
                "custom_branch_policies": False,
            },
        }
        result = SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        findings = self.preflight.check_github_environment(
            "strouddustinn-bot/agentpulse",
            release_ref="0" * 40,
            runner=lambda *args, **kwargs: result,
        )
        self.assertEqual(
            [finding.code for finding in findings],
            ["production_environment_release_policy_missing"],
        )
        findings = self.preflight.check_github_environment(
            "strouddustinn-bot/agentpulse",
            release_ref="v0.3.0",
            runner=lambda *args, **kwargs: result,
        )
        self.assertEqual(
            [finding.code for finding in findings],
            ["production_environment_release_policy_missing"],
        )

    def test_empty_reviewer_and_empty_custom_policy_fail_closed(self) -> None:
        environment = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "name": "production",
                    "protection_rules": [
                        {
                            "type": "required_reviewers",
                            "reviewers": [
                                {"reviewer": {"id": 123}},
                                {"type": "Robot", "reviewer": {"name": "not-a-login-or-slug"}},
                            ],
                        }
                    ],
                    "deployment_branch_policy": {
                        "protected_branches": False,
                        "custom_branch_policies": True,
                    },
                }
            ),
            stderr="",
        )
        policies = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"total_count": 0, "branch_policies": []}),
            stderr="",
        )
        results = iter((environment, policies))
        findings = self.preflight.check_github_environment(
            "strouddustinn-bot/agentpulse",
            release_ref="v0.3.0",
            runner=lambda *args, **kwargs: next(results),
        )
        self.assertEqual(
            {finding.code for finding in findings},
            {
                "production_environment_reviewers_unverified",
                "production_environment_branch_policies_empty",
            },
        )

    def test_custom_policy_must_allow_the_exact_immutable_tag(self) -> None:
        environment = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "name": "production",
                    "protection_rules": [
                        {
                            "type": "required_reviewers",
                            "reviewers": [
                                {"type": "User", "reviewer": {"login": "release-owner"}}
                            ],
                        }
                    ],
                    "deployment_branch_policy": {
                        "protected_branches": False,
                        "custom_branch_policies": True,
                    },
                }
            ),
            stderr="",
        )
        mutable_policy = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"total_count": 1, "branch_policies": [{"name": "master", "type": "branch"}]}
            ),
            stderr="",
        )
        exact_tag_policy = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"total_count": 1, "branch_policies": [{"name": "v0.3.0", "type": "tag"}]}
            ),
            stderr="",
        )
        mixed_policy = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "total_count": 2,
                    "branch_policies": [
                        {"name": "v0.3.0", "type": "tag"},
                        "MALFORMED",
                    ],
                }
            ),
            stderr="",
        )
        mutable_results = iter((environment, mutable_policy))
        findings = self.preflight.check_github_environment(
            "strouddustinn-bot/agentpulse",
            release_ref="v0.3.0",
            runner=lambda *args, **kwargs: next(mutable_results),
        )
        self.assertEqual(
            [finding.code for finding in findings],
            ["production_environment_release_policy_missing"],
        )

        exact_results = iter((environment, exact_tag_policy))
        self.assertEqual(
            self.preflight.check_github_environment(
                "strouddustinn-bot/agentpulse",
                release_ref="v0.3.0",
                runner=lambda *args, **kwargs: next(exact_results),
            ),
            [],
        )

        mixed_results = iter((environment, mixed_policy))
        findings = self.preflight.check_github_environment(
            "strouddustinn-bot/agentpulse",
            release_ref="v0.3.0",
            runner=lambda *args, **kwargs: next(mixed_results),
        )
        self.assertEqual(
            [finding.code for finding in findings],
            ["production_environment_branch_policies_unverified"],
        )

    def test_mixed_malformed_github_evidence_fails_closed(self) -> None:
        environment = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "name": "production",
                    "protection_rules": [
                        {
                            "type": "required_reviewers",
                            "reviewers": [
                                {"type": "User", "reviewer": {"login": "release-owner"}},
                                {"type": "Robot", "reviewer": {"name": "invalid"}},
                            ],
                        }
                    ],
                    "deployment_branch_policy": {
                        "protected_branches": False,
                        "custom_branch_policies": True,
                    },
                }
            ),
            stderr="",
        )
        policies = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "total_count": 2,
                    "branch_policies": [{"name": "v0.3.0", "type": "tag"}],
                }
            ),
            stderr="",
        )
        results = iter((environment, policies))
        findings = self.preflight.check_github_environment(
            "strouddustinn-bot/agentpulse",
            release_ref="v0.3.0",
            runner=lambda *args, **kwargs: next(results),
        )
        self.assertEqual(
            {finding.code for finding in findings},
            {
                "production_environment_reviewers_unverified",
                "production_environment_branch_policies_unverified",
            },
        )

        contradictory = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "name": "production",
                    "protection_rules": [
                        {
                            "type": "required_reviewers",
                            "reviewers": [
                                {"type": "User", "reviewer": {"login": "release-owner"}}
                            ],
                        },
                        "MALFORMED",
                    ],
                    "deployment_branch_policy": {
                        "protected_branches": True,
                        "custom_branch_policies": True,
                    },
                }
            ),
            stderr="",
        )
        findings = self.preflight.check_github_environment(
            "strouddustinn-bot/agentpulse",
            release_ref="0" * 40,
            runner=lambda *args, **kwargs: contradictory,
        )
        self.assertEqual(
            {finding.code for finding in findings},
            {
                "production_environment_rules_unverified",
                "production_environment_branch_policy_invalid",
            },
        )

    def test_malformed_or_timed_out_environment_check_fails_closed(self) -> None:
        malformed = SimpleNamespace(returncode=0, stdout="[]", stderr="")
        findings = self.preflight.check_github_environment(
            "strouddustinn-bot/agentpulse",
            release_ref="v0.3.0",
            runner=lambda *args, **kwargs: malformed,
        )
        self.assertEqual([finding.code for finding in findings], ["production_environment_invalid"])

        for payload in (
            '{"name":"staging","protection_rules":[],"deployment_branch_policy":null}',
            '{"name":"production","protection_rules":[],"deployment_branch_policy":null,"ignored":NaN}',
        ):
            with self.subTest(payload=payload):
                malformed = SimpleNamespace(returncode=0, stdout=payload, stderr="")
                findings = self.preflight.check_github_environment(
                    "strouddustinn-bot/agentpulse",
                    release_ref="v0.3.0",
                    runner=lambda *args, **kwargs: malformed,
                )
                self.assertTrue(findings)

        def timeout_runner(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="gh api", timeout=20)

        findings = self.preflight.check_github_environment(
            "strouddustinn-bot/agentpulse",
            release_ref="v0.3.0",
            runner=timeout_runner,
        )
        self.assertEqual([finding.code for finding in findings], ["production_environment_unverified"])

    def test_doh_evidence_requires_integer_fields_and_matching_name(self) -> None:
        malformed = {
            "Status": False,
            "Answer": [{"name": "unrelated.invalid", "type": True, "data": "1.1.1.1"}],
        }
        unrelated = {
            "Status": 0,
            "Answer": [{"name": "unrelated.invalid", "type": 1, "data": "1.1.1.1"}],
        }
        wrong_family = {
            "Status": 0,
            "Answer": [
                {"name": "api.agentpulse.ca.", "type": 28, "data": "2606:4700:4700::1111"}
            ],
        }
        wrong_address_family = {
            "Status": 0,
            "Answer": [
                {"name": "api.agentpulse.ca.", "type": 1, "data": "2606:4700:4700::1111"}
            ],
        }
        valid = {
            "Status": 0,
            "Answer": [
                {"name": "api.agentpulse.ca.", "type": 1, "data": "1.1.1.1"}
            ],
        }
        cname = {
            "Status": 0,
            "Answer": [
                {"name": "api.agentpulse.ca.", "type": 5, "data": "project.pages.dev."},
                {"name": "project.pages.dev.", "type": 1, "data": "1.1.1.1"},
            ],
        }
        malformed_cname = {
            "Status": 0,
            "Answer": [
                {"name": "api.agentpulse.ca.", "type": 5, "data": "bad name."},
                {"name": "bad name.", "type": 1, "data": "1.1.1.1"},
            ],
        }
        mixed = {
            "Status": 0,
            "Answer": [
                {"name": "api.agentpulse.ca.", "type": 1, "data": "1.1.1.1"},
                {"name": "unrelated.invalid.", "type": 1, "data": "8.8.8.8"},
            ],
        }
        mixed_malformed_address = {
            "Status": 0,
            "Answer": [
                {"name": "api.agentpulse.ca.", "type": 1, "data": "1.1.1.1"},
                {"name": "api.agentpulse.ca.", "type": 1, "data": "not-an-ip"},
            ],
        }
        mixed_nonpublic_address = {
            "Status": 0,
            "Answer": [
                {"name": "api.agentpulse.ca.", "type": 1, "data": "1.1.1.1"},
                {"name": "api.agentpulse.ca.", "type": 1, "data": "127.0.0.1"},
            ],
        }
        self.assertEqual(
            self.preflight.extract_public_dns_addresses("api.agentpulse.ca", malformed),
            [],
        )
        self.assertEqual(
            self.preflight.extract_public_dns_addresses("api.agentpulse.ca", unrelated),
            [],
        )
        self.assertEqual(
            self.preflight.extract_public_dns_addresses(
                "api.agentpulse.ca", wrong_family, query_type=1
            ),
            [],
        )
        with self.assertRaises(ValueError):
            self.preflight.extract_public_dns_addresses(
                "api.agentpulse.ca", wrong_address_family, query_type=1, strict=True
            )
        self.assertEqual(
            self.preflight.extract_public_dns_addresses(
                "api.agentpulse.ca", valid, query_type=1
            ),
            ["1.1.1.1"],
        )
        self.assertEqual(
            self.preflight.extract_public_dns_addresses(
                "api.agentpulse.ca", cname, query_type=1
            ),
            ["1.1.1.1"],
        )
        with self.assertRaises(ValueError):
            self.preflight.extract_public_dns_addresses(
                "api.agentpulse.ca", malformed_cname, query_type=1, strict=True
            )
        with self.assertRaises(ValueError):
            self.preflight.extract_public_dns_addresses(
                "api.agentpulse.ca", mixed, query_type=1, strict=True
            )
        with self.assertRaises(ValueError):
            self.preflight.extract_public_dns_addresses(
                "api.agentpulse.ca", mixed_malformed_address, query_type=1, strict=True
            )
        with self.assertRaises(ValueError):
            self.preflight.extract_public_dns_addresses(
                "api.agentpulse.ca", mixed_nonpublic_address, query_type=1, strict=True
            )

    def test_unresolved_or_nonpublic_production_domains_are_blockers(self) -> None:
        def resolver(host: str):
            if host == "api.agentpulse.ca":
                raise OSError("NXDOMAIN")
            return ["127.0.0.1"]

        findings = self.preflight.check_dns(resolver=resolver)
        self.assertEqual(
            {finding.code for finding in findings},
            {
                "dns_app_agentpulse_ca_nonpublic",
                "dns_api_agentpulse_ca_unresolved",
            },
        )

    def test_bootstrap_provider_state_allows_only_unresolved_dns_to_defer(self) -> None:
        allowed, findings = self.preflight.check_bootstrap_provider_state(
            self.write_provider_state()
        )
        self.assertTrue(allowed)
        self.assertEqual(findings, [])

        allowed, findings = self.preflight.check_bootstrap_provider_state(
            self.write_provider_state(
                worker_present=True,
                bootstrap_allowed=True,
            )
        )
        self.assertTrue(allowed)
        self.assertEqual(findings, [])

        allowed, findings = self.preflight.check_bootstrap_provider_state(
            self.write_provider_state(
                production_pages_deployment_present=True,
                bootstrap_allowed=False,
            )
        )
        self.assertFalse(allowed)
        self.assertEqual(findings, [])

        allowed, findings = self.preflight.check_bootstrap_provider_state(
            self.write_provider_state(bootstrap_allowed=False)
        )
        self.assertFalse(allowed)
        self.assertEqual(
            [finding.code for finding in findings],
            ["production_provider_state_inconsistent"],
        )

    def test_bootstrap_provider_state_rejects_wrong_resource_and_extra_fields(self) -> None:
        cases = (
            {"worker_name": "wrong-worker"},
            {"pages_project": "wrong-project"},
            {"unexpected": True},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                allowed, findings = self.preflight.check_bootstrap_provider_state(
                    self.write_provider_state(**overrides)
                )
                self.assertFalse(allowed)
                self.assertEqual(
                    [finding.code for finding in findings],
                    ["production_provider_state_invalid"],
                )

    def test_dns_cannot_be_deferred_after_completed_production_bootstrap(self) -> None:
        unresolved = [
            self.preflight.Finding(
                "dns_api_agentpulse_ca_unresolved",
                "api.agentpulse.ca unresolved",
            )
        ]
        findings, deferred = self.preflight.apply_bootstrap_dns_policy(
            unresolved,
            bootstrap_allowed=False,
        )
        self.assertEqual(findings, unresolved)
        self.assertFalse(deferred)

        findings, deferred = self.preflight.apply_bootstrap_dns_policy(
            unresolved,
            bootstrap_allowed=True,
        )
        self.assertEqual(findings, [])
        self.assertTrue(deferred)

        nonpublic = [
            self.preflight.Finding(
                "dns_api_agentpulse_ca_nonpublic",
                "api.agentpulse.ca nonpublic",
            )
        ]
        findings, deferred = self.preflight.apply_bootstrap_dns_policy(
            nonpublic,
            bootstrap_allowed=True,
        )
        self.assertEqual(findings, nonpublic)
        self.assertFalse(deferred)


if __name__ == "__main__":
    unittest.main()
