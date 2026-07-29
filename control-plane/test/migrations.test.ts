import { applyD1Migrations } from "cloudflare:test";
import { env } from "cloudflare:workers";
import { describe, expect, it } from "vitest";

async function tableExists(name: string): Promise<boolean> {
  const row = await env.DB.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name=?")
    .bind(name)
    .first<{ name: string }>();
  return row !== null;
}

async function columnNames(table: string): Promise<string[]> {
  const result = await env.DB.prepare(`PRAGMA table_info(${table})`).all<{ name: string }>();
  return result.results.map((column) => column.name);
}

describe("Phase 3A schema: checkout claim, browser sessions, entitlement, webhook outcome", () => {
  it("creates a checkout_sessions table holding pre-payment claim nonce state", async () => {
    expect(await tableExists("checkout_sessions")).toBe(true);
    const columns = await columnNames("checkout_sessions");
    expect(columns).toEqual(
      expect.arrayContaining([
        "stripe_checkout_session_id",
        "claim_nonce_hash",
        "price_id",
        "plan",
        "status",
        "tenant_id",
        "created_at",
        "expires_at",
        "ready_at",
        "claimed_at",
        "retention_purge_at",
      ]),
    );
  });

  it("allows a checkout_sessions row with no tenant yet (pre-webhook) and enforces a unique claim nonce", async () => {
    const timestamp = Math.floor(Date.now() / 1000);
    await env.DB.prepare(
      "INSERT INTO checkout_sessions (stripe_checkout_session_id,claim_nonce_hash,price_id,plan,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?)",
    ).bind("cs_test_1", "nonce-hash-1", "price_test", "pro", "pending", timestamp, timestamp + 900).run();
    const row = await env.DB.prepare("SELECT tenant_id, status FROM checkout_sessions WHERE stripe_checkout_session_id=?")
      .bind("cs_test_1")
      .first<{ tenant_id: string | null; status: string }>();
    expect(row?.tenant_id).toBeNull();
    expect(row?.status).toBe("pending");

    await expect(
      env.DB.prepare(
        "INSERT INTO checkout_sessions (stripe_checkout_session_id,claim_nonce_hash,price_id,plan,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?)",
      ).bind("cs_test_2", "nonce-hash-1", "price_test", "pro", "pending", timestamp, timestamp + 900).run(),
    ).rejects.toThrow();
  });

  it("rejects a checkout_sessions status outside the approved lifecycle", async () => {
    const timestamp = Math.floor(Date.now() / 1000);
    await expect(
      env.DB.prepare(
        "INSERT INTO checkout_sessions (stripe_checkout_session_id,claim_nonce_hash,price_id,plan,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?)",
      ).bind("cs_test_bad_status", "nonce-hash-bad", "price_test", "pro", "invented", timestamp, timestamp + 900).run(),
    ).rejects.toThrow();
  });

  it("creates a browser_sessions table with hashed token, csrf, expiry, revocation, and rotation lineage", async () => {
    expect(await tableExists("browser_sessions")).toBe(true);
    const columns = await columnNames("browser_sessions");
    expect(columns).toEqual(
      expect.arrayContaining([
        "id",
        "tenant_id",
        "session_hash",
        "csrf_token_hash",
        "created_at",
        "expires_at",
        "last_seen_at",
        "rotated_from_id",
        "revoked_at",
        "retention_purge_at",
      ]),
    );
  });

  it("enforces a unique session_hash and supports rotation lineage on browser_sessions", async () => {
    const timestamp = Math.floor(Date.now() / 1000);
    await env.DB.prepare("INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)")
      .bind("tenant-sessions", "sessions@example.com", timestamp, timestamp)
      .run();
    await env.DB.prepare(
      "INSERT INTO browser_sessions (id,tenant_id,session_hash,csrf_token_hash,created_at,expires_at) VALUES (?,?,?,?,?,?)",
    ).bind("session-1", "tenant-sessions", "session-hash-1", "csrf-hash-1", timestamp, timestamp + 3600).run();
    await env.DB.prepare(
      "INSERT INTO browser_sessions (id,tenant_id,session_hash,csrf_token_hash,created_at,expires_at,rotated_from_id) VALUES (?,?,?,?,?,?,?)",
    ).bind("session-2", "tenant-sessions", "session-hash-2", "csrf-hash-2", timestamp, timestamp + 3600, "session-1").run();

    await expect(
      env.DB.prepare(
        "INSERT INTO browser_sessions (id,tenant_id,session_hash,csrf_token_hash,created_at,expires_at) VALUES (?,?,?,?,?,?)",
      ).bind("session-3", "tenant-sessions", "session-hash-1", "csrf-hash-3", timestamp, timestamp + 3600).run(),
    ).rejects.toThrow();
  });

  it("rejects browser-session rotation lineage across tenant boundaries", async () => {
    const timestamp = Math.floor(Date.now() / 1000);
    for (const [id, email] of [["tenant-a", "a@example.com"], ["tenant-b", "b@example.com"]]) {
      await env.DB.prepare("INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)")
        .bind(id, email, timestamp, timestamp)
        .run();
    }
    await env.DB.prepare(
      "INSERT INTO browser_sessions (id,tenant_id,session_hash,csrf_token_hash,created_at,expires_at) VALUES (?,?,?,?,?,?)",
    ).bind("session-a", "tenant-a", "session-hash-a", "csrf-hash-a", timestamp, timestamp + 3600).run();

    await expect(
      env.DB.prepare(
        "INSERT INTO browser_sessions (id,tenant_id,session_hash,csrf_token_hash,created_at,expires_at,rotated_from_id) VALUES (?,?,?,?,?,?,?)",
      ).bind("session-b", "tenant-b", "session-hash-b", "csrf-hash-b", timestamp, timestamp + 3600, "session-a").run(),
    ).rejects.toThrow();
  });

  it("adds normalized entitlement_status and grace_period_ends_at to subscriptions", async () => {
    const columns = await columnNames("subscriptions");
    expect(columns).toEqual(expect.arrayContaining(["entitlement_status", "grace_period_ends_at"]));

    const timestamp = Math.floor(Date.now() / 1000);
    await env.DB.prepare("INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)")
      .bind("tenant-entitlement", "entitlement@example.com", timestamp, timestamp)
      .run();
    await expect(
      env.DB.prepare(
        "INSERT INTO subscriptions (id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit,updated_at,entitlement_status) VALUES (?,?,?,?,?,?,?,?,?,?)",
      ).bind("sub-bad-entitlement", "tenant-entitlement", "cus_1", "sub_1", "active", "price_test", "pro", 5, timestamp, "invented").run(),
    ).rejects.toThrow();
  });

  it("adds outcome and retention columns to stripe_events with an approved lifecycle constraint", async () => {
    const columns = await columnNames("stripe_events");
    expect(columns).toEqual(expect.arrayContaining(["outcome", "retention_purge_at"]));

    const timestamp = Math.floor(Date.now() / 1000);
    await env.DB.prepare("INSERT INTO stripe_events (id,event_type,received_at,outcome) VALUES (?,?,?,?)")
      .bind("evt_outcome_default", "invoice.paid", timestamp, "processed")
      .run();
    await expect(
      env.DB.prepare("INSERT INTO stripe_events (id,event_type,received_at,outcome) VALUES (?,?,?,?)")
        .bind("evt_outcome_bad", "invoice.paid", timestamp, "invented")
        .run(),
    ).rejects.toThrow();
  });

  it("enforces one subscription per tenant and adds fenced webhook ordering state", async () => {
    expect(await columnNames("subscriptions")).toEqual(expect.arrayContaining(["stripe_event_created_at"]));
    expect(await columnNames("stripe_events")).toEqual(
      expect.arrayContaining(["lease_token", "lease_expires_at", "attempt_count", "payload_sha256"]),
    );

    const timestamp = Math.floor(Date.now() / 1000);
    await env.DB.prepare("INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)")
      .bind("tenant-one-subscription", "one-subscription@example.com", timestamp, timestamp)
      .run();
    await env.DB.prepare(
      "INSERT INTO subscriptions (id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit,updated_at,entitlement_status) VALUES (?,?,?,?,?,?,?,?,?,?)",
    ).bind("sub-first", "tenant-one-subscription", "cus_first", "stripe_sub_first", "active", "price_test", "starter", 1, timestamp, "active").run();
    await expect(
      env.DB.prepare(
        "INSERT INTO subscriptions (id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit,updated_at,entitlement_status) VALUES (?,?,?,?,?,?,?,?,?,?)",
      ).bind("sub-second", "tenant-one-subscription", "cus_second", "stripe_sub_second", "active", "price_test", "starter", 1, timestamp, "active").run(),
    ).rejects.toThrow();
  });

  it("replays the full migration set idempotently without error or duplicated schema", async () => {
    await applyD1Migrations(env.DB, env.TEST_MIGRATIONS);
    await applyD1Migrations(env.DB, env.TEST_MIGRATIONS);
    const columns = await columnNames("subscriptions");
    expect(columns.filter((name) => name === "entitlement_status")).toHaveLength(1);
    expect(await tableExists("checkout_sessions")).toBe(true);
  });

  it("fails closed when legacy inserts omit normalized lifecycle columns", async () => {
    const timestamp = Math.floor(Date.now() / 1000);
    await env.DB.prepare("INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)")
      .bind("tenant-upgrade", "upgrade@example.com", timestamp, timestamp)
      .run();
    await env.DB.prepare(
      "INSERT INTO subscriptions (id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
    ).bind("sub-upgrade", "tenant-upgrade", "cus_upgrade", "sub_upgrade", "active", "price_test", "starter", 1, timestamp).run();
    await env.DB.prepare("INSERT INTO stripe_events (id,event_type,received_at) VALUES (?,?,?)")
      .bind("evt_upgrade", "invoice.paid", timestamp)
      .run();

    const subscription = await env.DB.prepare("SELECT entitlement_status, grace_period_ends_at FROM subscriptions WHERE id=?")
      .bind("sub-upgrade")
      .first<{ entitlement_status: string; grace_period_ends_at: number | null }>();
    expect(subscription?.entitlement_status).toBe("blocked");
    expect(subscription?.grace_period_ends_at).toBeNull();

    const event = await env.DB.prepare("SELECT outcome,payload_sha256 FROM stripe_events WHERE id=?")
      .bind("evt_upgrade")
      .first<{ outcome: string; payload_sha256: string }>();
    expect(event).toEqual({ outcome: "pending", payload_sha256: "" });
  });
});
