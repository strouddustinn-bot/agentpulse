#!/usr/bin/env python3
"""Capture read-only Cloudflare state for the production bootstrap decision.

The script fails closed on transport, authentication, API, pagination, or schema
ambiguity. It emits a redacted JSON document and never prints credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, NamedTuple, Sequence

CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"
DEFAULT_WORKER = "agentpulse-control-plane-production"
DEFAULT_PAGES_PROJECT = "agentpulse-production-app"


class CaptureError(RuntimeError):
    """A provider response could not prove a safe state."""


class ApiResponse(NamedTuple):
    status: int
    payload: object


Requester = Callable[[str, str, str], ApiResponse]


def strict_json_loads(text: str) -> object:
    def reject_constant(value: str) -> object:
        raise ValueError(f"non-standard JSON constant: {value}")

    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(
        text,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicate_keys,
    )


def _request_json(url: str, account_id: str, api_token: str) -> ApiResponse:
    del account_id
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_token}",
            "User-Agent": "AgentPulse-production-state/1",
        },
    )
    try:
        response = urllib.request.urlopen(request, timeout=20)
    except urllib.error.HTTPError as exc:
        response = exc
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise CaptureError(f"Cloudflare request failed: {type(exc).__name__}") from exc
    try:
        body = response.read(2 * 1024 * 1024 + 1)
        if len(body) > 2 * 1024 * 1024:
            raise CaptureError("Cloudflare response exceeded the 2 MiB limit")
        try:
            payload = strict_json_loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise CaptureError("Cloudflare returned malformed JSON") from exc
        status = response.getcode()
        if not isinstance(status, int):
            raise CaptureError("Cloudflare response omitted HTTP status")
        return ApiResponse(status, payload)
    finally:
        response.close()


def _result_list(response: ApiResponse, label: str) -> list[object]:
    if response.status != 200:
        raise CaptureError(f"{label} returned HTTP {response.status}")
    payload = response.payload
    if not isinstance(payload, dict):
        raise CaptureError(f"{label} response must be an object")
    if payload.get("success") is not True:
        raise CaptureError(f"{label} did not report success")
    if payload.get("errors") != []:
        raise CaptureError(f"{label} returned provider errors")
    result = payload.get("result")
    if not isinstance(result, list):
        raise CaptureError(f"{label} result must be an array")
    return result


def capture_state(
    account_id: str,
    api_token: str,
    worker_name: str,
    pages_project: str,
    *,
    requester: Requester = _request_json,
) -> dict[str, object]:
    if not account_id or not api_token:
        raise CaptureError("Cloudflare account ID and API token are required")
    if not worker_name or not pages_project:
        raise CaptureError("Worker and Pages project names are required")

    workers_url = f"{CLOUDFLARE_API}/accounts/{urllib.parse.quote(account_id, safe='')}/workers/scripts"
    workers = _result_list(
        requester(workers_url, account_id, api_token),
        "Workers list",
    )
    worker_ids: list[str] = []
    for item in workers:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise CaptureError("Workers list contained a malformed entry")
        worker_ids.append(item["id"])
    if len(worker_ids) != len(set(worker_ids)):
        raise CaptureError("Workers list contained duplicate identities")
    worker_present = worker_name in worker_ids

    pages_url = (
        f"{CLOUDFLARE_API}/accounts/{urllib.parse.quote(account_id, safe='')}"
        f"/pages/projects/{urllib.parse.quote(pages_project, safe='')}/deployments"
        "?env=production&page=1&per_page=1"
    )
    deployments = _result_list(
        requester(pages_url, account_id, api_token),
        "Pages production deployment list",
    )
    if len(deployments) > 1:
        raise CaptureError("Pages API ignored the one-result page bound")
    for item in deployments:
        if (
            not isinstance(item, dict)
            or item.get("project_name") != pages_project
            or item.get("environment") != "production"
            or not isinstance(item.get("id"), str)
            or not item["id"]
        ):
            raise CaptureError("Pages list contained an unrelated or malformed deployment")
    pages_production_deployment_present = bool(deployments)
    # The production workflow deploys the Worker before Pages. A failed route
    # attachment can therefore leave the Worker script present even though the
    # first production deployment never reached the console or smoke gates.
    # The first successful production Pages deployment is the durable marker
    # that the bootstrap sequence completed and DNS must be enforced on every
    # later deployment.
    bootstrap_allowed = not pages_production_deployment_present
    return {
        "schema_version": 1,
        "worker_name": worker_name,
        "worker_present": worker_present,
        "pages_project": pages_project,
        "production_pages_deployment_present": pages_production_deployment_present,
        "bootstrap_allowed": bootstrap_allowed,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-name", default=DEFAULT_WORKER)
    parser.add_argument("--pages-project", default=DEFAULT_PAGES_PROJECT)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        state = capture_state(
            os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""),
            os.environ.get("CLOUDFLARE_API_TOKEN", ""),
            args.worker_name,
            args.pages_project,
        )
        args.output.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (CaptureError, OSError) as exc:
        print("PRODUCTION_PROVIDER_STATE=BLOCKED")
        print(f"[BLOCK] provider_state_unverified: {exc}")
        return 1
    print("PRODUCTION_PROVIDER_STATE=CAPTURED")
    print(f"bootstrap_allowed={'true' if state['bootstrap_allowed'] else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
