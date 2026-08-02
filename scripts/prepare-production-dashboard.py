#!/usr/bin/env python3
"""Create the identity-only manifest for an AgentPulse production dashboard build."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

PRODUCTION_API_ORIGIN = "https://api.agentpulse.ca"
VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?")
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
MAIN_JS_PATTERN = re.compile(r"/assets/index-[A-Za-z0-9_-]+\.js")
MAIN_CSS_PATTERN = re.compile(r"/assets/index-[A-Za-z0-9_-]+\.css")
ALLOWED_ASSIGNED_ORIGINS = {
    PRODUCTION_API_ORIGIN,
    "http://localhost",
    "http://localhost:8787",
    "http://www.w3.org/2000/svg",
    "https://react.dev/errors/",
}
ALLOWED_LITERAL_ORIGINS = {
    PRODUCTION_API_ORIGIN,
    "http://localhost",
    "http://www.w3.org",
    "https://react.dev",
}
FORBIDDEN_API_MARKERS = (
    "staging-api.agentpulse.ca",
    "127.0.0.1",
    "0.0.0.0",
    ".workers.dev",
)


class ArtifactError(RuntimeError):
    """A fail-closed production artifact validation error."""


class DashboardShellParser(HTMLParser):
    """Collect executable shell markers while ignoring comments."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title_parts: list[str] = []
        self.root_count = 0
        self.script_sources: list[tuple[str, str, bool]] = []
        self.inline_script_count = 0
        self.style_sources: list[str] = []
        self.base_count = 0
        self.inert_depth = 0
        self.duplicate_attribute = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered_tag = tag.lower()
        names = [name.lower() for name, _ in attrs]
        if len(names) != len(set(names)):
            self.duplicate_attribute = True
        attributes = {name.lower(): value or "" for name, value in attrs}

        if lowered_tag in {"template", "noscript"}:
            self.inert_depth += 1
            return
        if self.inert_depth:
            return
        if lowered_tag == "title":
            self.in_title = True
        if lowered_tag == "div" and attributes.get("id") == "root":
            self.root_count += 1
        if lowered_tag == "base":
            self.base_count += 1
        if lowered_tag == "script":
            source = attributes.get("src")
            if source:
                self.script_sources.append(
                    (source, attributes.get("type", ""), "nomodule" in names)
                )
            else:
                self.inline_script_count += 1
        if lowered_tag == "link":
            relation = {value.lower() for value in attributes.get("rel", "").split()}
            href = attributes.get("href")
            if "stylesheet" in relation and href:
                self.style_sources.append(href)

    def handle_endtag(self, tag: str) -> None:
        lowered_tag = tag.lower()
        if lowered_tag in {"template", "noscript"} and self.inert_depth:
            self.inert_depth -= 1
            return
        if self.inert_depth:
            return
        if lowered_tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title and not self.inert_depth:
            self.title_parts.append(data)

    @property
    def title(self) -> str:
        return "".join(self.title_parts).strip()


def _exact_single(matches: list[str], label: str) -> str:
    unique = sorted(set(matches))
    if len(unique) != 1:
        raise ArtifactError(f"expected exactly one {label}, found {len(unique)}")
    return unique[0]


def _safe_asset(dist: Path, public_path: str) -> Path:
    relative = public_path.removeprefix("/")
    candidate = dist / relative
    if candidate.is_symlink():
        raise ArtifactError(f"asset must not be a symlink: {public_path}")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ArtifactError(f"asset is missing: {public_path}") from exc
    try:
        resolved.relative_to(dist)
    except ValueError as exc:
        raise ArtifactError(f"asset escapes the dashboard build: {public_path}") from exc
    if not resolved.is_file():
        raise ArtifactError(f"asset is not a regular file: {public_path}")
    return resolved


