#!/usr/bin/env python3
"""Validate the packaged launchd plist without requiring macOS."""

from __future__ import annotations

import plistlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLIST = ROOT / "agent" / "packaging" / "com.agentpulse.agent.plist"


def main() -> int:
    data = plistlib.loads(PLIST.read_bytes())
    if data.get("Label") != "com.agentpulse.agent":
        print(f"unexpected label: {data.get('Label')!r}", file=sys.stderr)
        return 1
    args = data.get("ProgramArguments") or []
    if not args or not str(args[0]).endswith("agentpulse"):
        print(f"unexpected ProgramArguments: {args!r}", file=sys.stderr)
        return 1
    if "run" not in args:
        print("ProgramArguments must include 'run'", file=sys.stderr)
        return 1
    print("launchd plist: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
