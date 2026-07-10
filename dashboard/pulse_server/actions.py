"""Approve/deny pending actions by shelling out to the agent CLI.

The dashboard NEVER mutates state.json directly — the agent's own approve
path (decision loop, safety gate, verify) must run. Fail closed on anything
unexpected: unknown verb, malformed pending id, missing agent dir or config,
subprocess timeout, or exec errors. The command is always an argv list —
never a shell string — so ids can't be used for injection even if the
format check were bypassed.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Tuple

# Agent pending ids are short lowercase hex. Anything else is rejected
# before any subprocess is spawned.
_ID_RE = re.compile(r"^[0-9a-f]{6,12}$")

_TIMEOUT_S = 120


def _run_agent(agent_dir: str, config_path: str, verb: str,
               pending_id: str) -> Tuple[bool, str]:
    if verb not in ("approve", "deny"):
        return False, "invalid verb"
    if not isinstance(pending_id, str) or not _ID_RE.fullmatch(pending_id):
        return False, "invalid pending id format"
    if not agent_dir or not os.path.isdir(agent_dir):
        return False, "agent dir not configured or missing"
    if not config_path or not os.path.isfile(config_path):
        return False, "agent config not configured or missing"
    cmd = [sys.executable, "-m", "agentpulse", verb, config_path, pending_id]
    try:
        proc = subprocess.run(
            cmd, cwd=agent_dir, capture_output=True, text=True,
            timeout=_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return False, "agent CLI timed out"
    except OSError as exc:
        return False, "agent CLI failed to start: %s" % exc
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode == 0, out


def approve(agent_dir: str, config_path: str,
            pending_id: str) -> Tuple[bool, str]:
    return _run_agent(agent_dir, config_path, "approve", pending_id)


def deny(agent_dir: str, config_path: str,
         pending_id: str) -> Tuple[bool, str]:
    return _run_agent(agent_dir, config_path, "deny", pending_id)
