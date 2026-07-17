"""Packaging integrity tests for the AgentPulse agent release artifact.

These tests deliberately build an isolated wheel and assert release gates from
Tier 1 of the completion plan. They are separate from the dependency-light agent
unit suite so `agent/tools/run_tests.py` stays free of build tooling.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG = ROOT / "agent" / "agentpulse.config.example.json"
LOCAL_CONFIG = ROOT / "agent" / "agentpulse.config.local.json"


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


class PackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="agentpulse-packaging-"))
        cls.venv = cls.tmpdir / "build-venv"
        cls.dist = cls.tmpdir / "dist"
        cls.dist.mkdir()
        py = sys.executable
        create = _run([py, "-m", "venv", str(cls.venv)])
        if create.returncode != 0:
            raise unittest.SkipTest(f"unable to create build venv: {create.stderr}")
        cls.pip = cls.venv / "bin" / "pip"
        cls.python = cls.venv / "bin" / "python"
        install = _run([str(cls.pip), "install", "--upgrade", "pip", "build"])
        if install.returncode != 0:
            raise unittest.SkipTest(f"unable to install build tooling: {install.stderr}")
        build = _run(
            [str(cls.python), "-m", "build", "--wheel", "--outdir", str(cls.dist)],
            cwd=ROOT,
        )
        if build.returncode != 0:
            # Keep stdout/stderr for assertions that expect a successful build later.
            cls.build_stdout = build.stdout
            cls.build_stderr = build.stderr
            cls.wheel = None
            return
        wheels = sorted(cls.dist.glob("agentpulse-*.whl"))
        if not wheels:
            cls.wheel = None
            cls.build_stdout = build.stdout
            cls.build_stderr = build.stderr
            return
        cls.wheel = wheels[-1]
        cls.build_stdout = build.stdout
        cls.build_stderr = build.stderr
        with zipfile.ZipFile(cls.wheel) as zf:
            cls.names = set(zf.namelist())

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_wheel_builds_successfully(self) -> None:
        self.assertIsNotNone(self.wheel, msg=f"wheel build failed\n{self.build_stdout}\n{self.build_stderr}")
        self.assertTrue(self.wheel.is_file())
        self.assertGreater(self.wheel.stat().st_size, 1024)

    def test_wheel_contains_agentpulse_package(self) -> None:
        self.assertIsNotNone(self.wheel)
        package_files = [n for n in self.names if n.startswith("agentpulse/") and n.endswith(".py")]
        self.assertIn("agentpulse/__init__.py", self.names)
        self.assertIn("agentpulse/cli.py", self.names)
        self.assertGreaterEqual(len(package_files), 10)

    def test_wheel_contains_systemd_unit(self) -> None:
        self.assertIsNotNone(self.wheel)
        matches = [n for n in self.names if n.endswith("agentpulse.service")]
        self.assertTrue(matches, msg=f"systemd unit missing from wheel: {sorted(self.names)[:40]}")
        self.assertTrue(any("assets" in n or "systemd" in n for n in matches))

    def test_wheel_contains_launchd_plist(self) -> None:
        self.assertIsNotNone(self.wheel)
        matches = [n for n in self.names if n.endswith(".plist")]
        self.assertTrue(matches, msg="launchd plist missing from wheel")
        self.assertTrue(any("com.agentpulse.agent.plist" in n for n in matches))

    def test_wheel_contains_example_config(self) -> None:
        self.assertIsNotNone(self.wheel)
        matches = [n for n in self.names if n.endswith("agentpulse.config.example.json")]
        self.assertTrue(matches, msg="example config missing from wheel")

    def test_wheel_contains_license_and_version_metadata(self) -> None:
        self.assertIsNotNone(self.wheel)
        license_matches = [n for n in self.names if n.endswith("LICENSE") or n.endswith("LICENSE.txt")]
        self.assertTrue(license_matches, msg="LICENSE missing from wheel")
        dist_info = [n for n in self.names if n.endswith(".dist-info/METADATA")]
        self.assertTrue(dist_info)
        with zipfile.ZipFile(self.wheel) as zf:
            metadata = zf.read(dist_info[0]).decode("utf-8")
        self.assertRegex(metadata, r"(?m)^Name: agentpulse$")
        # Accept PEP 440 final and pre-release versions (e.g. 0.2.0b1).
        self.assertRegex(metadata, r"(?m)^Version: \d+\.\d+\.\d+(?:[a-zA-Z]+\d+(?:\.\d+)*)?")
        self.assertTrue(
            re.search(r"(?mi)^License(-Expression)?:.*Apache", metadata),
            msg="Apache license metadata missing",
        )
        # Console script must be declared.
        entry_points = [n for n in self.names if n.endswith(".dist-info/entry_points.txt")]
        self.assertTrue(entry_points)
        with zipfile.ZipFile(self.wheel) as zf:
            ep = zf.read(entry_points[0]).decode("utf-8")
        self.assertIn("[console_scripts]", ep)
        self.assertIn("agentpulse = agentpulse.cli:main", ep)

    def test_wheel_excludes_control_plane_and_dashboard_source(self) -> None:
        self.assertIsNotNone(self.wheel)
        forbidden_prefixes = (
            "control-plane/",
            "dashboard/",
            "packages/contracts/",
            "docs/",
        )
        for name in self.names:
            for prefix in forbidden_prefixes:
                self.assertFalse(
                    name.startswith(prefix),
                    msg=f"wheel unexpectedly contains {name}",
                )

    def test_fresh_venv_install_exposes_cli(self) -> None:
        self.assertIsNotNone(self.wheel)
        install_venv = self.tmpdir / "install-venv"
        create = _run([sys.executable, "-m", "venv", str(install_venv)])
        self.assertEqual(create.returncode, 0, create.stderr)
        pip = install_venv / "bin" / "pip"
        python = install_venv / "bin" / "python"
        agentpulse = install_venv / "bin" / "agentpulse"
        installed = _run([str(pip), "install", str(self.wheel)])
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertTrue(agentpulse.is_file())

        help_proc = _run([str(agentpulse), "--help"])
        self.assertEqual(help_proc.returncode, 0, help_proc.stderr)
        self.assertIn("validate", help_proc.stdout)
        self.assertIn("run-once", help_proc.stdout)

        version_proc = _run([str(agentpulse), "--version"])
        self.assertEqual(version_proc.returncode, 0, version_proc.stderr)
        self.assertRegex(
            version_proc.stdout + version_proc.stderr,
            r"agentpulse\s+\d+\.\d+\.\d+(?:[a-zA-Z]+\d+(?:\.\d+)*)?",
        )

        # Safe configs: local config is developer-oriented and should validate.
        # Use a temp copy so the installed package cannot mutate the repo.
        work = self.tmpdir / "cli-work"
        work.mkdir(exist_ok=True)
        cfg = work / "config.json"
        cfg.write_text(LOCAL_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
        # Point state/log into the temp dir so dry-run cannot touch system paths.
        data = json.loads(cfg.read_text(encoding="utf-8"))
        data["state_file"] = str(work / "state.json")
        data["log_file"] = str(work / "agentpulse.log")
        if "control_plane" in data and isinstance(data["control_plane"], dict):
            data["control_plane"]["credential_file"] = str(work / "agent.credential")
        cfg.write_text(json.dumps(data, indent=2), encoding="utf-8")

        validate = _run([str(agentpulse), "validate", str(cfg)])
        self.assertEqual(validate.returncode, 0, validate.stderr)
        self.assertIn("OK: config is valid", validate.stdout)

        dry = _run([str(agentpulse), "run-once", "--dry-run", str(cfg)])
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertRegex(dry.stdout, r"observations=\d+")

        # Importable module version matches metadata.
        mod_ver = _run([str(python), "-c", "import agentpulse; print(agentpulse.__version__)"])
        self.assertEqual(mod_ver.returncode, 0, mod_ver.stderr)
        self.assertRegex(mod_ver.stdout.strip(), r"^\d+\.\d+\.\d+(?:[a-zA-Z]+\d+(?:\.\d+)*)?$")

    def test_release_workflow_publishes_checksums(self) -> None:
        text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("python -m build", text)
        self.assertRegex(text, r"SHA256SUMS|sha256sum")
        self.assertTrue(
            ("dist/*.whl" in text) or ("dist/agentpulse-*.whl" in text),
            msg="release workflow must publish wheel artifacts under dist/",
        )
        # Must not publish only CHANGELOG without the wheel.
        self.assertIn("agentpulse-*.whl", text)

    def test_installers_require_immutable_release_artifacts(self) -> None:
        install = (ROOT / "scripts" / "install-agent.sh").read_text(encoding="utf-8")
        public = (ROOT / "docs" / "install.sh").read_text(encoding="utf-8")
        # No mutable branch raw fetches.
        self.assertNotIn("raw.githubusercontent.com", install)
        self.assertNotIn("/main/", install)
        self.assertIn("SHA-256", install + public or install)
        self.assertTrue(
            re.search(r"--version|AGENTPULSE_VERSION|RELEASE_VERSION", install),
            msg="installer must require an explicit release version",
        )
        self.assertIn("releases/download", install)
        # Public endpoint remains fail-closed until release gates pass, OR supports
        # version+checksum flow. Either way it must not curl raw main files.
        self.assertNotIn("raw.githubusercontent.com", public)
        self.assertNotIn("pip install --quiet agentpulse", install)

    def test_upgrade_and_rollback_scripts_exist(self) -> None:
        upgrade = ROOT / "scripts" / "upgrade-agent.sh"
        rollback = ROOT / "scripts" / "rollback-agent.sh"
        self.assertTrue(upgrade.is_file())
        self.assertTrue(rollback.is_file())
        upgrade_text = upgrade.read_text(encoding="utf-8")
        rollback_text = rollback.read_text(encoding="utf-8")
        self.assertIn("SHA", upgrade_text.upper())
        self.assertIn("preserve", (upgrade_text + rollback_text).lower())
        for path in (upgrade, rollback):
            self.assertTrue(os.access(path, os.X_OK), msg=f"{path} must be executable")


if __name__ == "__main__":
    unittest.main()