def _validate_api_bundle(bundle: bytes) -> None:
    try:
        text = bundle.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ArtifactError("main JavaScript asset is not UTF-8") from exc

    lowered = text.lower()
    forbidden = [marker for marker in FORBIDDEN_API_MARKERS if marker in lowered]
    if forbidden:
        raise ArtifactError("main JavaScript contains a forbidden non-production API marker")
    if "api.agentpulse.ca" in text.replace(PRODUCTION_API_ORIGIN, ""):
        raise ArtifactError("main JavaScript contains an ambiguous AgentPulse API hostname")
    dynamic_origin_patterns = (
        r"([\"'])https?://\1\s*\+",
        r"([\"'])https?:\1\s*\+\s*([\"'])//",
        r"([\"'])https?\1\s*\+\s*([\"']):?//",
        r"`https?://[^`]*\$\{",
    )
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in dynamic_origin_patterns):
        raise ArtifactError("main JavaScript contains a dynamically constructed URL origin")

    literal_urls = {
        match[1]
        for match in re.findall(
            r"([\"'`])(https?://[^\"'`\\\s]+)\1",
            text,
            flags=re.IGNORECASE,
        )
    }
    localhost_urls = {value for value in literal_urls if value.startswith("http://localhost")}
    if localhost_urls:
        localhost_matches = list(
            re.finditer(r"([\"'`])http://localhost\1", text)
        )
        if localhost_urls != {"http://localhost"} or len(localhost_matches) != 1:
            raise ArtifactError("main JavaScript contains an unapproved localhost URL")
        context = text[localhost_matches[0].start() : localhost_matches[0].start() + 500]
        if "No window.location.(origin|href) available to create URL" not in context:
            raise ArtifactError("main JavaScript uses localhost outside the pinned router fallback")

    literal_origins: set[str] = set()
    for value in literal_urls:
        try:
            parsed = urlsplit(value)
            if parsed.username is not None or parsed.password is not None or parsed.hostname is None:
                raise ValueError
            # Accessing port validates that a malformed port cannot hide in netloc.
            parsed.port
        except ValueError as exc:
            raise ArtifactError("main JavaScript contains a malformed absolute URL literal") from exc
        literal_origins.add(f"{parsed.scheme.lower()}://{parsed.netloc.lower()}")
    unknown_literal_origins = sorted(literal_origins - ALLOWED_LITERAL_ORIGINS)
    if unknown_literal_origins:
        raise ArtifactError("main JavaScript contains an unapproved absolute URL origin")

    active_api_origins = set(
        re.findall(
            r"\b[A-Za-z_$][A-Za-z0-9_$]*(?:api|base)[A-Za-z0-9_$]*\s*=\s*"
            r"[\"'](https?://[^\"'\\\s]+)[\"']",
            text,
            flags=re.IGNORECASE,
        )
    )
    if active_api_origins - {PRODUCTION_API_ORIGIN}:
        raise ArtifactError("main JavaScript assigns an active API/base variable to a non-production origin")

    selected_origins = {
        match[1]
        for match in re.findall(
            r"=\s*([\"'])(https?://[^\"'\\\s]+)\1\.replace\(",
            text,
        )
    }
    assigned_origins = {
        match[1]
        for match in re.findall(
            r"=\s*([\"'])(https?://[^\"'\\\s]+)\1",
            text,
        )
    }
    if selected_origins != {PRODUCTION_API_ORIGIN}:
        raise ArtifactError("main JavaScript does not select the canonical production API origin")
    unknown = sorted(assigned_origins - ALLOWED_ASSIGNED_ORIGINS)
    if unknown:
        raise ArtifactError("main JavaScript contains unknown assigned URL origins")


