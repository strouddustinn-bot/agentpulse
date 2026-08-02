from __future__ import annotations

import importlib.util
import hashlib
import unittest
import urllib.request
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "production-smoke.py"


def load_module():
    spec = importlib.util.spec_from_file_location("production_smoke", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load production smoke module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProductionSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.smoke = load_module()
        self.app = "https://app.agentpulse.ca"
        self.api = "https://api.agentpulse.ca"
        self.version = "0.3.0"
        self.source_sha = "a" * 40
        self.shell = (
            '<!doctype html><html><head><title>AgentPulse Dashboard</title>'
            '<script type="module" src="/assets/index-good.js"></script>'
            '<link rel="stylesheet" href="/assets/index-good.css"></head>'
            '<body><div id="root"></div></body></html>'
        ).encode()
        self.asset = b'const Be="https://api.agentpulse.ca".replace(/\\/+$/,"");'

    def response(self, status: int, body: bytes, *, content_type: str, url: str, headers=None):
        values = {"content-type": content_type}
        values.update({key.lower(): value for key, value in (headers or {}).items()})
        return self.smoke.HttpResponse(
            status=status,
            headers=tuple(values.items()),
            body=body,
            final_url=url,
        )

    def cors(self) -> dict[str, str]:
        return {
            "access-control-allow-origin": self.app,
            "access-control-allow-credentials": "true",
            "vary": "Origin",
        }

    def good_requester(self) -> Callable:
        health = b'{"ok":true,"service":"agentpulse-control-plane","version":"0.3.0","environment":"production"}'
        account = b'{"error":{"code":"unauthorized","message":"Browser session is required"}}'
        manifest = (
            b'{"service":"agentpulse-dashboard","environment":"production",'
            b'"version":"0.3.0","source_sha":"' + self.source_sha.encode() + b'",'
            b'"api_base_url":"https://api.agentpulse.ca","main_js_sha256":"'
            + hashlib.sha256(self.asset).hexdigest().encode()
            + b'"}'
        )

        def request(url: str, headers: dict[str, str]):
            self.assertEqual(headers.get("Cache-Control"), "no-cache")
            self.assertEqual(headers.get("Pragma"), "no-cache")
            if url in {self.app + "/", self.app + "/account"}:
                return self.response(200, self.shell, content_type="text/html; charset=utf-8", url=url)
            if url == self.app + "/deployment.json":
                return self.response(200, manifest, content_type="application/json", url=url)
            if url == self.app + "/assets/index-good.js":
                return self.response(200, self.asset, content_type="application/javascript", url=url)
            if url == self.api + "/health" and headers.get("Origin") == self.app:
                return self.response(200, health, content_type="application/json", url=url, headers=self.cors())
            if url == self.api + "/health" and headers.get("Origin") != self.app:
                return self.response(200, health, content_type="application/json", url=url)
            if url == self.api + "/v1/account" and headers.get("Origin") == self.app:
                return self.response(401, account, content_type="application/json", url=url, headers=self.cors())
            if url == self.api + "/v1/account" and headers.get("Origin") != self.app:
                return self.response(401, account, content_type="application/json", url=url)
            raise AssertionError(f"unexpected request: {url} {headers}")

        return request

    def check_map(self, request=None):
        checks = self.smoke.run_smoke(
            app_base_url=self.app,
            api_base_url=self.api,
            expected_version=self.version,
            expected_source_sha=self.source_sha,
            requester=request or self.good_requester(),
        )
        return {check.code: check for check in checks}

    def test_script_is_executable(self) -> None:
        self.assertTrue(MODULE_PATH.is_file())
        self.assertTrue(MODULE_PATH.stat().st_mode & 0o111, "production smoke command must be executable")

    def test_complete_contract_passes(self) -> None:
        checks = self.check_map()
        self.assertTrue(checks)
        self.assertTrue(all(check.passed for check in checks.values()), checks)
        self.assertIn("console_api_base", checks)
        self.assertIn("console_deployment_identity", checks)
        self.assertIn("api_health_identity", checks)
        self.assertIn("api_trusted_cors", checks)
        self.assertIn("api_untrusted_cors_absent", checks)
        self.assertIn("api_disallowed_origins_absent", checks)
        self.assertIn("api_session_required", checks)

    def test_non_https_or_non_origin_inputs_fail_before_network(self) -> None:
        called = False

        def requester(url: str, headers: dict[str, str]):
            nonlocal called
            called = True
            raise AssertionError("network must not run")

        cases = (
            ("http://app.agentpulse.ca", self.api),
            (self.app + "/console", self.api),
            ("https://user@app.agentpulse.ca", self.api),
            (self.app, "https://api.agentpulse.ca/base"),
        )
        for app, api in cases:
            with self.subTest(app=app, api=api):
                checks = self.smoke.run_smoke(app, api, self.version, self.source_sha, requester)
                self.assertEqual([check.code for check in checks], ["input_invalid"])
                self.assertFalse(checks[0].passed)
        self.assertFalse(called)

    def test_release_identifiers_must_be_immutable(self) -> None:
        def requester(url: str, headers: dict[str, str]):
            raise AssertionError("network must not run")

        cases = (
            ("master", self.source_sha),
            ("0.3", self.source_sha),
            (self.version, "main"),
            (self.version, "a" * 39),
        )
        for version, source_sha in cases:
            with self.subTest(version=version, source_sha=source_sha):
                checks = self.smoke.run_smoke(
                    self.app,
                    self.api,
                    version,
                    source_sha,
                    requester,
                )
                self.assertEqual([check.code for check in checks], ["input_invalid"])
        self.assertEqual(self.smoke._validate_version("0.2.0b2"), "0.2.0b2")
        with self.assertRaises(ValueError):
            self.smoke._validate_version("0.3.0-alpha")

    def test_default_http_client_refuses_redirects(self) -> None:
        handler = self.smoke.NoRedirectHandler()
        request = urllib.request.Request(self.app + "/")
        redirected = handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {"Location": "https://redirect.invalid/"},
            "https://redirect.invalid/",
        )
        self.assertIsNone(redirected)

    def test_placeholder_or_missing_built_assets_blocks_shell(self) -> None:
        requester = self.good_requester()
        bad_shell = b'<title>AgentPulse Dashboard</title><div id="root"></div>placeholder'

        def bad(url: str, headers: dict[str, str]):
            if url == self.app + "/":
                return self.response(200, bad_shell, content_type="text/html", url=url)
            return requester(url, headers)

        checks = self.check_map(bad)
        self.assertFalse(checks["console_root_shell"].passed)
        self.assertFalse(checks["console_api_base"].passed)

        def wrong_media(url: str, headers: dict[str, str]):
            if url == self.app + "/":
                return self.response(200, self.shell, content_type="text/html-evil", url=url)
            return requester(url, headers)

        media_checks = self.check_map(wrong_media)
        self.assertFalse(media_checks["console_root_shell"].passed)

    def test_staging_or_local_api_base_in_console_asset_blocks(self) -> None:
        requester = self.good_requester()

        def bad(url: str, headers: dict[str, str]):
            if url == self.app + "/assets/index-good.js":
                body = b'https://staging-api.agentpulse.ca http://localhost:8787'
                return self.response(200, body, content_type="text/javascript", url=url)
            return requester(url, headers)

        checks = self.check_map(bad)
        self.assertFalse(checks["console_api_base"].passed)

    def test_console_asset_requires_javascript_and_selected_production_api(self) -> None:
        requester = self.good_requester()

        def bad(url: str, headers: dict[str, str]):
            if url == self.app + "/assets/index-good.js":
                body = (
                    b'const Dead="https://api.agentpulse.ca".replace(/\\/+$/,"");'
                    b'let API_BASE_URL;API_BASE_URL="http://127.0.0.1:8787";'
                    b'globalThis["API_BASE_URL"]="https://off-origin.invalid";'
                    b'fetch(API_BASE_URL+"/health");'
                )
                return self.response(200, body, content_type="application/javascript", url=url)
            return requester(url, headers)

        checks = self.check_map(bad)
        self.assertFalse(checks["console_api_base"].passed)

    def test_console_manifest_binds_release_source_and_api(self) -> None:
        requester = self.good_requester()
        stale = (
            b'{"service":"agentpulse-dashboard","environment":"production",'
            b'"version":"0.2.0","source_sha":"' + (b"b" * 40) + b'",'
            b'"api_base_url":"https://staging-api.agentpulse.ca",'
            b'"main_js_sha256":"' + (b"c" * 64) + b'"}'
        )

        def bad(url: str, headers: dict[str, str]):
            if url == self.app + "/deployment.json":
                return self.response(200, stale, content_type="application/json", url=url)
            return requester(url, headers)

        checks = self.check_map(bad)
        self.assertFalse(checks["console_deployment_identity"].passed)

    def test_console_manifest_rejects_non_identity_fields(self) -> None:
        requester = self.good_requester()
        manifest = (
            b'{"service":"agentpulse-dashboard","environment":"production",'
            b'"version":"0.3.0","source_sha":"' + self.source_sha.encode() + b'",'
            b'"api_base_url":"https://api.agentpulse.ca","main_js_sha256":"'
            + hashlib.sha256(self.asset).hexdigest().encode()
            + b'","token":"PUBLIC_SECRET","account_id":"acct_customer"}'
        )

        def bad(url: str, headers: dict[str, str]):
            if url == self.app + "/deployment.json":
                return self.response(200, manifest, content_type="application/json", url=url)
            return requester(url, headers)

        checks = self.check_map(bad)
        self.assertFalse(checks["console_deployment_identity"].passed)

    def test_json_must_be_strict_and_use_exact_media_type(self) -> None:
        requester = self.good_requester()
        malformed = (
            b'{"ok":false,"ok":true,"service":"agentpulse-control-plane",'
            b'"version":"0.3.0","environment":"production","value":NaN}'
        )

        def bad(url: str, headers: dict[str, str]):
            if url == self.api + "/health":
                return self.response(
                    200,
                    malformed,
                    content_type="application/jsonp",
                    url=url,
                    headers=self.cors() if headers.get("Origin") == self.app else {},
                )
            return requester(url, headers)

        checks = self.check_map(bad)
        self.assertFalse(checks["api_health_identity"].passed)
        self.assertFalse(checks["api_disallowed_origins_absent"].passed)

    def test_health_identity_and_cors_are_fail_closed(self) -> None:
        requester = self.good_requester()
        wrong = b'{"ok":true,"service":"agentpulse-control-plane","version":"0.2.0","environment":"staging"}'

        def bad(url: str, headers: dict[str, str]):
            if url == self.api + "/health" and headers.get("Origin") == self.app:
                headers_out = self.cors() | {"access-control-allow-origin": "https://evil.invalid"}
                return self.response(200, wrong, content_type="application/json", url=url, headers=headers_out)
            if url == self.api + "/health" and headers.get("Origin") == "https://untrusted.invalid":
                return self.response(
                    200,
                    wrong,
                    content_type="application/json",
                    url=url,
                    headers={"access-control-allow-origin": "*"},
                )
            return requester(url, headers)

        checks = self.check_map(bad)
        self.assertFalse(checks["api_health_identity"].passed)
        self.assertFalse(checks["api_trusted_cors"].passed)
        self.assertFalse(checks["api_untrusted_cors_absent"].passed)

    def test_duplicate_cors_headers_fail_closed(self) -> None:
        requester = self.good_requester()

        def bad(url: str, headers: dict[str, str]):
            response = requester(url, headers)
            if url == self.api + "/health" and headers.get("Origin") == self.app:
                return response._replace(
                    headers=(
                        ("content-type", "application/json"),
                        ("access-control-allow-origin", "https://evil.invalid"),
                        ("access-control-allow-origin", self.app),
                        ("access-control-allow-credentials", "true"),
                        ("vary", "Origin"),
                    )
                )
            return response

        checks = self.check_map(bad)
        self.assertFalse(checks["api_trusted_cors"].passed)

    def test_duplicate_untrusted_cors_headers_are_not_absent(self) -> None:
        requester = self.good_requester()

        def bad(url: str, headers: dict[str, str]):
            response = requester(url, headers)
            if headers.get("Origin") == "https://untrusted.invalid":
                return response._replace(
                    headers=(
                        ("content-type", "application/json"),
                        ("access-control-allow-origin", "https://evil.invalid"),
                        ("access-control-allow-origin", "https://other.invalid"),
                        ("access-control-allow-credentials", "true"),
                        ("access-control-allow-credentials", "false"),
                    )
                )
            return response

        checks = self.check_map(bad)
        self.assertFalse(checks["api_disallowed_origins_absent"].passed)

    def test_known_nonproduction_origins_are_probed(self) -> None:
        requester = self.good_requester()
        seen: set[str] = set()

        def bad(url: str, headers: dict[str, str]):
            origin = headers.get("Origin", "")
            seen.add(origin)
            response = requester(url, headers)
            if origin in {"https://staging-app.agentpulse.ca", "http://localhost:5173"}:
                return response._replace(
                    headers=(
                        ("content-type", "application/json"),
                        ("access-control-allow-origin", origin),
                        ("access-control-allow-credentials", "true"),
                    )
                )
            return response

        checks = self.check_map(bad)
        self.assertFalse(checks["api_disallowed_origins_absent"].passed)
        self.assertTrue(
            {"https://staging-app.agentpulse.ca", "http://localhost:5173"} <= seen
        )

    def test_authenticated_account_or_wrong_error_shape_blocks(self) -> None:
        requester = self.good_requester()

        def bad(url: str, headers: dict[str, str]):
            if url == self.api + "/v1/account":
                return self.response(200, b'{"plan":"starter"}', content_type="application/json", url=url, headers=self.cors())
            return requester(url, headers)

        checks = self.check_map(bad)
        self.assertFalse(checks["api_session_required"].passed)

    def test_untrusted_account_origin_never_receives_cors(self) -> None:
        requester = self.good_requester()

        def bad(url: str, headers: dict[str, str]):
            if url == self.api + "/v1/account" and headers.get("Origin") == "https://untrusted.invalid":
                account = b'{"error":{"code":"unauthorized"}}'
                return self.response(
                    401,
                    account,
                    content_type="application/json",
                    url=url,
                    headers={"access-control-allow-origin": "*"},
                )
            return requester(url, headers)

        checks = self.check_map(bad)
        self.assertFalse(checks["api_untrusted_account_cors_absent"].passed)

    def test_api_redirects_away_from_expected_urls_block(self) -> None:
        requester = self.good_requester()

        def redirected(url: str, headers: dict[str, str]):
            response = requester(url, headers)
            if url == self.api + "/health":
                return response._replace(final_url="https://redirect.invalid/health")
            return response

        checks = self.check_map(redirected)
        self.assertFalse(checks["api_health_identity"].passed)
        self.assertFalse(checks["api_untrusted_cors_absent"].passed)

    def test_transport_failure_is_structured_and_does_not_reuse_a_prior_body(self) -> None:
        requester = self.good_requester()

        def flaky(url: str, headers: dict[str, str]):
            if url == self.app + "/account":
                raise self.smoke.ProbeError("dns failure")
            return requester(url, headers)

        checks = self.check_map(flaky)
        self.assertFalse(checks["console_account_transport"].passed)
        self.assertFalse(checks["console_account_shell"].passed)
        self.assertNotIn("stale", checks["console_account_shell"].detail.lower())


if __name__ == "__main__":
    unittest.main()
