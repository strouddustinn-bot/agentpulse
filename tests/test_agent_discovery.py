from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
AI_CRAWLERS = (
    "GPTBot",
    "OAI-SearchBot",
    "Claude-Web",
    "Google-Extended",
    "Amazonbot",
    "anthropic-ai",
    "Bytespider",
    "CCBot",
    "Applebot-Extended",
)
CONTENT_SIGNAL = "Content-Signal: ai-train=no, search=yes, ai-input=yes"


def robots_groups(text: str) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    current: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip()
            current = groups.setdefault(agent, [])
        elif current is not None:
            current.append(line)
    return groups


class AgentDiscoveryTest(unittest.TestCase):
    def test_robots_declares_wildcard_and_ai_crawler_policy(self) -> None:
        text = (DOCS / "robots.txt").read_text()
        groups = robots_groups(text)
        for agent in ("*", *AI_CRAWLERS):
            self.assertIn(agent, groups)
            self.assertIn("Allow: /", groups[agent])
            self.assertIn("Disallow: /planning/", groups[agent])
            self.assertIn(CONTENT_SIGNAL, groups[agent])
        self.assertIn("Sitemap: https://agentpulse.ca/sitemap.xml", text)

    def test_api_catalog_describes_only_the_live_staging_api(self) -> None:
        catalog = json.loads((DOCS / ".well-known/api-catalog").read_text())
        self.assertEqual(list(catalog), ["linkset"])
        self.assertEqual(len(catalog["linkset"]), 1)
        entry = catalog["linkset"][0]
        self.assertEqual(entry["anchor"], "https://staging-api.agentpulse.ca")
        self.assertEqual(entry["service-desc"], [
            {"href": "https://agentpulse.ca/api/openapi.yaml", "type": "application/yaml"}
        ])
        self.assertEqual(entry["service-doc"], [
            {"href": "https://agentpulse.ca/api/", "type": "text/html"}
        ])
        self.assertEqual(entry["status"], [
            {"href": "https://staging-api.agentpulse.ca/health", "type": "application/json"}
        ])
        self.assertNotIn("https://api.agentpulse.ca", json.dumps(catalog))

    def test_jekyll_publishes_well_known_files_and_canonical_openapi(self) -> None:
        config = (DOCS / "_config.yml").read_text()
        self.assertRegex(config, r"(?m)^include:\s*\[.*[\"']?\.well-known[\"']?.*\]\s*$")
        workflow = (ROOT / ".github/workflows/pages.yml").read_text()
        self.assertIn("cp packages/contracts/openapi.yaml docs/api/openapi.yaml", workflow)
        api_docs = (DOCS / "api/index.md").read_text()
        self.assertIn("staging-api.agentpulse.ca", api_docs)
        self.assertIn("production API is not deployed", api_docs)

    def test_agent_skill_index_has_a_verifiable_artifact(self) -> None:
        index_path = DOCS / ".well-known/agent-skills/index.json"
        index = json.loads(index_path.read_text())
        self.assertEqual(index["$schema"], "https://schemas.agentskills.io/discovery/0.2.0/schema.json")
        self.assertEqual(len(index["skills"]), 1)
        entry = index["skills"][0]
        self.assertEqual(entry["name"], "agentpulse-status")
        self.assertEqual(entry["type"], "skill-md")
        self.assertEqual(entry["url"], "https://agentpulse.ca/.well-known/agent-skills/agentpulse-status/SKILL.md")
        artifact = DOCS / ".well-known/agent-skills/agentpulse-status/SKILL.md"
        expected = "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest()
        self.assertEqual(entry["digest"], expected)

    def test_discovery_does_not_claim_unimplemented_auth_or_agent_services(self) -> None:
        absent = (
            ".well-known/openid-configuration",
            ".well-known/oauth-authorization-server",
            ".well-known/oauth-protected-resource",
            ".well-known/mcp/server-card.json",
            "auth.md",
        )
        for relative in absent:
            self.assertFalse((DOCS / relative).exists())
        self.assertNotIn("navigator.modelContext", (DOCS / "index.md").read_text())


if __name__ == "__main__":
    unittest.main()
