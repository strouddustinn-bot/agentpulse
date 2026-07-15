import { SELF } from "cloudflare:test";
import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";

const now = () => Math.floor(Date.now() / 1000);

async function sha256(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function seedTenant(options: {
  tenantId: string;
  email: string;
  accountKey: string;
  status?: string;
  plan?: string;
  limit?: number;
}): Promise<void> {
  const timestamp = now();
  await env.DB.batch([
    env.DB.prepare("INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)")
      .bind(options.tenantId, options.email, timestamp, timestamp),
    env.DB.prepare("INSERT INTO subscriptions (id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit,current_period_end,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)")
      .bind(`subscription-${options.tenantId}`, options.tenantId, `customer-${options.tenantId}`, `stripe-sub-${options.tenantId}`, options.status ?? "active", "price_test", options.plan ?? "pro", options.limit ?? 5, timestamp + 86400, timestamp),
    env.DB.prepare("INSERT INTO account_credentials (id,tenant_id,credential_hash,prefix,created_at) VALUES (?,?,?,?,?)")
      .bind(`credential-${options.tenantId}`, options.tenantId, await sha256(options.accountKey), options.accountKey.slice(0, 12), timestamp),
  ]);
}

async function mintEnrollment(accountKey: string): Promise<string> {
  const response = await SELF.fetch("https://agentpulse.test/v1/enrollment-tokens", {
    method: "POST",
    headers: { Authorization: `Bearer ${accountKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({ ttl_seconds: 300 }),
  });
  expect(response.status).toBe(201);
  const body = await response.json<{ enrollment_token: string }>();
  return body.enrollment_token;
}

async function enroll(enrollmentToken: string, agentKey: string, hostname: string, localCeiling = "alert"): Promise<{ response: Response; credential?: string }> {
  const response = await SELF.fetch("https://agentpulse.test/v1/agents/enroll", {
    method: "POST",
    headers: { Authorization: `Bearer ${enrollmentToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ agent_key: agentKey, hostname, local_policy_ceiling: localCeiling }),
  });
  if (!response.ok) return { response };
  const body = await response.json<{ agent_credential: string }>();
  return { response, credential: body.agent_credential };
}

async function stripeSignature(payload: string, timestamp = now()): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode("whsec_test_agentpulse"),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(`${timestamp}.${payload}`));
  const hex = [...new Uint8Array(signature)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return `t=${timestamp},v1=${hex}`;
}

beforeEach(async () => {
  const tables = ["heartbeat_events", "incidents", "agents", "enrollment_tokens", "onboarding_claims", "account_credentials", "policies", "subscriptions", "tenants", "stripe_events"];
  for (const table of tables) await env.DB.prepare(`DELETE FROM ${table}`).run();
});

