"""Tests for the fail-closed Tier 4 production readiness preflight."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "production-preflight.py"


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

    def test_current_placeholder_configuration_fails_closed_with_all_blockers(self) -> None:
        findings = self.preflight.check_production_config(ROOT / "control-plane" / "wrangler.jsonc")
        codes = {finding.code for finding in findings}
        self.assertIn("production_d1_placeholder", codes)
        self.assertIn("production_price_starter_missing", codes)
        self.assertIn("production_price_pro_missing", codes)
        self.assertIn("production_price_business_missing", codes)
        self.assertIn("production_api_route_missing", codes)

    def test_phase5a_artifacts_pass_static_checks(self) -> None:
        self.assertEqual(self.preflight.check_phase5a_artifacts(ROOT), [])

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


if __name__ == "__main__":
    unittest.main()
