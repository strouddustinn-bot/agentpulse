"""Locate packaged release assets shipped inside the agentpulse wheel."""

from __future__ import annotations

from importlib import resources
from pathlib import Path


def asset_path(*parts: str) -> Path:
    """Return a filesystem path to a packaged asset under agentpulse/assets/."""
    base = resources.files("agentpulse").joinpath("assets", *parts)
    with resources.as_file(base) as path:
        return Path(path)


def read_asset_text(*parts: str, encoding: str = "utf-8") -> str:
    return asset_path(*parts).read_text(encoding=encoding)
