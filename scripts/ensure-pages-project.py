#!/usr/bin/env python3
"""Create or verify the one approved AgentPulse production Pages project."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

API_ROOT = "https://api.cloudflare.com/client/v4"
UrlOpen = Callable[..., object]


def _request_json(
    url: str,
    token: str,
    *,
    method: str = "GET",
    body: dict[str, str] | None = None,
    opener: UrlOpen = urllib.request.urlopen,
) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with opener(request, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise RuntimeError("Cloudflare Pages API did not return success")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("Cloudflare Pages API returned an invalid project")
    return result


def ensure_pages_project(
    account_id: str,
    token: str,
    project_name: str,
    production_branch: str,
    *,
    opener: UrlOpen = urllib.request.urlopen,
) -> str:
    encoded_account = urllib.parse.quote(account_id, safe="")
    encoded_project = urllib.parse.quote(project_name, safe="")
    collection_url = f"{API_ROOT}/accounts/{encoded_account}/pages/projects"
    project_url = f"{collection_url}/{encoded_project}"

    try:
        project = _request_json(project_url, token, opener=opener)
        disposition = "reused"
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        project = _request_json(
            collection_url,
            token,
            method="POST",
            body={"name": project_name, "production_branch": production_branch},
            opener=opener,
        )
        disposition = "created"

    if project.get("name") != project_name:
        raise RuntimeError("production Pages project name is invalid")
    if project.get("production_branch") != production_branch:
        raise RuntimeError("production Pages project branch is invalid")
    return disposition


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", default=os.environ.get("CLOUDFLARE_ACCOUNT_ID"))
    parser.add_argument("--token", default=os.environ.get("CLOUDFLARE_API_TOKEN"))
    parser.add_argument("--project", default=os.environ.get("PRODUCTION_PAGES_PROJECT"))
    parser.add_argument("--production-branch", default=os.environ.get("PRODUCTION_PAGES_BRANCH"))
    args = parser.parse_args(argv)

    missing = [
        name
        for name, value in (
            ("account ID", args.account_id),
            ("API token", args.token),
            ("project", args.project),
            ("production branch", args.production_branch),
        )
        if not value
    ]
    if missing:
        parser.error(f"missing {', '.join(missing)}")

    try:
        disposition = ensure_pages_project(
            args.account_id,
            args.token,
            args.project,
            args.production_branch,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"production Pages project verification failed: {exc}", file=sys.stderr)
        return 1

    print(f"production_pages={disposition}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
