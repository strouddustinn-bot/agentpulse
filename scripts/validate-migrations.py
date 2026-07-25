#!/usr/bin/env python3
"""Validate AgentPulse D1 migrations against fresh and upgraded SQLite fixtures."""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = sorted((ROOT / "control-plane" / "migrations").glob("*.sql"))


def apply_migrations(connection: sqlite3.Connection, migrations: list[Path]) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS _agentpulse_migrations "
        "(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    applied = {
        row[0]
        for row in connection.execute("SELECT name FROM _agentpulse_migrations")
    }
    for migration in migrations:
        if migration.name in applied:
            continue
        connection.executescript(migration.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO _agentpulse_migrations(name) VALUES (?)",
            (migration.name,),
        )
    connection.commit()


def columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def validate_fresh_replay() -> None:
    with sqlite3.connect(":memory:") as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        apply_migrations(connection, MIGRATIONS)
        apply_migrations(connection, MIGRATIONS)
        applied = connection.execute(
            "SELECT COUNT(*) FROM _agentpulse_migrations"
        ).fetchone()[0]
        if applied != len(MIGRATIONS):
            raise ValueError(f"migration replay ledger mismatch: {applied} != {len(MIGRATIONS)}")
        if not {"checkout_sessions", "browser_sessions"}.issubset(
            {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        ):
            raise ValueError("fresh migration is missing Phase 3A tables")


def validate_upgrade_fixture() -> None:
    if len(MIGRATIONS) < 2:
        raise ValueError("upgrade validation requires at least two migrations")
    with sqlite3.connect(":memory:") as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        apply_migrations(connection, MIGRATIONS[:1])
        timestamp = 1_721_868_800
        connection.execute(
            "INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)",
            ("tenant-upgrade", "upgrade@example.com", timestamp, timestamp),
        )
        for status in ("active", "trialing", "past_due", "canceled", "unpaid", "paused"):
            connection.execute(
                "INSERT INTO subscriptions "
                "(id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    f"sub-{status}",
                    "tenant-upgrade",
                    f"cus_{status}",
                    f"stripe_sub_{status}",
                    status,
                    "price_test",
                    "starter",
                    1,
                    timestamp,
                ),
            )
        connection.execute(
            "INSERT INTO stripe_events (id,event_type,received_at,processed_at) VALUES (?,?,?,?)",
            ("evt-processed", "invoice.paid", timestamp, timestamp + 1),
        )
        connection.execute(
            "INSERT INTO stripe_events (id,event_type,received_at,processing_error) VALUES (?,?,?,?)",
            ("evt-failed", "invoice.payment_failed", timestamp, "boom"),
        )
        connection.execute(
            "INSERT INTO stripe_events (id,event_type,received_at) VALUES (?,?,?)",
            ("evt-pending", "invoice.paid", timestamp),
        )
        connection.commit()

        apply_migrations(connection, MIGRATIONS[1:])
        entitlements = dict(
            connection.execute(
                "SELECT status, entitlement_status FROM subscriptions ORDER BY status"
            )
        )
        expected_entitlements = {
            "active": "active",
            "trialing": "active",
            "past_due": "blocked",
            "canceled": "blocked",
            "unpaid": "blocked",
            "paused": "blocked",
        }
        if entitlements != expected_entitlements:
            raise ValueError(f"subscription upgrade backfill is unsafe: {entitlements!r}")
        events = dict(
            connection.execute(
                "SELECT id, outcome FROM stripe_events ORDER BY id"
            )
        )
        expected_events = {
            "evt-processed": "processed",
            "evt-failed": "failed",
            "evt-pending": "pending",
        }
        if events != expected_events:
            raise ValueError(f"Stripe event upgrade backfill is unsafe: {events!r}")
        required = {
            "subscriptions": {"entitlement_status", "grace_period_ends_at"},
            "stripe_events": {"outcome", "retention_purge_at"},
        }
        for table, expected in required.items():
            missing = expected - columns(connection, table)
            if missing:
                raise ValueError(f"{table} missing upgraded columns: {sorted(missing)}")


def main() -> int:
    validate_fresh_replay()
    validate_upgrade_fixture()
    print(
        f"Migrations: PASS ({len(MIGRATIONS)} files; fresh replay and upgraded fixture)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
