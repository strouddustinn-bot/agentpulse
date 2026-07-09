"""Management CLI for the AgentPulse backend."""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .settings import load_settings
from .store import DEFAULT_ORG_ID, Store


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agentpulse-backend", description="AgentPulse backend management"
    )
    p.add_argument(
        "--db",
        default=None,
        help="SQLite database path (default: AGENTPULSE_BACKEND_DB or ./data/agentpulse.db)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create/update backend database schema")

    key = sub.add_parser("create-api-key", help="create an agent/API bearer token")
    key.add_argument("--org", default=DEFAULT_ORG_ID, help="organization id")
    key.add_argument("--label", default="default", help="human-readable token label")

    lic = sub.add_parser("create-license", help="create a paid-plan license key")
    lic.add_argument("--org", default=DEFAULT_ORG_ID, help="organization id")
    lic.add_argument("--plan", default="starter", help="plan name")
    lic.add_argument("--max-agents", type=int, default=1, help="maximum agents allowed")
    lic.add_argument(
        "--expires-at", default=None, help="optional ISO-8601 expiry timestamp"
    )

    verify = sub.add_parser("verify-license", help="verify a license key")
    verify.add_argument("license_key")
    verify.add_argument(
        "--agent-id", default="", help="optional agent id for limit checks"
    )

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    store = Store(args.db or settings.db_path)

    if args.command == "init-db":
        store.init_db()
        print(f"initialized database: {store.db_path}")
        return 0

    if args.command == "create-api-key":
        store.init_db()
        token = store.create_api_key(org_id=args.org, label=args.label)
        print(token)
        print("Store this now; only the SHA-256 hash is saved.", file=sys.stderr)
        return 0

    if args.command == "create-license":
        store.init_db()
        key = store.create_license(
            org_id=args.org,
            plan=args.plan,
            max_agents=args.max_agents,
            expires_at=args.expires_at,
        )
        print(key)
        print("Store this now; only the SHA-256 hash is saved.", file=sys.stderr)
        return 0

    if args.command == "verify-license":
        store.init_db()
        result = store.verify_license(
            license_key=args.license_key, agent_id=args.agent_id
        )
        print(
            f"active={str(result.active).lower()} reason={result.reason!r} "
            f"org={result.org_id} plan={result.plan} max_agents={result.max_agents}"
        )
        return 0 if result.active else 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
