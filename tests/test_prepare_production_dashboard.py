from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY / "scripts" / "prepare-production-dashboard.py"
RUNBOOK = REPOSITORY / "docs" / "runbooks" / "production-deploy-rollback.md"
PREFLIGHT_RUNBOOK = REPOSITORY / "docs" / "runbooks" / "production-readiness-preflight.md"
SMOKE_RUNBOOK = REPOSITORY / "docs" / "runbooks" / "production-smoke.md"
WORKFLOW = REPOSITORY / ".github" / "workflows" / "production-readiness.yml"
RELEASE_WORKFLOW = REPOSITORY / ".github" / "workflows" / "release.yml"
VERSION = "0.3.0"
SOURCE_SHA = "0123456789abcdef0123456789abcdef01234567"


class PrepareProductionDashboardTests(unittest.TestCase):
    def make_dist(
        self,
        root: Path,
        *,
        javascript: str = 'const e="https://api.agentpulse.ca".replace(/\\/$/,"");',
        html: str | None = None,
    ) -> tuple[Path, bytes]:
        dist = root / "dist"
        assets = dist / "assets"
        assets.mkdir(parents=True)
        bundle = javascript.encode("utf-8")
        (assets / "index-AbCd1234.js").write_bytes(bundle)
        (assets / "index-AbCd1234.css").write_text("body{}", encoding="utf-8")
        (dist / "index.html").write_text(
            html
            or """<!doctype html>
<html><head>
<title>AgentPulse Dashboard</title>
<link rel="stylesheet" href="/assets/index-AbCd1234.css">
</head><body><div id="root"></div>
<script type="module" src="/assets/index-AbCd1234.js"></script>
</body></html>
""",
            encoding="utf-8",
        )
        return dist, bundle

    def run_script(self, dist: Path, *, version: str = "0.3.0", source_sha: str = SOURCE_SHA):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--dist",
                str(dist),
                "--version",
                version,
                "--source-sha",
                source_sha,
            ],
            cwd=REPOSITORY,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_complete_build_creates_exact_identity_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            dist, bundle = self.make_dist(Path(directory))
            result = self.run_script(dist)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PRODUCTION_DASHBOARD_ARTIFACT=PASS", result.stdout)
            manifest = json.loads((dist / "deployment.json").read_text(encoding="utf-8"))
            self.assertEqual(
                manifest,
                {
                    "service": "agentpulse-dashboard",
                    "environment": "production",
                    "version": "0.3.0",
                    "source_sha": SOURCE_SHA,
                    "api_base_url": "https://api.agentpulse.ca",
                    "main_js_sha256": hashlib.sha256(bundle).hexdigest(),
                },
            )
            self.assertEqual((dist / "deployment.json").stat().st_mode & 0o777, 0o644)

    def test_release_version_must_be_exact_semantic_version(self):
        for version in ("latest", "1.2.3garbage9", "1.2", "v1.2.3"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                dist, _ = self.make_dist(Path(directory))
                result = self.run_script(dist, version=version)

                self.assertEqual(result.returncode, 1)
                self.assertIn("PRODUCTION_DASHBOARD_ARTIFACT=BLOCKED", result.stdout)
                self.assertFalse((dist / "deployment.json").exists())

    def test_source_sha_must_be_full_lowercase_commit(self):
        for source_sha in ("c8ee079", SOURCE_SHA.upper(), "g" * 40):
            with self.subTest(source_sha=source_sha), tempfile.TemporaryDirectory() as directory:
                dist, _ = self.make_dist(Path(directory))
                result = self.run_script(dist, source_sha=source_sha)

                self.assertEqual(result.returncode, 1)
                self.assertIn("PRODUCTION_DASHBOARD_ARTIFACT=BLOCKED", result.stdout)
                self.assertFalse((dist / "deployment.json").exists())

    def test_staging_or_unknown_assigned_api_origin_blocks(self):
        for javascript in (
            'const e="https://staging-api.agentpulse.ca".replace(/\\/$/,"");',
            'const e="https://api.agentpulse.ca".replace(/\\/$/,"");const x="https://evil.invalid";',
            'const dead="https://api.agentpulse.ca".replace(/\\/+$/,"");'
            'const API_BASE_URL="https://"+"staging-api.agentpulse.ca";'
            'fetch(API_BASE_URL+"/health");',
            'const dead="https://api.agentpulse.ca".replace(/\\/+$/,"");'
            'const API_BASE_URL="http://localhost:8787";fetch(API_BASE_URL+"/health");',
            'const dead="https://api.agentpulse.ca".replace(/\\/+$/,"");'
            'const endpoint="http://localhost:8787";fetch(endpoint+"/health");',
            'const dead="https://api.agentpulse.ca".replace(/\\/+$/,"");'
            'fetch("http://localhost:8787/health");',
            'const dead="https://api.agentpulse.ca".replace(/\\/+$/,"");'
            'fetch("https://evil.invalid/health");',
            'const dead="https://api.agentpulse.ca".replace(/\\/+$/,"");'
            'new URL("/health","https://evil.invalid");',
            'const dead="https://api.agentpulse.ca".replace(/\\/+$/,"");'
            'fetch(`https://evil.invalid/health`);',
            'const dead="https://api.agentpulse.ca".replace(/\\/+$/,"");'
            'const API_BASE_URL="https:"+"//evil.invalid";fetch(API_BASE_URL+"/health");',
        ):
            with self.subTest(javascript=javascript), tempfile.TemporaryDirectory() as directory:
                dist, _ = self.make_dist(Path(directory), javascript=javascript)
                result = self.run_script(dist)

                self.assertEqual(result.returncode, 1)
                self.assertFalse((dist / "deployment.json").exists())

    def test_missing_or_duplicate_hashed_assets_block(self):
        cases = (
            """<title>AgentPulse Dashboard</title><div id="root"></div>
<link href="/assets/index-AbCd1234.css" rel="stylesheet">""",
            """<title>AgentPulse Dashboard</title><div id="root"></div>
<link href="/assets/index-AbCd1234.css" rel="stylesheet">
<script src="/assets/index-AbCd1234.js"></script>
<script src="/assets/index-Other567.js"></script>""",
        )
        for html in cases:
            with self.subTest(html=html), tempfile.TemporaryDirectory() as directory:
                dist, _ = self.make_dist(Path(directory), html=html)
                if "Other567" in html:
                    (dist / "assets" / "index-Other567.js").write_text(
                        'const e="https://api.agentpulse.ca".replace(/\\/$/,"");',
                        encoding="utf-8",
                    )
                result = self.run_script(dist)

                self.assertEqual(result.returncode, 1)
                self.assertFalse((dist / "deployment.json").exists())

    def test_asset_paths_inside_comments_do_not_satisfy_shell_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            dist, _ = self.make_dist(Path(directory))
            (dist / "index.html").write_text(
                "<!doctype html><html><head><title>AgentPulse Dashboard</title>"
                "<!-- /assets/index-TEST.css -->"
                "</head><body><div id=\"root\"></div>"
                "<!-- /assets/index-TEST.js -->"
                '<script src="https://evil.invalid/app.js"></script>'
                "</body></html>",
                encoding="utf-8",
            )

            result = self.run_script(dist)

            self.assertEqual(result.returncode, 1)
            self.assertIn("PRODUCTION_DASHBOARD_ARTIFACT=BLOCKED", result.stdout)
            self.assertFalse((dist / "deployment.json").exists())

    def test_fully_comment_only_shell_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            dist, _ = self.make_dist(Path(directory))
            (dist / "index.html").write_text(
                "<!doctype html><html><head>"
                "<!-- <title>AgentPulse Dashboard</title> -->"
                "<!-- <link rel=\"stylesheet\" href=\"/assets/index-TEST.css\"> -->"
                "</head><body>"
                "<!-- <div id=\"root\"></div> -->"
                "<!-- <script type=\"module\" src=\"/assets/index-TEST.js\"></script> -->"
                "</body></html>",
                encoding="utf-8",
            )

            result = self.run_script(dist)

            self.assertEqual(result.returncode, 1)
            self.assertIn("PRODUCTION_DASHBOARD_ARTIFACT=BLOCKED", result.stdout)
            self.assertFalse((dist / "deployment.json").exists())

    def test_shell_markers_inside_inert_elements_block(self):
        inert_shell = (
            '<title>AgentPulse Dashboard</title>'
            '<link rel="stylesheet" href="/assets/index-TEST.css">'
            '<div id="root"></div>'
            '<script type="module" src="/assets/index-TEST.js"></script>'
        )
        for tag in ("template", "noscript"):
            with self.subTest(tag=tag), tempfile.TemporaryDirectory() as directory:
                dist, _ = self.make_dist(Path(directory))
                (dist / "index.html").write_text(
                    f"<!doctype html><html><body><{tag}>{inert_shell}</{tag}></body></html>",
                    encoding="utf-8",
                )

                result = self.run_script(dist)

                self.assertEqual(result.returncode, 1)
                self.assertFalse((dist / "deployment.json").exists())

    def test_non_executable_or_inline_main_script_blocks(self):
        variants = (
            '<script type="application/json" src="/assets/index-TEST.js"></script>',
            '<script type="module" nomodule src="/assets/index-TEST.js"></script>',
            '<script type="module" src="/assets/index-TEST.js"></script><script>evil()</script>',
        )
        for scripts in variants:
            with self.subTest(scripts=scripts), tempfile.TemporaryDirectory() as directory:
                dist, _ = self.make_dist(Path(directory))
                (dist / "index.html").write_text(
                    "<!doctype html><html><head><title>AgentPulse Dashboard</title>"
                    '<link rel="stylesheet" href="/assets/index-TEST.css">'
                    f'</head><body><div id="root"></div>{scripts}</body></html>',
                    encoding="utf-8",
                )

                result = self.run_script(dist)

                self.assertEqual(result.returncode, 1)
                self.assertFalse((dist / "deployment.json").exists())

    def test_placeholder_shell_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            dist, _ = self.make_dist(Path(directory))
            index = dist / "index.html"
            index.write_text(index.read_text(encoding="utf-8") + "<!-- placeholder -->", encoding="utf-8")
            result = self.run_script(dist)

            self.assertEqual(result.returncode, 1)
            self.assertFalse((dist / "deployment.json").exists())

    def test_existing_manifest_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            dist, _ = self.make_dist(Path(directory))
            manifest = dist / "deployment.json"
            manifest.write_text("owner-artifact\n", encoding="utf-8")
            result = self.run_script(dist)

            self.assertEqual(result.returncode, 1)
            self.assertEqual(manifest.read_text(encoding="utf-8"), "owner-artifact\n")

    def test_symlinked_dist_directory_blocks_without_writing_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real_dist, _ = self.make_dist(root / "real")
            alias = root / "dist-alias"
            try:
                alias.symlink_to(real_dist, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symlinks are unavailable")

            result = self.run_script(alias)

            self.assertEqual(result.returncode, 1)
            self.assertIn("PRODUCTION_DASHBOARD_ARTIFACT=BLOCKED", result.stdout)
            self.assertFalse((real_dist / "deployment.json").exists())

    def test_symlinked_main_asset_blocks(self):
        if os.name == "nt":
            self.skipTest("symlink creation is not reliably available on Windows")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dist, _ = self.make_dist(root)
            asset = dist / "assets" / "index-AbCd1234.js"
            asset.unlink()
            outside = root / "outside.js"
            outside.write_text('const e="https://api.agentpulse.ca".replace(/\\/$/,"");', encoding="utf-8")
            asset.symlink_to(outside)
            result = self.run_script(dist)

            self.assertEqual(result.returncode, 1)
            self.assertFalse((dist / "deployment.json").exists())

    def test_runbook_examples_fail_closed_and_avoid_forced_rollback(self):
        text = RUNBOOK.read_text(encoding="utf-8")
        bash_blocks = re.findall(r"```bash\n(.*?)\n```", text, flags=re.DOTALL)

        self.assertGreaterEqual(len(bash_blocks), 6)
        for block in bash_blocks:
            self.assertTrue(block.startswith("set -euo pipefail\n"), block)
        self.assertIn("npm exec --no -- wrangler deploy --env production \\\n  --strict", text)
        self.assertIn("npm exec --no -- wrangler versions deploy", text)
        self.assertNotIn("npx wrangler", text)
        self.assertNotIn("npm exec --no -- wrangler rollback", text)
        self.assertIn('test -z "$(git status --porcelain -- dashboard)"', text)
        self.assertIn("defer the exact full production smoke", text)

    def test_public_production_runbooks_do_not_expose_workstation_paths(self):
        for path in (RUNBOOK, PREFLIGHT_RUNBOOK, SMOKE_RUNBOOK):
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("/home/", text)
                self.assertNotIn("desktopdusty", text)

    def test_workflow_fetches_history_and_pins_actions(self):
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("fetch-depth: 0", text)
        action_refs = re.findall(r"uses: (actions/[^@]+)@([^\s#]+)", text)
        self.assertGreaterEqual(len(action_refs), 2)
        for action, reference in action_refs:
            with self.subTest(action=action):
                self.assertRegex(reference, r"^[0-9a-f]{40}$")

    def test_release_workflow_is_immutable_artifact_only_and_pins_actions(self):
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("github.ref_type == 'tag'", text)
        self.assertIn('RELEASE_REF="$GITHUB_REF_NAME"', text)
        self.assertIn('SOURCE_SHA="$(git rev-parse "${RELEASE_REF}^{commit}")"', text)
        self.assertIn('PACKAGE_VERSION="$(python3 -c', text)
        self.assertIn('test "$PACKAGE_VERSION" = "$EXPECTED_PACKAGE_VERSION"', text)
        self.assertIn("tests.test_production_preflight", text)
        self.assertIn("tests.test_prepare_production_dashboard", text)
        self.assertIn("tests.test_production_smoke", text)
        self.assertIn("--only-verified --exclude-detectors=Lob", text)
        self.assertNotIn("deploy_control_plane", text)
        self.assertNotIn("release-control-plane", text)
        self.assertNotIn("wrangler-action", text)
        self.assertNotIn("environment: production", text)
        self.assertNotIn("deploy --env production", text)

        action_refs = re.findall(r"uses: ([^@\s]+)@([^\s#]+)", text)
        self.assertGreaterEqual(len(action_refs), 8)
        for action, reference in action_refs:
            with self.subTest(action=action):
                self.assertRegex(reference, r"^[0-9a-f]{40}$")

    def test_script_is_executable(self):
        self.assertTrue(os.access(SCRIPT, os.X_OK))


if __name__ == "__main__":
    unittest.main()