describe("AgentPulse control-plane contract", () => {
  it("returns a versioned health response", async () => {
    const response = await SELF.fetch("https://agentpulse.test/health");
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ ok: true, service: "agentpulse-control-plane", version: "0.1.0", environment: "development" });
  });

  it("isolates fleet reads by the authenticated tenant", async () => {
    await seedTenant({ tenantId: "tenant-a", email: "a@example.com", accountKey: "ap_account_a" });
    await seedTenant({ tenantId: "tenant-b", email: "b@example.com", accountKey: "ap_account_b" });
    const a = await enroll(await mintEnrollment("ap_account_a"), "node-a", "host-a");
    const b = await enroll(await mintEnrollment("ap_account_b"), "node-b", "host-b");
    expect(a.response.status).toBe(201);
    expect(b.response.status).toBe(201);

    const response = await SELF.fetch("https://agentpulse.test/v1/fleet", { headers: { Authorization: "Bearer ap_account_a" } });
    expect(response.status).toBe(200);
    const body = await response.json<{ agents: Array<{ agent_key: string }> }>();
    expect(body.agents.map((agent) => agent.agent_key)).toEqual(["node-a"]);
  });

  it("materializes heartbeat incidents and exposes them in tenant-scoped fleet reads", async () => {
    await seedTenant({ tenantId: "tenant-a", email: "a@example.com", accountKey: "ap_account_a" });
    await seedTenant({ tenantId: "tenant-b", email: "b@example.com", accountKey: "ap_account_b" });
    const enrolledA = await enroll(await mintEnrollment("ap_account_a"), "node-a", "host-a");
    const enrolledB = await enroll(await mintEnrollment("ap_account_b"), "node-b", "host-b");
    const send = (credential: string, idempotency_key: string, fingerprint: string) => SELF.fetch("https://agentpulse.test/v1/agents/heartbeat", {
      method: "POST",
      headers: { Authorization: `Bearer ${credential}`, "Content-Type": "application/json" },
      body: JSON.stringify({ idempotency_key, observed_at: now(), summary: {}, incidents: [{ fingerprint, kind: "disk", status: "open", severity: "critical", detail: "disk pressure" }] }),
    });
    expect((await send(enrolledA.credential ?? "", "cycle-a", "disk:/var")).status).toBe(202);
    expect((await send(enrolledA.credential ?? "", "cycle-a", "disk:/var")).status).toBe(200);
    expect((await send(enrolledB.credential ?? "", "cycle-b", "disk:/tmp")).status).toBe(202);
    const count = await env.DB.prepare("SELECT COUNT(*) AS count FROM incidents WHERE tenant_id='tenant-a'").first<{ count: number }>();
    expect(count?.count).toBe(1);
    const fleet = await SELF.fetch("https://agentpulse.test/v1/fleet", { headers: { Authorization: "Bearer ap_account_a" } });
    expect(fleet.status).toBe(200);
    const body = await fleet.json<{ agents: Array<{ agent_key: string; incidents: Array<{ fingerprint: string; severity: string }> }> }>();
    expect(body.agents).toHaveLength(1);
    expect(body.agents[0]?.incidents).toEqual([expect.objectContaining({ fingerprint: "disk:/var", severity: "critical" })]);
  });

  it("bounds and fails closed on malformed heartbeat incidents", async () => {
    await seedTenant({ tenantId: "tenant-a", email: "a@example.com", accountKey: "ap_account_a" });
    const enrolled = await enroll(await mintEnrollment("ap_account_a"), "node-a", "host-a");
    const response = await SELF.fetch("https://agentpulse.test/v1/agents/heartbeat", {
      method: "POST",
      headers: { Authorization: `Bearer ${enrolled.credential}`, "Content-Type": "application/json" },
      body: JSON.stringify({ idempotency_key: "cycle-invalid", observed_at: now(), summary: {}, incidents: [null] }),
    });
    expect(response.status).toBe(422);
  });

  it("mints an expiring one-time enrollment token for an active account", async () => {
    await seedTenant({ tenantId: "tenant-a", email: "a@example.com", accountKey: "ap_account_a" });
    const response = await SELF.fetch("https://agentpulse.test/v1/enrollment-tokens", {
      method: "POST",
      headers: { Authorization: "Bearer ap_account_a", "Content-Type": "application/json" },
      body: JSON.stringify({ ttl_seconds: 300 }),
    });
    expect(response.status).toBe(201);
    const body = await response.json<{ enrollment_token: string; expires_at: number }>();
    expect(body.enrollment_token).toMatch(/^ap_enroll_/);
    expect(body.expires_at).toBeGreaterThan(now());
    const row = await env.DB.prepare("SELECT token_hash FROM enrollment_tokens").first<{ token_hash: string }>();
    expect(row?.token_hash).toBe(await sha256(body.enrollment_token));
    expect(JSON.stringify(row)).not.toContain(body.enrollment_token);
  });

  it("atomically exchanges enrollment for one unique agent credential", async () => {
    await seedTenant({ tenantId: "tenant-a", email: "a@example.com", accountKey: "ap_account_a" });
    const token = await mintEnrollment("ap_account_a");
    const first = await enroll(token, "node-1", "host-1", "ask");
    expect(first.response.status).toBe(201);
    expect(first.credential).toMatch(/^ap_agent_/);
    const reused = await enroll(token, "node-2", "host-2");
    expect(reused.response.status).toBe(409);
    const row = await env.DB.prepare("SELECT credential_hash,local_policy_ceiling FROM agents WHERE agent_key='node-1'").first<{ credential_hash: string; local_policy_ceiling: string }>();
    expect(row?.credential_hash).toBe(await sha256(first.credential ?? ""));
    expect(row?.local_policy_ceiling).toBe("ask");
  });

  it("rejects expired enrollment tokens", async () => {
    await seedTenant({ tenantId: "tenant-a", email: "a@example.com", accountKey: "ap_account_a" });
    const token = "ap_enroll_expired";
    await env.DB.prepare("INSERT INTO enrollment_tokens (id,tenant_id,token_hash,created_by_credential_id,created_at,expires_at) VALUES (?,?,?,?,?,?)")
      .bind("expired", "tenant-a", await sha256(token), "credential-tenant-a", now() - 600, now() - 1).run();
    expect((await enroll(token, "node-1", "host-1")).response.status).toBe(401);
  });

  it("accepts bounded idempotent heartbeats only from the enrolled agent", async () => {
    await seedTenant({ tenantId: "tenant-a", email: "a@example.com", accountKey: "ap_account_a" });
    const enrolled = await enroll(await mintEnrollment("ap_account_a"), "node-1", "host-1");
    const heartbeat = { idempotency_key: "cycle-1", observed_at: now(), summary: { observations: 3, breaches: 0 }, incidents: [] };
    const send = (credential: string) => SELF.fetch("https://agentpulse.test/v1/agents/heartbeat", {
      method: "POST",
      headers: { Authorization: `Bearer ${credential}`, "Content-Type": "application/json" },
      body: JSON.stringify(heartbeat),
    });
    expect((await send(enrolled.credential ?? "")).status).toBe(202);
    expect((await send(enrolled.credential ?? "")).status).toBe(200);
    expect((await send("ap_agent_invalid")).status).toBe(401);
    const count = await env.DB.prepare("SELECT COUNT(*) AS count FROM heartbeat_events").first<{ count: number }>();
    expect(count?.count).toBe(1);
  });

  it("fails closed for inactive subscriptions", async () => {
    await seedTenant({ tenantId: "tenant-a", email: "a@example.com", accountKey: "ap_account_a", status: "past_due" });
    const mint = await SELF.fetch("https://agentpulse.test/v1/enrollment-tokens", {
      method: "POST",
      headers: { Authorization: "Bearer ap_account_a", "Content-Type": "application/json" },
      body: JSON.stringify({ ttl_seconds: 300 }),
    });
    expect(mint.status).toBe(402);
  });

  it("never returns policy authority above the agent local ceiling", async () => {
    await seedTenant({ tenantId: "tenant-a", email: "a@example.com", accountKey: "ap_account_a" });
    await env.DB.prepare("INSERT INTO policies (id,tenant_id,version,document,created_at) VALUES (?,?,?,?,?)")
      .bind("policy-a", "tenant-a", 1, JSON.stringify({ checks: { disk: { mode: "auto" }, service: { mode: "auto" } } }), now()).run();
    const enrolled = await enroll(await mintEnrollment("ap_account_a"), "node-1", "host-1", "ask");
    const response = await SELF.fetch("https://agentpulse.test/v1/agents/policy", { headers: { Authorization: `Bearer ${enrolled.credential}` } });
    expect(response.status).toBe(200);
    const body = await response.json<{ policy: { checks: Record<string, { mode: string }> } }>();
    expect(body.policy.checks.disk?.mode).toBe("ask");
    expect(body.policy.checks.service?.mode).toBe("ask");
  });

  it("verifies Stripe signatures and records event IDs idempotently", async () => {
    const event = { id: "evt_1", type: "invoice.payment_failed", data: { object: { subscription: "stripe-sub-tenant-a" } } };
    const payload = JSON.stringify(event);
    const invalid = await SELF.fetch("https://agentpulse.test/v1/stripe/webhook", { method: "POST", headers: { "Stripe-Signature": "t=1,v1=bad" }, body: payload });
    expect(invalid.status).toBe(400);
    const signature = await stripeSignature(payload);
    const first = await SELF.fetch("https://agentpulse.test/v1/stripe/webhook", { method: "POST", headers: { "Stripe-Signature": signature }, body: payload });
    const second = await SELF.fetch("https://agentpulse.test/v1/stripe/webhook", { method: "POST", headers: { "Stripe-Signature": signature }, body: payload });
    expect(first.status).toBe(200);
    expect(await second.json()).toMatchObject({ ok: true, duplicate: true });
    const count = await env.DB.prepare("SELECT COUNT(*) AS count FROM stripe_events WHERE id='evt_1'").first<{ count: number }>();
    expect(count?.count).toBe(1);
  });

  it("disables agent heartbeat after failed payment", async () => {
    await seedTenant({ tenantId: "tenant-a", email: "a@example.com", accountKey: "ap_account_a" });
    const enrolled = await enroll(await mintEnrollment("ap_account_a"), "node-1", "host-1");
    const event = { id: "evt_failed", type: "invoice.payment_failed", data: { object: { subscription: "stripe-sub-tenant-a" } } };
    const payload = JSON.stringify(event);
    await SELF.fetch("https://agentpulse.test/v1/stripe/webhook", { method: "POST", headers: { "Stripe-Signature": await stripeSignature(payload) }, body: payload });
    const response = await SELF.fetch("https://agentpulse.test/v1/agents/heartbeat", {
      method: "POST",
      headers: { Authorization: `Bearer ${enrolled.credential}`, "Content-Type": "application/json" },
      body: JSON.stringify({ idempotency_key: "cycle-2", observed_at: now(), summary: {}, incidents: [] }),
    });
    expect(response.status).toBe(402);
  });

  it("rejects oversized bodies before parsing JSON", async () => {
    const response = await SELF.fetch("https://agentpulse.test/v1/agents/heartbeat", {
      method: "POST",
      headers: { Authorization: "Bearer invalid", "Content-Type": "application/json", "Content-Length": "70000" },
      body: "{}",
    });
    expect(response.status).toBe(413);
  });
});
