#!/usr/bin/env python3
"""Fail-closed, read-only preflight for AgentPulse production deployment.

This command performs no provider mutation. It validates repository production
intent, an immutable release reference, GitHub production-environment controls,
and public DNS. Passing it is necessary but not sufficient to authorize or
execute a production deployment.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib
from pathlib import Path
from typing import Callable, NamedTuple, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "control-plane" / "wrangler.jsonc"
DEFAULT_REPOSITORY = "strouddustinn-bot/agentpulse"
PRODUCTION_HOSTS = ("app.agentpulse.ca", "api.agentpulse.ca")
TAG_REF_PATTERN = r"v\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)(?:\.?\d+)?)?"
PRICE_VARS = {
    "STARTER": "production_price_starter_missing",
    "PRO": "production_price_pro_missing",
    "BUSINESS": "production_price_business_missing",
}
EXPECTED_STRIPE_PRICES = {
    "STARTER": 2900,
    "PRO": 9900,
    "BUSINESS": 29900,
}
EXPECTED_PROVIDER_STATE_KEYS = {
    "schema_version",
    "worker_name",
    "worker_present",
    "pages_project",
    "production_pages_deployment_present",
    "bootstrap_allowed",
}
PHASE5A_ARTIFACTS = {
    ".github/workflows/production-deploy.yml": (
        "production_deploy_workflow_unreadable",
        (
            (
                "production_deploy_workflow_missing_full_secret_gate",
                "--only-verified --exclude-detectors=Lob",
            ),
            (
                "production_deploy_workflow_missing_agent_gate",
                "python agent/tools/run_tests.py",
            ),
            (
                "production_deploy_workflow_missing_contract_gate",
                "python scripts/validate-contracts.py",
            ),
            (
                "production_deploy_workflow_missing_packaging_gate",
                "python -m unittest tests.test_packaging -v",
            ),
            (
                "production_deploy_workflow_missing_dependency_gate",
                "npm audit --audit-level=high",
            ),
            (
                "production_deploy_workflow_missing_export_identity",
                "id: d1_export",
            ),
            (
                "production_deploy_workflow_missing_failure_safe_recovery_upload",
                "if: ${{ !cancelled() && steps.d1_export.outcome == 'success' }}",
            ),
            (
                "production_deploy_workflow_missing_disposable_d1_restore",
                "d1_disposable_restore=pass",
            ),
            (
                "production_deploy_workflow_missing_saved_version_rehearsal",
                "wrangler versions deploy",
            ),
            (
                "production_deploy_workflow_missing_live_stripe_gate",
                "stripe_live_prices=verified",
            ),
            (
                "production_deploy_workflow_missing_provider_state_capture",
                "python scripts/capture-production-provider-state.py",
            ),
            (
                "production_deploy_workflow_missing_bootstrap_state_binding",
                '--bootstrap-provider-state "$RUNNER_TEMP/provider-state.json"',
            ),
            (
                "production_deploy_workflow_missing_bounded_smoke_retry",
                "--attempts 12",
            ),
        ),
    ),
    ".github/workflows/release.yml": (
        "production_release_workflow_unreadable",
        (
            ("production_release_workflow_missing_tag_trigger", "tags: ['v*']"),
            ("production_release_workflow_missing_dispatch", "workflow_dispatch:"),
            (
                "production_release_workflow_missing_immutable_tag_gate",
                "github.ref_type == 'tag'",
            ),
            (
                "production_release_workflow_missing_release_identity",
                'RELEASE_REF="$GITHUB_REF_NAME"',
            ),
            (
                "production_release_workflow_missing_phase5a_verifiers",
                "tests.test_production_preflight",
            ),
        ),
    ),
    "docs/runbooks/production-readiness-preflight.md": (
        "production_preflight_runbook_unreadable",
        (
            ("production_preflight_runbook_missing_phase5a", "Phase 5A"),
            ("production_preflight_runbook_missing_migration_sequence", "migration status and redacted preflight"),
            ("production_preflight_runbook_missing_rollback_sequence", "Worker/console rollback receipt"),
        ),
    ),
    "docs/runbooks/production-smoke.md": (
        "production_smoke_runbook_unreadable",
        (
            ("production_smoke_runbook_missing_verifier_boundary", "read-only, fail-closed post-deploy verifier"),
            ("production_smoke_runbook_missing_manifest_contract", "deployment.json"),
            ("production_smoke_runbook_missing_failure_boundary", "No billing, credential, migration, DNS, deployment, or provider mutation was performed."),
        ),
    ),
}

PHASE5A_FORBIDDEN_MARKERS = {
    ".github/workflows/release.yml": (
        "deploy_control_plane",
        "release-control-plane",
        "wrangler-action",
        "environment: production",
        "deploy --env production",
    ),
}


class Finding(NamedTuple):
    code: str
    message: str


class StripeAPIError(RuntimeError):
    """A sanitized Stripe API failure category."""

    def __init__(self, category: str):
        super().__init__(category)
        self.category = category


def strip_jsonc_comments(text: str) -> str:
    """Remove JSONC comments without corrupting comment-like text in strings."""
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue

        if char == "/" and next_char == "/":
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue

        if char == "/" and next_char == "*":
            index += 2
            closed = False
            while index + 1 < len(text):
                if text[index : index + 2] == "*/":
                    closed = True
                    index += 2
                    break
                output.append("\n" if text[index] == "\n" else " ")
                index += 1
            if not closed:
                raise ValueError("unterminated JSONC block comment")
            continue

        output.append(char)
        index += 1

    return "".join(output)


def strict_json_loads(text: str) -> object:
    def reject_constant(value: str) -> object:
        raise ValueError(f"non-standard JSON constant is not allowed: {value}")

    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object key is not allowed: {key}")
            result[key] = value
        return result

    return json.loads(
        text,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicate_keys,
    )


def load_jsonc(path: Path) -> object:
    return strict_json_loads(strip_jsonc_comments(path.read_text(encoding="utf-8")))


def _invalid_config(message: str) -> Finding:
    return Finding("production_config_invalid", message)


def _plausibly_unpatterned(value: str, *, min_unique: int = 10) -> bool:
    encoded = value.encode("utf-8")
    return len(set(value)) >= min_unique and len(zlib.compress(encoded)) >= len(encoded)


def _valid_uuid(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = uuid.UUID(value)
        return (
            parsed.int != 0
            and str(parsed) == value.lower()
            and _plausibly_unpatterned(parsed.hex)
        )
    except ValueError:
        return False


def check_production_config(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        config = load_jsonc(path)
    except (OSError, ValueError) as exc:
        return [Finding("production_config_unreadable", f"cannot parse {path}: {exc}")]
    if not isinstance(config, dict):
        return [_invalid_config("wrangler config root must be an object")]

    environments = config.get("env")
    if not isinstance(environments, dict):
        return [_invalid_config("wrangler env must be an object")]
    production = environments.get("production")
    if production is None:
        return [
            Finding(
                "production_environment_config_missing",
                "wrangler production environment is absent",
            )
        ]
    if not isinstance(production, dict):
        return [_invalid_config("wrangler production environment must be an object")]

    if production.get("name") != "agentpulse-control-plane-production":
        findings.append(
            Finding(
                "production_worker_name_invalid",
                "production Worker name must be agentpulse-control-plane-production",
            )
        )

    databases = production.get("d1_databases")
    if not isinstance(databases, list):
        findings.append(_invalid_config("production d1_databases must be an array"))
        databases = []
    elif any(not isinstance(item, dict) for item in databases):
        findings.append(_invalid_config("production d1_databases entries must be objects"))
    database = next(
        (
            item
            for item in databases
            if isinstance(item, dict) and item.get("binding") == "DB"
        ),
        None,
    )
    database_id = database.get("database_id") if database else None
    if not _valid_uuid(database_id) or "REPLACE" in str(database_id).upper():
        findings.append(
            Finding(
                "production_d1_placeholder",
                "production DB binding must contain a structurally valid non-placeholder D1 UUID",
            )
        )

    variables = production.get("vars")
    if not isinstance(variables, dict):
        findings.append(_invalid_config("production vars must be an object"))
        variables = {}
    expected_variables = {
        "ENVIRONMENT": "production",
        "PUBLIC_BASE_URL": "https://api.agentpulse.ca",
        "APP_BASE_URL": "https://app.agentpulse.ca",
        "CHECKOUT_MODE": "closed",
        "STRIPE_PORTAL_URL": "https://billing.stripe.com/p/login/6oU28rbSBgPS8Qa5CB7N600",
    }
    for name, expected in expected_variables.items():
        if variables.get(name) != expected:
            findings.append(
                Finding(
                    f"production_{name.lower()}_invalid",
                    f"{name} must be {expected}",
                )
            )

    version = variables.get("AGENTPULSE_VERSION")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:[a-zA-Z]+\d+)?", version):
        findings.append(
            Finding(
                "production_version_invalid",
                "AGENTPULSE_VERSION must be an explicit package version",
            )
        )

    for tier, code in PRICE_VARS.items():
        value = variables.get(f"STRIPE_PRICE_{tier}")
        plausible_id = (
            isinstance(value, str)
            and re.fullmatch(r"price_[A-Za-z0-9]{16,}", value)
            and _plausibly_unpatterned(value.removeprefix("price_"))
        )
        shaped_placeholder = isinstance(value, str) and re.search(
            r"fake|test|replace|placeholder|example|dummy",
            value,
            re.IGNORECASE,
        )
        if not plausible_id or shaped_placeholder:
            findings.append(
                Finding(code, f"STRIPE_PRICE_{tier} must be a non-placeholder external Price ID")
            )

    routes = production.get("routes")
    if not isinstance(routes, list):
        findings.append(_invalid_config("production routes must be an array"))
        routes = []
    elif any(not isinstance(route, dict) for route in routes):
        findings.append(_invalid_config("production route entries must be objects"))
    api_route_present = any(
        isinstance(route, dict)
        and route.get("pattern") == "api.agentpulse.ca"
        and route.get("custom_domain") is True
        for route in routes
    )
    if not api_route_present:
        findings.append(
            Finding(
                "production_api_route_missing",
                "production must declare api.agentpulse.ca as a custom domain",
            )
        )

    return findings


def _fetch_stripe_price(price_id: str, api_key: str) -> object:
    query = urllib.parse.urlencode({"expand[]": "product"})
    request = urllib.request.Request(
        f"https://api.stripe.com/v1/prices/{urllib.parse.quote(price_id, safe='')}?{query}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "AgentPulse-production-preflight/1",
        },
    )
    try:
        response = urllib.request.urlopen(request, timeout=15)
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
        categories = {
            401: "authentication",
            403: "permission",
            404: "missing",
            429: "rate_limited",
        }
        raise StripeAPIError(categories.get(status, "unavailable")) from exc
    with response:
        return strict_json_loads(response.read().decode("utf-8"))


def check_stripe_prices(
    path: Path,
    api_key: str,
    *,
    fetcher: Callable[[str, str], object] = _fetch_stripe_price,
) -> list[Finding]:
    """Read and verify the exact live recurring Prices configured for production."""
    if not api_key:
        return [
            Finding(
                "stripe_api_key_missing",
                "STRIPE_API_KEY is required for live production Price verification",
            )
        ]

    try:
        config = load_jsonc(path)
        production = config["env"]["production"]
        variables = production["vars"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [
            Finding(
                "stripe_price_config_unreadable",
                f"production Stripe Price configuration could not be read: {exc}",
            )
        ]

    findings: list[Finding] = []
    seen_ids: set[str] = set()
    for tier, expected_amount in EXPECTED_STRIPE_PRICES.items():
        price_id = variables.get(f"STRIPE_PRICE_{tier}")
        if not isinstance(price_id, str) or not price_id:
            findings.append(
                Finding(
                    f"stripe_{tier.lower()}_price_unverified",
                    f"production {tier.title()} Price ID is missing",
                )
            )
            continue
        if price_id in seen_ids:
            findings.append(
                Finding(
                    "stripe_price_ids_not_unique",
                    "production tiers must use distinct Stripe Price IDs",
                )
            )
            continue
        seen_ids.add(price_id)

        try:
            payload = fetcher(price_id, api_key)
        except StripeAPIError as exc:
            if exc.category == "missing":
                findings.append(
                    Finding(
                        f"stripe_{tier.lower()}_price_missing",
                        f"Stripe could not find the configured production {tier.title()} Price in the authenticated account",
                    )
                )
                continue
            code_and_message = {
                "authentication": (
                    "stripe_api_authentication_failed",
                    "Stripe rejected the production API key",
                ),
                "permission": (
                    "stripe_api_permission_denied",
                    "Stripe key permissions do not allow read-only Price verification",
                ),
                "rate_limited": (
                    "stripe_api_rate_limited",
                    "Stripe rate-limited production Price verification",
                ),
                "unavailable": (
                    "stripe_api_unavailable",
                    "Stripe returned an unavailable response during production Price verification",
                ),
            }
            code, message = code_and_message.get(
                exc.category,
                code_and_message["unavailable"],
            )
            findings.append(Finding(code, message))
            break
        except (
            OSError,
            TimeoutError,
            ValueError,
            json.JSONDecodeError,
            urllib.error.URLError,
        ):
            findings.append(
                Finding(
                    f"stripe_{tier.lower()}_price_unverified",
                    f"Stripe did not return usable evidence for the production {tier.title()} Price",
                )
            )
            continue

        recurring = payload.get("recurring") if isinstance(payload, dict) else None
        product = payload.get("product") if isinstance(payload, dict) else None
        valid = (
            isinstance(payload, dict)
            and payload.get("id") == price_id
            and payload.get("object") == "price"
            and payload.get("active") is True
            and payload.get("livemode") is True
            and payload.get("currency") == "cad"
            and payload.get("type") == "recurring"
            and payload.get("unit_amount") == expected_amount
            and isinstance(recurring, dict)
            and recurring.get("interval") == "month"
            and recurring.get("interval_count") == 1
            and isinstance(product, dict)
            and product.get("object") == "product"
            and product.get("active") is True
            and product.get("livemode") is True
        )
        if not valid:
            findings.append(
                Finding(
                    f"stripe_{tier.lower()}_price_mismatch",
                    f"production {tier.title()} must be an active live CAD monthly Price for {expected_amount} cents on an active live Product",
                )
            )

    return findings


def check_phase5a_artifacts(repository_root: Path = ROOT) -> list[Finding]:
    findings: list[Finding] = []
    for relative_path, (unreadable_code, markers) in PHASE5A_ARTIFACTS.items():
        path = repository_root / relative_path
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(Finding(unreadable_code, f"cannot read {path}: {exc}"))
            continue
        for code, marker in markers:
            if marker not in text:
                findings.append(Finding(code, f"{path.name} must contain {marker!r}"))
        for marker in PHASE5A_FORBIDDEN_MARKERS.get(relative_path, ()):
            if marker in text:
                findings.append(
                    Finding(
                        "production_release_workflow_contains_unsafe_production_deploy",
                        f"{path.name} must not contain production mutation marker {marker!r} before Owner Gate 5",
                    )
                )
    return findings


def check_release_ref(release_ref: str) -> list[Finding]:
    sha_pattern = r"[0-9a-fA-F]{40}"
    if re.fullmatch(TAG_REF_PATTERN, release_ref) or re.fullmatch(sha_pattern, release_ref):
        return []
    return [
        Finding(
            "release_ref_not_immutable",
            "release ref must be a version tag or full 40-character commit SHA",
        )
    ]


def check_release_ref_exists(release_ref: str, repository_root: Path = ROOT) -> list[Finding]:
    if re.fullmatch(TAG_REF_PATTERN, release_ref):
        try:
            tag_result = subprocess.run(
                ["git", "show-ref", "--verify", "--quiet", f"refs/tags/{release_ref}"],
                cwd=repository_root,
                text=True,
                capture_output=True,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            tag_result = None
        if tag_result is None or tag_result.returncode != 0:
            return [
                Finding(
                    "release_ref_not_tag",
                    "version-shaped release ref must exist under refs/tags",
                )
            ]

    def resolve(ref: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
                cwd=repository_root,
                text=True,
                capture_output=True,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    resolved_ref = resolve(release_ref)
    if resolved_ref is None:
        return [
            Finding(
                "release_ref_missing",
                "immutable release ref does not resolve to a commit in this checkout",
            )
        ]
    checked_out_commit = resolve("HEAD")
    if checked_out_commit is None:
        return [
            Finding(
                "release_ref_unverified",
                "checked-out commit could not be resolved",
            )
        ]
    if resolved_ref != checked_out_commit:
        return [
            Finding(
                "release_ref_not_checkout",
                "immutable release ref must resolve to the checked-out commit",
            )
        ]
    return []


def check_github_environment(
    repository: str,
    *,
    release_ref: str = "",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> list[Finding]:
    command = ["gh", "api", f"repos/{repository}/environments/production"]
    try:
        result = runner(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [
            Finding(
                "production_environment_unverified",
                f"GitHub production environment could not be checked: {exc}",
            )
        ]

    if result.returncode != 0:
        if "404" in result.stderr or "Not Found" in result.stderr:
            return [
                Finding(
                    "production_environment_missing",
                    "GitHub production environment does not exist",
                )
            ]
        return [
            Finding(
                "production_environment_unverified",
                "GitHub production environment check failed without usable evidence",
            )
        ]

    try:
        payload = strict_json_loads(result.stdout)
    except ValueError:
        return [
            Finding(
                "production_environment_unverified",
                "GitHub production environment returned invalid JSON",
            )
        ]
    if not isinstance(payload, dict):
        return [
            Finding(
                "production_environment_invalid",
                "GitHub production environment response must be an object",
            )
        ]
    if payload.get("name") != "production":
        return [
            Finding(
                "production_environment_invalid",
                "GitHub environment response identity must be production",
            )
        ]

    findings: list[Finding] = []
    rules = payload.get("protection_rules")
    if not isinstance(rules, list):
        return [
            Finding(
                "production_environment_invalid",
                "GitHub production protection_rules must be an array",
            )
        ]
    if any(not isinstance(rule, dict) for rule in rules):
        findings.append(
            Finding(
                "production_environment_rules_unverified",
                "GitHub production protection rules contained malformed entries",
            )
        )
    reviewer_rule = next(
        (
            rule
            for rule in rules
            if isinstance(rule, dict) and rule.get("type") == "required_reviewers"
        ),
        None,
    )
    reviewers = reviewer_rule.get("reviewers", []) if reviewer_rule else []

    def reviewer_is_valid(item: object) -> bool:
        if not isinstance(item, dict) or not isinstance(item.get("reviewer"), dict):
            return False
        reviewer = item["reviewer"]
        if item.get("type") == "User":
            return isinstance(reviewer.get("login"), str) and bool(reviewer["login"].strip())
        if item.get("type") == "Team":
            return isinstance(reviewer.get("slug"), str) and bool(reviewer["slug"].strip())
        return False

    if not isinstance(reviewers, list):
        findings.append(
            Finding(
                "production_environment_reviewers_unverified",
                "production environment reviewers returned malformed evidence",
            )
        )
    elif not reviewers:
        findings.append(
            Finding(
                "production_environment_reviewers_missing",
                "production environment must require at least one named reviewer",
            )
        )
    elif not all(reviewer_is_valid(item) for item in reviewers):
        findings.append(
            Finding(
                "production_environment_reviewers_unverified",
                "production environment reviewers contained malformed identities",
            )
        )

    policy = payload.get("deployment_branch_policy")
    protected_branches = isinstance(policy, dict) and policy.get("protected_branches") is True
    custom_branch_policies = isinstance(policy, dict) and policy.get("custom_branch_policies") is True
    if protected_branches and custom_branch_policies:
        findings.append(
            Finding(
                "production_environment_branch_policy_invalid",
                "production environment cannot enable protected and custom branch policies together",
            )
        )
        return findings
    release_is_tag = bool(re.fullmatch(TAG_REF_PATTERN, release_ref))
    if protected_branches and not release_is_tag:
        findings.append(
            Finding(
                "production_environment_release_policy_missing",
                "protected-branch mode does not bind the environment to the exact immutable release ref",
            )
        )
        return findings
    if not custom_branch_policies:
        findings.append(
            Finding(
                "production_environment_release_policy_missing"
                if release_is_tag
                else "production_environment_branch_policy_missing",
                "production environment must allow the exact immutable release tag"
                if release_is_tag
                else "production environment must restrict deployable branches or tags",
            )
        )
        return findings

    policies_command = [
        "gh",
        "api",
        f"repos/{repository}/environments/production/deployment-branch-policies?per_page=100",
    ]
    try:
        policies_result = runner(
            policies_command,
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        policies_result = None
    if policies_result is None or policies_result.returncode != 0:
        findings.append(
            Finding(
                "production_environment_branch_policies_unverified",
                "custom production deployment policies could not be verified",
            )
        )
        return findings
    try:
        policies_payload = strict_json_loads(policies_result.stdout)
    except ValueError:
        policies_payload = None
    if not isinstance(policies_payload, dict):
        findings.append(
            Finding(
                "production_environment_branch_policies_unverified",
                "custom production deployment policies returned malformed evidence",
            )
        )
        return findings
    total_count = policies_payload.get("total_count")
    branch_policies = policies_payload.get("branch_policies")
    if not isinstance(total_count, int) or isinstance(total_count, bool) or not isinstance(branch_policies, list):
        findings.append(
            Finding(
                "production_environment_branch_policies_unverified",
                "custom production deployment policies returned malformed evidence",
            )
        )
        return findings
    if total_count != len(branch_policies):
        findings.append(
            Finding(
                "production_environment_branch_policies_unverified",
                "custom production deployment policy count did not match returned entries",
            )
        )
        return findings
    if total_count < 1 or not branch_policies:
        findings.append(
            Finding(
                "production_environment_branch_policies_empty",
                "custom production deployment policy is enabled but has no allowed branch or tag",
            )
        )
        return findings
    malformed_policy = any(
        not isinstance(policy_item, dict)
        or policy_item.get("type") not in ("branch", "tag")
        or not isinstance(policy_item.get("name"), str)
        or not policy_item["name"].strip()
        for policy_item in branch_policies
    )
    if malformed_policy:
        findings.append(
            Finding(
                "production_environment_branch_policies_unverified",
                "custom production deployment policies contained malformed entries",
            )
        )
        return findings
    exact_tag_allowed = release_is_tag and any(
        policy_item["type"] == "tag" and policy_item["name"] == release_ref
        for policy_item in branch_policies
    )
    if not exact_tag_allowed:
        findings.append(
            Finding(
                "production_environment_release_policy_missing",
                "custom production policy must allow the exact immutable release tag",
            )
        )

    return findings


def _finding_code_for_host(host: str, suffix: str) -> str:
    safe = re.sub(r"[^a-z0-9]+", "_", host.lower()).strip("_")
    return f"dns_{safe}_{suffix}"


def _valid_dns_name(value: str) -> bool:
    normalized = value.rstrip(".")
    if not normalized or len(normalized) > 253:
        return False
    labels = normalized.split(".")
    return all(
        len(label) <= 63
        and bool(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label))
        for label in labels
    )


def extract_public_dns_addresses(
    host: str,
    payload: object,
    *,
    query_type: int = 1,
    strict: bool = False,
) -> list[str]:
    def invalid() -> list[str]:
        if strict:
            raise ValueError("malformed or unrelated DNS-over-HTTPS evidence")
        return []

    if query_type not in (1, 28) or not isinstance(payload, dict):
        return invalid()
    status = payload.get("Status")
    if not isinstance(status, int) or isinstance(status, bool):
        return invalid()
    if status != 0:
        return []
    answers = payload.get("Answer")
    if not isinstance(answers, list):
        return invalid()

    records: list[tuple[str, int, str]] = []
    for answer in answers:
        if not isinstance(answer, dict):
            return invalid()
        record_type = answer.get("type")
        record_name = answer.get("name")
        record_data = answer.get("data")
        if (
            not isinstance(record_type, int)
            or isinstance(record_type, bool)
            or record_type not in (5, query_type)
            or not isinstance(record_name, str)
            or not record_name.strip()
            or not _valid_dns_name(record_name)
            or not isinstance(record_data, str)
            or not record_data.strip()
        ):
            return invalid()
        normalized_data = record_data.rstrip(".").lower()
        if record_type == query_type:
            try:
                parsed_address = ipaddress.ip_address(normalized_data)
            except ValueError:
                return invalid()
            expected_version = 4 if query_type == 1 else 6
            if parsed_address.version != expected_version or not parsed_address.is_global:
                return invalid()
            normalized_data = str(parsed_address)
        elif not _valid_dns_name(normalized_data):
            return invalid()
        records.append(
            (
                record_name.rstrip(".").lower(),
                record_type,
                normalized_data,
            )
        )

    if not records:
        return []
    current_name = host.rstrip(".").lower()
    visited: set[str] = set()
    for _ in range(len(records) + 1):
        if current_name in visited:
            return invalid()
        visited.add(current_name)
        addresses = [
            data
            for name, record_type, data in records
            if name == current_name and record_type == query_type
        ]
        cname_targets = [
            data
            for name, record_type, data in records
            if name == current_name and record_type == 5
        ]
        if addresses:
            if cname_targets or any(name not in visited for name, _, _ in records):
                return invalid()
            return addresses
        if len(cname_targets) != 1:
            return invalid()
        current_name = cname_targets[0]
    return invalid()


def _query_public_dns(host: str) -> list[str]:
    addresses: list[str] = []
    for query_name, query_type in (("A", 1), ("AAAA", 28)):
        query = urllib.parse.urlencode({"name": host, "type": query_name})
        request = urllib.request.Request(
            f"https://cloudflare-dns.com/dns-query?{query}",
            headers={
                "Accept": "application/dns-json",
                "User-Agent": "AgentPulse-production-preflight/1",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = strict_json_loads(response.read().decode("utf-8"))
        addresses.extend(
            extract_public_dns_addresses(
                host, payload, query_type=query_type, strict=True
            )
        )
    return addresses


def check_dns(
    hosts: Sequence[str] = PRODUCTION_HOSTS,
    *,
    resolver: Callable[[str], Sequence[str]] = _query_public_dns,
) -> list[Finding]:
    findings: list[Finding] = []
    for host in hosts:
        try:
            addresses = list(resolver(host))
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError, urllib.error.URLError):
            addresses = []
        if not addresses:
            findings.append(
                Finding(
                    _finding_code_for_host(host, "unresolved"),
                    f"{host} does not resolve through the public DNS-over-HTTPS resolver",
                )
            )
            continue
        global_addresses = []
        for address in addresses:
            try:
                if ipaddress.ip_address(address).is_global:
                    global_addresses.append(address)
            except ValueError:
                continue
        if not global_addresses:
            findings.append(
                Finding(
                    _finding_code_for_host(host, "nonpublic"),
                    f"{host} resolves only to non-public or malformed addresses",
                )
            )
    return findings


def check_bootstrap_provider_state(path: Path | None) -> tuple[bool, list[Finding]]:
    """Validate provider evidence and return whether first-deploy DNS may defer."""
    if path is None:
        return False, []
    try:
        payload = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, [
            Finding(
                "production_provider_state_unreadable",
                f"bootstrap provider evidence could not be read: {exc}",
            )
        ]
    valid_shape = (
        isinstance(payload, dict)
        and set(payload) == EXPECTED_PROVIDER_STATE_KEYS
        and payload.get("schema_version") == 1
        and payload.get("worker_name") == "agentpulse-control-plane-production"
        and type(payload.get("worker_present")) is bool
        and payload.get("pages_project") == "agentpulse-production-app"
        and type(payload.get("production_pages_deployment_present")) is bool
        and type(payload.get("bootstrap_allowed")) is bool
    )
    if not valid_shape:
        return False, [
            Finding(
                "production_provider_state_invalid",
                "bootstrap provider evidence has an unexpected schema or resource identity",
            )
        ]
    computed_allowed = (
        payload["worker_present"] is False
        and payload["production_pages_deployment_present"] is False
    )
    if payload["bootstrap_allowed"] is not computed_allowed:
        return False, [
            Finding(
                "production_provider_state_inconsistent",
                "bootstrap provider evidence does not match the recorded resource state",
            )
        ]
    return computed_allowed, []


def apply_bootstrap_dns_policy(
    dns_findings: Sequence[Finding],
    *,
    bootstrap_allowed: bool,
) -> tuple[list[Finding], bool]:
    """Defer only unresolved DNS backed by empty first-deploy provider state."""
    findings = list(dns_findings)
    if (
        bootstrap_allowed
        and findings
        and all(finding.code.endswith("_unresolved") for finding in findings)
    ):
        return [], True
    return findings, False


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--release-ref", default=os.environ.get("AP_PRODUCTION_RELEASE_REF", ""))
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPOSITORY))
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="validate source intent and immutable ref only; never counts as live readiness",
    )
    parser.add_argument(
        "--bootstrap-provider-state",
        type=Path,
        help="redacted Cloudflare state captured immediately before a protected deployment",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    findings = check_production_config(args.config)
    release_ref_findings = check_release_ref(args.release_ref)
    findings.extend(release_ref_findings)
    if not release_ref_findings:
        findings.extend(check_release_ref_exists(args.release_ref))
    findings.extend(check_phase5a_artifacts())
    dns_deferred = False
    if args.static_only:
        live_status = "SKIPPED_NON_GATING"
    else:
        findings.extend(
            check_github_environment(args.repository, release_ref=args.release_ref)
        )
        bootstrap_allowed, provider_findings = check_bootstrap_provider_state(
            args.bootstrap_provider_state
        )
        findings.extend(provider_findings)
        gated_dns_findings, dns_deferred = apply_bootstrap_dns_policy(
            check_dns(),
            bootstrap_allowed=bootstrap_allowed,
        )
        findings.extend(gated_dns_findings)
        findings.extend(
            check_stripe_prices(
                args.config,
                os.environ.get("STRIPE_API_KEY", ""),
            )
        )
        live_status = "CHECKED"

    if findings:
        print("PRODUCTION_PREFLIGHT=BLOCKED")
        print(f"LIVE_CHECKS={live_status}")
        for finding in findings:
            print(f"[BLOCK] {finding.code}: {finding.message}")
        return 1

    print("PRODUCTION_PREFLIGHT=PASS")
    print(f"LIVE_CHECKS={live_status}")
    if not args.static_only:
        print("stripe_live_prices=verified")
        print(
            "dns_predeploy=deferred_first_deploy"
            if dns_deferred
            else "dns_predeploy=verified"
        )
    print("No deployment, migration, DNS, billing, or secret mutation was performed.")
    if args.static_only:
        print("Static-only PASS is not production readiness or deployment authorization.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
