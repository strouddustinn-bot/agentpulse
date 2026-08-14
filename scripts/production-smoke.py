#!/usr/bin/env python3
"""Read-only, fail-closed smoke checks for an AgentPulse production deployment.

The checker performs bounded unauthenticated GET requests only. It does not call
billing or mutation routes, use credentials, or modify provider resources.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import NamedTuple

DEFAULT_APP_URL = "https://app.agentpulse.ca"
DEFAULT_API_URL = "https://api.agentpulse.ca"
UNTRUSTED_ORIGIN = "https://untrusted.invalid"
KNOWN_NONPRODUCTION_ORIGINS = (
    "https://staging-app.agentpulse.ca",
    "http://localhost:5173",
)
MAX_BODY_BYTES = 2 * 1024 * 1024
USER_AGENT = "AgentPulse-production-smoke/1"
VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+(?:[a-zA-Z]+\d+)?")
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")


class ProbeError(RuntimeError):
    """A bounded transport or response-size failure."""


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Return redirect responses to the checker instead of following them."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class HttpResponse(NamedTuple):
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    final_url: str


class Check(NamedTuple):
    code: str
    passed: bool
    detail: str


Requester = Callable[[str, dict[str, str]], HttpResponse]


def _origin_url(value: str, label: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{label} must be an absolute HTTPS origin")
    if parsed.port not in (None, 443):
        raise ValueError(f"{label} must use the default HTTPS port")
    return f"https://{parsed.hostname.lower()}"


def _validate_version(value: str) -> str:
    if VERSION_PATTERN.fullmatch(value) is None:
        raise ValueError("expected_version must be an exact semantic release version")
    return value


def _validate_source_sha(value: str) -> str:
    normalized = value.lower()
    if SHA_PATTERN.fullmatch(normalized) is None:
        raise ValueError("expected_source_sha must be a full 40-character commit SHA")
    return normalized


def _header(response: HttpResponse, name: str) -> str:
    values = _header_values(response, name)
    return values[0] if len(values) == 1 else ""


def _header_values(response: HttpResponse, name: str) -> list[str]:
    return [value for key, value in response.headers if key == name.lower()]


def _same_url(actual: str, expected: str) -> bool:
    try:
        actual_parts = urllib.parse.urlsplit(actual)
        expected_parts = urllib.parse.urlsplit(expected)
    except ValueError:
        return False
    return (
        actual_parts.scheme == expected_parts.scheme == "https"
        and actual_parts.hostname == expected_parts.hostname
        and actual_parts.port in (None, 443)
        and expected_parts.port in (None, 443)
        and actual_parts.path == expected_parts.path
        and actual_parts.query == expected_parts.query
        and actual_parts.fragment == expected_parts.fragment
        and actual_parts.username is None
        and actual_parts.password is None
    )


def _json_object(response: HttpResponse) -> dict[str, object] | None:
    media_type = _header(response, "content-type").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        return None

    def strict_object(pairs):  # noqa: ANN001
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    def reject_constant(value: str):
        raise ValueError(f"non-standard JSON constant: {value}")

    try:
        value = json.loads(
            response.body.decode("utf-8"),
            object_pairs_hook=strict_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _cors_passes(response: HttpResponse, expected_origin: str) -> bool:
    vary = {item.strip().lower() for item in _header(response, "vary").split(",")}
    return (
        _header(response, "access-control-allow-origin") == expected_origin
        and _header(response, "access-control-allow-credentials").lower() == "true"
        and "origin" in vary
    )


def _cors_absent(response: HttpResponse) -> bool:
    return (
        not _header_values(response, "access-control-allow-origin")
        and not _header_values(response, "access-control-allow-credentials")
    )


def _health_identity_passes(
    response: HttpResponse,
    expected_url: str,
    expected_version: str,
) -> bool:
    payload = _json_object(response)
    return (
        response.status == 200
        and _same_url(response.final_url, expected_url)
        and payload is not None
        and payload.get("ok") is True
        and payload.get("service") == "agentpulse-control-plane"
        and payload.get("environment") == "production"
        and payload.get("version") == expected_version
    )


def _account_denial_passes(response: HttpResponse, expected_url: str) -> bool:
    payload = _json_object(response)
    error = payload.get("error") if payload is not None else None
    return (
        response.status == 401
        and _same_url(response.final_url, expected_url)
        and isinstance(error, dict)
        and error.get("code") == "unauthorized"
    )


def _request_with_urllib(timeout: float) -> Requester:
    context = ssl.create_default_context()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        NoRedirectHandler(),
    )

    def request(url: str, headers: dict[str, str]) -> HttpResponse:
        request_headers = {"Accept": "*/*", "User-Agent": USER_AGENT, **headers}
        req = urllib.request.Request(url, headers=request_headers, method="GET")
        try:
            response = opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProbeError(f"transport failed: {type(exc).__name__}") from exc
        try:
            body = response.read(MAX_BODY_BYTES + 1)
            if len(body) > MAX_BODY_BYTES:
                raise ProbeError("response exceeded the 2 MiB safety limit")
            response_headers = tuple(
                (key.lower(), value) for key, value in response.headers.items()
            )
            status = response.getcode()
            if not isinstance(status, int):
                raise ProbeError("response did not include an HTTP status")
            return HttpResponse(
                status=status,
                headers=response_headers,
                body=body,
                final_url=response.geturl(),
            )
        finally:
            response.close()

    return request


def _console_shell_check(response: HttpResponse, expected_url: str) -> tuple[bool, str, str | None]:
    if response.status != 200:
        return False, f"expected HTTP 200, got {response.status}", None
    if not _same_url(response.final_url, expected_url):
        return False, "response redirected away from the expected HTTPS URL", None
    media_type = _header(response, "content-type").split(";", 1)[0].strip().lower()
    if media_type != "text/html":
        return False, "response is not HTML", None
    try:
        text = response.body.decode("utf-8")
    except UnicodeDecodeError:
        return False, "response body is not UTF-8", None
    script_matches = re.findall(r"<script\b[^>]*\bsrc=[\"']([^\"']+)[\"']", text, flags=re.IGNORECASE)
    style_matches = re.findall(r"<link\b[^>]*\bhref=[\"']([^\"']+\.css(?:\?[^\"']*)?)[\"']", text, flags=re.IGNORECASE)
    required = {
        "dashboard title": "<title>AgentPulse Dashboard</title>" in text,
        "root element": bool(re.search(r"\bid=[\"']root[\"']", text)),
        "built JavaScript asset": any(re.search(r"/assets/index-[^/]+\.js(?:\?|$)", item) for item in script_matches),
        "built CSS asset": any(re.search(r"/assets/index-[^/]+\.css(?:\?|$)", item) for item in style_matches),
        "placeholder absent": "placeholder" not in text.lower(),
    }
    failed = [name for name, passed in required.items() if not passed]
    if failed:
        return False, "missing or unsafe shell markers: " + ", ".join(failed), None
    main_script = next(
        item for item in script_matches if re.search(r"/assets/index-[^/]+\.js(?:\?|$)", item)
    )
    return True, "real built console shell served", main_script


def _probe(requester: Requester, url: str, headers: dict[str, str]) -> tuple[HttpResponse | None, str | None]:
    try:
        request_headers = {
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            **headers,
        }
        return requester(url, request_headers), None
    except ProbeError as exc:
        return None, str(exc)
    except Exception as exc:  # Provider/client errors must block, never crash the gate.
        return None, f"requester failed: {type(exc).__name__}"


def run_smoke(
    app_base_url: str,
    api_base_url: str,
    expected_version: str,
    expected_source_sha: str,
    requester: Requester,
) -> list[Check]:
    """Run read-only production checks and return every PASS/BLOCK result."""

    try:
        app = _origin_url(app_base_url, "app_base_url")
        api = _origin_url(api_base_url, "api_base_url")
        version = _validate_version(expected_version)
        source_sha = _validate_source_sha(expected_source_sha)
    except ValueError as exc:
        return [Check("input_invalid", False, str(exc))]
    if app == api:
        return [Check("input_invalid", False, "app and API origins must be distinct")]

    checks: list[Check] = []
    root_url = app + "/"
    account_page_url = app + "/account"

    root, root_error = _probe(requester, root_url, {})
    checks.append(Check("console_root_transport", root is not None, root_error or "response received"))
    root_script: str | None = None
    if root is None:
        checks.append(Check("console_root_shell", False, "shell was not parsed after transport failure"))
    else:
        passed, detail, root_script = _console_shell_check(root, root_url)
        checks.append(Check("console_root_shell", passed, detail))

    account_page, account_error = _probe(requester, account_page_url, {})
    checks.append(Check("console_account_transport", account_page is not None, account_error or "response received"))
    if account_page is None:
        checks.append(Check("console_account_shell", False, "shell was not parsed after transport failure"))
    else:
        passed, detail, _ = _console_shell_check(account_page, account_page_url)
        checks.append(Check("console_account_shell", passed, detail))

    manifest_url = app + "/deployment.json"
    manifest_asset_sha: str | None = None
    manifest, manifest_error = _probe(
        requester,
        manifest_url,
        {"Accept": "application/json"},
    )
    checks.append(
        Check(
            "console_deployment_transport",
            manifest is not None,
            manifest_error or "response received",
        )
    )
    if manifest is None:
        checks.append(
            Check(
                "console_deployment_identity",
                False,
                "deployment manifest unavailable",
            )
        )
    else:
        manifest_payload = _json_object(manifest)
        expected_manifest_keys = {
            "service",
            "environment",
            "version",
            "source_sha",
            "api_base_url",
            "main_js_sha256",
        }
        manifest_hash = (
            manifest_payload.get("main_js_sha256")
            if manifest_payload is not None
            else None
        )
        manifest_passed = (
            manifest.status == 200
            and _same_url(manifest.final_url, manifest_url)
            and manifest_payload is not None
            and set(manifest_payload) == expected_manifest_keys
            and manifest_payload.get("service") == "agentpulse-dashboard"
            and manifest_payload.get("environment") == "production"
            and manifest_payload.get("version") == version
            and manifest_payload.get("source_sha") == source_sha
            and manifest_payload.get("api_base_url") == api
            and isinstance(manifest_hash, str)
            and re.fullmatch(r"[0-9a-f]{64}", manifest_hash) is not None
        )
        if manifest_passed and isinstance(manifest_hash, str):
            manifest_asset_sha = manifest_hash
        checks.append(
            Check(
                "console_deployment_identity",
                manifest_passed,
                "console manifest matches the exact identity-only schema"
                if manifest_passed
                else "console manifest schema, release, source, asset, or API identity mismatched",
            )
        )

    if root_script is None:
        checks.append(Check("console_api_base", False, "main console asset was not identified"))
        checks.append(Check("console_asset_integrity", False, "main console asset was not identified"))
    else:
        asset_url = urllib.parse.urljoin(root_url, root_script)
        asset_parts = urllib.parse.urlsplit(asset_url)
        if f"{asset_parts.scheme}://{asset_parts.hostname}" != app or asset_parts.port not in (None, 443):
            checks.append(Check("console_api_base", False, "main console asset is not same-origin HTTPS"))
            checks.append(Check("console_asset_integrity", False, "main console asset is not same-origin HTTPS"))
        else:
            asset, asset_error = _probe(requester, asset_url, {})
            if asset is None:
                checks.append(Check("console_api_base", False, asset_error or "asset transport failed"))
                checks.append(Check("console_asset_integrity", False, asset_error or "asset transport failed"))
            elif asset.status != 200 or not _same_url(asset.final_url, asset_url):
                checks.append(Check("console_api_base", False, "main console asset was not served directly with HTTP 200"))
                checks.append(Check("console_asset_integrity", False, "main console asset was not served directly with HTTP 200"))
            else:
                media_type = _header(asset, "content-type").split(";", 1)[0].strip().lower()
                try:
                    asset_text = asset.body.decode("utf-8")
                except UnicodeDecodeError:
                    asset_text = ""
                selected_api_origins = {
                    match[1]
                    for match in re.findall(
                        r"=\s*([\"'])(https?://[^\"'\\\s]+)\1\.replace\(",
                        asset_text,
                    )
                }
                assigned_origins = {
                    match[1]
                    for match in re.findall(
                        r"=\s*([\"'])(https?://[^\"'\\\s]+)\1",
                        asset_text,
                    )
                }
                allowed_assigned_origins = {
                    api,
                    "http://localhost",
                    "http://www.w3.org/2000/svg",
                    "https://react.dev/errors/",
                }
                passed = (
                    media_type in {"application/javascript", "text/javascript"}
                    and selected_api_origins == {api}
                    and assigned_origins <= allowed_assigned_origins
                )
                detail = (
                    "JavaScript bundle binds the production API without unknown URL assignments"
                    if passed
                    else "bundle media type or selected API origin mismatched"
                )
                checks.append(Check("console_api_base", passed, detail))
                asset_digest = hashlib.sha256(asset.body).hexdigest()
                integrity_passed = (
                    manifest_asset_sha is not None
                    and asset_digest == manifest_asset_sha
                )
                checks.append(
                    Check(
                        "console_asset_integrity",
                        integrity_passed,
                        "main JavaScript matches the deployment manifest SHA-256"
                        if integrity_passed
                        else "main JavaScript SHA-256 does not match the deployment manifest",
                    )
                )

    health_url = api + "/health"
    health, health_error = _probe(requester, health_url, {"Origin": app, "Accept": "application/json"})
    checks.append(Check("api_health_transport", health is not None, health_error or "response received"))
    if health is None:
        checks.append(Check("api_health_identity", False, "health response unavailable"))
        checks.append(Check("api_trusted_cors", False, "health response unavailable"))
    else:
        payload = _json_object(health)
        identity_passed = (
            health.status == 200
            and _same_url(health.final_url, health_url)
            and payload is not None
            and payload.get("ok") is True
            and payload.get("service") == "agentpulse-control-plane"
            and payload.get("environment") == "production"
            and payload.get("version") == version
        )
        checks.append(
            Check(
                "api_health_identity",
                identity_passed,
                "production health identity matches expected release" if identity_passed else "health status, JSON identity, environment, or version mismatched",
            )
        )
        cors_passed = _cors_passes(health, app)
        checks.append(Check("api_trusted_cors", cors_passed, "trusted console CORS is credentialed" if cors_passed else "trusted console CORS headers mismatched"))

    untrusted_health_passed = False
    untrusted, untrusted_error = _probe(
        requester,
        health_url,
        {"Origin": UNTRUSTED_ORIGIN, "Accept": "application/json"},
    )
    if untrusted is None:
        checks.append(Check("api_untrusted_cors_absent", False, untrusted_error or "untrusted-origin probe failed"))
    else:
        untrusted_health_passed = (
            _health_identity_passes(untrusted, health_url, version)
            and _cors_absent(untrusted)
        )
        checks.append(
            Check(
                "api_untrusted_cors_absent",
                untrusted_health_passed,
                "untrusted origin received valid health without a CORS grant"
                if untrusted_health_passed
                else "untrusted health response was malformed, redirected, or received CORS headers",
            )
        )

    account_url = api + "/v1/account"
    account, account_error = _probe(requester, account_url, {"Origin": app, "Accept": "application/json"})
    checks.append(Check("api_account_transport", account is not None, account_error or "response received"))
    if account is None:
        checks.append(Check("api_session_required", False, "account response unavailable"))
        checks.append(Check("api_account_cors", False, "account response unavailable"))
    else:
        payload = _json_object(account)
        error = payload.get("error") if payload is not None else None
        passed = (
            account.status == 401
            and _same_url(account.final_url, account_url)
            and isinstance(error, dict)
            and error.get("code") == "unauthorized"
        )
        checks.append(Check("api_session_required", passed, "unauthenticated account access fails closed" if passed else "account route did not return the expected unauthorized JSON boundary"))
        cors_passed = _cors_passes(account, app)
        checks.append(Check("api_account_cors", cors_passed, "account error preserves trusted credentialed CORS" if cors_passed else "account error CORS headers mismatched"))

    untrusted_account_passed = False
    untrusted_account, untrusted_account_error = _probe(
        requester,
        account_url,
        {"Origin": UNTRUSTED_ORIGIN, "Accept": "application/json"},
    )
    if untrusted_account is None:
        checks.append(
            Check(
                "api_untrusted_account_cors_absent",
                False,
                untrusted_account_error or "untrusted account-origin probe failed",
            )
        )
    else:
        untrusted_account_passed = (
            _account_denial_passes(untrusted_account, account_url)
            and _cors_absent(untrusted_account)
        )
        checks.append(
            Check(
                "api_untrusted_account_cors_absent",
                untrusted_account_passed,
                "untrusted account origin received no CORS grant"
                if untrusted_account_passed
                else "untrusted account origin received a grant, redirect, or wrong auth boundary",
            )
        )

    known_nonproduction_passed = True
    for origin in KNOWN_NONPRODUCTION_ORIGINS:
        known_health, _ = _probe(
            requester,
            health_url,
            {"Origin": origin, "Accept": "application/json"},
        )
        known_account, _ = _probe(
            requester,
            account_url,
            {"Origin": origin, "Accept": "application/json"},
        )
        origin_passed = (
            known_health is not None
            and _health_identity_passes(known_health, health_url, version)
            and _cors_absent(known_health)
            and known_account is not None
            and _account_denial_passes(known_account, account_url)
            and _cors_absent(known_account)
        )
        known_nonproduction_passed = known_nonproduction_passed and origin_passed

    all_disallowed_passed = (
        untrusted_health_passed
        and untrusted_account_passed
        and known_nonproduction_passed
    )
    checks.append(
        Check(
            "api_disallowed_origins_absent",
            all_disallowed_passed,
            "fixed untrusted, staging, and local origins received no CORS grants"
            if all_disallowed_passed
            else "a disallowed-origin response was malformed, redirected, or received CORS headers",
        )
    )

    return checks


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-version", required=True, help="exact AGENTPULSE_VERSION expected from /health")
    parser.add_argument(
        "--expected-source-sha",
        required=True,
        help="full 40-character source commit expected from the console deployment manifest",
    )
    parser.add_argument("--app-url", default=DEFAULT_APP_URL, help="production console HTTPS origin")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="production API HTTPS origin")
    parser.add_argument("--timeout", type=float, default=20.0, help="per-request timeout in seconds (default: 20)")
    parser.add_argument(
        "--attempts",
        type=int,
        default=1,
        help="bounded complete smoke attempts (default: 1, maximum: 30)",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=10.0,
        help="seconds between attempts (default: 10, maximum: 60)",
    )
    return parser.parse_args(argv)


def run_smoke_with_retries(
    *,
    app_base_url: str,
    api_base_url: str,
    expected_version: str,
    expected_source_sha: str,
    requester: Requester,
    attempts: int,
    retry_delay: float,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[list[Check], int]:
    """Retry the complete gate; never convert a partial pass into success."""
    final_checks: list[Check] = []
    for attempt in range(1, attempts + 1):
        final_checks = run_smoke(
            app_base_url=app_base_url,
            api_base_url=api_base_url,
            expected_version=expected_version,
            expected_source_sha=expected_source_sha,
            requester=requester,
        )
        if final_checks and all(check.passed for check in final_checks):
            return final_checks, attempt
        if attempt < attempts:
            sleeper(retry_delay)
    return final_checks, attempts


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if not (0 < args.timeout <= 60):
        print("PRODUCTION_SMOKE=BLOCKED")
        print("[BLOCK] input_invalid: timeout must be greater than 0 and at most 60 seconds")
        return 1
    if not (1 <= args.attempts <= 30):
        print("PRODUCTION_SMOKE=BLOCKED")
        print("[BLOCK] input_invalid: attempts must be between 1 and 30")
        return 1
    if not (0 <= args.retry_delay <= 60):
        print("PRODUCTION_SMOKE=BLOCKED")
        print("[BLOCK] input_invalid: retry delay must be between 0 and 60 seconds")
        return 1
    checks, attempts_used = run_smoke_with_retries(
        app_base_url=args.app_url,
        api_base_url=args.api_url,
        expected_version=args.expected_version,
        expected_source_sha=args.expected_source_sha,
        requester=_request_with_urllib(args.timeout),
        attempts=args.attempts,
        retry_delay=args.retry_delay,
    )
    passed = bool(checks) and all(check.passed for check in checks)
    print(f"PRODUCTION_SMOKE={'PASS' if passed else 'BLOCKED'}")
    print(f"ATTEMPTS_USED={attempts_used}")
    for check in checks:
        label = "PASS" if check.passed else "BLOCK"
        print(f"[{label}] {check.code}: {check.detail}")
    print("No billing, credential, migration, DNS, deployment, or provider mutation was performed.")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