def prepare_manifest(dist_value: str, version: str, source_sha: str) -> Path:
    if VERSION_PATTERN.fullmatch(version) is None:
        raise ArtifactError("version must be an exact semantic release version")
    if SHA_PATTERN.fullmatch(source_sha) is None:
        raise ArtifactError("source SHA must be a full lowercase 40-character commit SHA")

    raw_dist = Path(dist_value).expanduser()
    absolute_dist = Path(os.path.abspath(raw_dist))
    if raw_dist.is_symlink():
        raise ArtifactError("dashboard dist path must not be a symlink")
    dist = raw_dist.resolve(strict=True)
    if dist != absolute_dist:
        raise ArtifactError("dashboard dist path must not traverse symlinked directories")
    if not dist.is_dir():
        raise ArtifactError("dashboard dist path must be a directory")

    index = dist / "index.html"
    if index.is_symlink() or not index.is_file():
        raise ArtifactError("dashboard dist must contain a regular index.html")
    try:
        html = index.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ArtifactError("dashboard index.html is not UTF-8") from exc

    parser = DashboardShellParser()
    parser.feed(html)
    parser.close()
    if parser.duplicate_attribute:
        raise ArtifactError("dashboard shell contains duplicate HTML attributes")
    if parser.title != "AgentPulse Dashboard":
        raise ArtifactError("dashboard title marker is missing or ambiguous")
    if parser.root_count != 1:
        raise ArtifactError(f"expected exactly one dashboard root element, found {parser.root_count}")
    if parser.base_count:
        raise ArtifactError("dashboard shell must not contain a base element")
    if parser.inline_script_count:
        raise ArtifactError("dashboard shell must not contain inline scripts")
    if "placeholder" in html.lower():
        raise ArtifactError("dashboard placeholder marker is present")

    if len(parser.script_sources) != 1:
        raise ArtifactError(
            f"expected exactly one executable script source, found {len(parser.script_sources)}"
        )
    script_source, script_type, script_nomodule = parser.script_sources[0]
    if script_type.lower() != "module" or script_nomodule:
        raise ArtifactError("main JavaScript source must be an executable module script")
    if len(parser.style_sources) != 1:
        raise ArtifactError(f"expected exactly one stylesheet source, found {len(parser.style_sources)}")
    style_source = parser.style_sources[0]

    script_parts = urlsplit(script_source)
    style_parts = urlsplit(style_source)
    if script_parts.scheme or script_parts.netloc or script_parts.query or script_parts.fragment:
        raise ArtifactError("main JavaScript source must be an unqualified local asset path")
    if style_parts.scheme or style_parts.netloc or style_parts.query or style_parts.fragment:
        raise ArtifactError("main CSS source must be an unqualified local asset path")

    main_js_public = _exact_single(
        [script_source] if MAIN_JS_PATTERN.fullmatch(script_source) else [],
        "hashed main JavaScript asset",
    )
    main_css_public = _exact_single(
        [style_source] if MAIN_CSS_PATTERN.fullmatch(style_source) else [],
        "hashed main CSS asset",
    )
    main_js = _safe_asset(dist, main_js_public)
    _safe_asset(dist, main_css_public)

    bundle = main_js.read_bytes()
    _validate_api_bundle(bundle)
    digest = hashlib.sha256(bundle).hexdigest()

    manifest = {
        "service": "agentpulse-dashboard",
        "environment": "production",
        "version": version,
        "source_sha": source_sha,
        "api_base_url": PRODUCTION_API_ORIGIN,
        "main_js_sha256": digest,
    }
    manifest_path = dist / "deployment.json"
    payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    try:
        descriptor = os.open(
            manifest_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o644,
        )
    except FileExistsError as exc:
        raise ArtifactError("deployment.json already exists; use a fresh build directory") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(payload)

    return manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a fail-closed production dashboard deployment manifest",
    )
    parser.add_argument("--dist", required=True, help="fresh dashboard build directory")
    parser.add_argument("--version", required=True, help="exact package version")
    parser.add_argument("--source-sha", required=True, help="full immutable source commit SHA")
    args = parser.parse_args(argv)

    try:
        manifest_path = prepare_manifest(args.dist, args.version, args.source_sha)
    except (ArtifactError, FileNotFoundError, OSError) as exc:
        print("PRODUCTION_DASHBOARD_ARTIFACT=BLOCKED")
        print(f"[BLOCK] {exc}")
        return 1

    print("PRODUCTION_DASHBOARD_ARTIFACT=PASS")
    print(f"MANIFEST_PATH={manifest_path}")
    print("No credential, billing, DNS, migration, deployment, or provider mutation was performed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
