import { SELF } from "cloudflare:test";
import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";

const now = () => Math.floor(Date.now() / 1000);
const originalFetch = globalThis.fetch;

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
  entitlement?: string;
  graceEndsAt?: number | null;
}): Promise<void> {
  const timestamp = now();
  await env.DB.batch([
    env.DB.prepare("INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)")
      .bind(options.tenantId, options.email, timestamp, timestamp),
    env.DB.prepare("INSERT INTO subscriptions (id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit,current_period_end,updated_at,entitlement_status,grace_period_ends_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)")
      .bind(
        `subscription-${options.tenantId}`,
        options.tenantId,
        `customer-${options.tenantId}`,
        `stripe-sub-${options.tenantId}`,
        options.status ?? "active",
        "price_test_pro",
        options.plan ?? "pro",
        options.limit ?? 5,
        timestamp + 86400,
        timestamp,
        options.entitlement ?? ((options.status ?? "active") === "active" || (options.status ?? "active") === "trialing" ? "active" : "blocked"),
        options.graceEndsAt ?? null,
      ),
    env.DB.prepare("INSERT INTO account_credentials (id,tenant_id,credential_hash,prefix,created_at) VALUES (?,?,?,?,?)")
      .bind(`credential-${options.tenantId}`, options.tenantId, await sha256(options.accountKey), options.accountKey.slice(0, 12), timestamp),
  ]);
}

async function seedBrowserSession(): Promise<{ sessionToken: string; csrfToken: string }> {
  const timestamp = now();
  const sessionToken = "ap_session_browser_security_1234567890";
  const csrfToken = "ap_csrf_browser_security_1234567890";
  await seedTenant({ tenantId: "tenant-browser-security", email: "browser-security@example.com", accountKey: "ap_account_browser_security" });
  await env.DB.prepare(
    "INSERT INTO browser_sessions (id,tenant_id,session_hash,csrf_token_hash,created_at,expires_at,last_seen_at) VALUES (?,?,?,?,?,?,?)",
  ).bind(
    "session-browser-security",
    "tenant-browser-security",
    await sha256(sessionToken),
    await sha256(csrfToken),
    timestamp,
    timestamp + 3600,
    timestamp,
  ).run();
  return { sessionToken, csrfToken };
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

type StripeHandler = (method: string, path: string, body: string) => Response | Promise<Response>;

function installStripeMock(handler: StripeHandler): void {
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    if (!url.startsWith("https://api.stripe.com/v1")) throw new Error(`unexpected outbound fetch: ${url}`);
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.slice("https://api.stripe.com/v1".length);
    const body = typeof init?.body === "string" ? init.body : "";
    return handler(method, path, body);
  }) as typeof fetch;
}

function formMap(body: string): Record<string, string> {
  return Object.fromEntries(new URLSearchParams(body).entries());
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

async function workerFetch(input: string, init?: RequestInit): Promise<Response> {
  const response = await SELF.fetch(input, init);
  const bytes = await response.arrayBuffer();
  const body = [101, 204, 205, 304].includes(response.status) ? null : bytes;
  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}

beforeEach(async () => {
  globalThis.fetch = originalFetch;
  env.STRIPE_PORTAL_URL = "";
  const tables = [
    "heartbeat_events",
    "incidents",
    "agents",
    "enrollment_tokens",
    "onboarding_claims",
    "browser_sessions",
    "checkout_sessions",
    "account_credentials",
    "policies",
    "subscriptions",
    "tenants",
    "stripe_events",
  ];
  for (const table of tables) await env.DB.prepare(`DELETE FROM ${table}`).run();
});

describe("AgentPulse control-plane contract", () => {
  it("returns a versioned health response", async () => {
    const response = await SELF.fetch("https://agentpulse.test/health");
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ ok: true, service: "agentpulse-control-plane", version: "0.1.0", environment: "development" });
  });

  it("returns the configured Stripe-hosted portal after session, origin, and CSRF checks without calling Stripe", async () => {
    const { sessionToken, csrfToken } = await seedBrowserSession();
    env.STRIPE_PORTAL_URL = "https://billing.stripe.com/p/login/test_portal";
    installStripeMock((method, path) => {
      throw new Error(`unexpected Stripe API call: ${method} ${path}`);
    });

    const response = await workerFetch("https://agentpulse.test/v1/billing/portal", {
      method: "POST",
      headers: {
        Cookie: `ap_session=${sessionToken}`,
        "X-CSRF-Token": csrfToken,
        Origin: "https://app.agentpulse.test",
      },
    });

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      portal_url: "https://billing.stripe.com/p/login/test_portal",
    });
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

  it("rejects malformed identifiers and heartbeat summaries", async () => {
    await seedTenant({ tenantId: "tenant-a", email: "a@example.com", accountKey: "ap_account_a" });
    const enrollment = await enroll(await mintEnrollment("ap_account_a"), "   ", "host-a");
    expect(enrollment.response.status).toBe(422);

    const enrolled = await enroll(await mintEnrollment("ap_account_a"), "node-a", "host-a");
    const submit = (idempotencyKey: string, summary: Record<string, unknown>) => SELF.fetch(
      "https://agentpulse.test/v1/agents/heartbeat",
      {
        method: "POST",
        headers: { Authorization: `Bearer ${enrolled.credential}`, "Content-Type": "application/json" },
        body: JSON.stringify({ idempotency_key: idempotencyKey, observed_at: now(), summary, incidents: [] }),
      },
    );

    expect((await submit("cycle-invalid-counter", { observations: 3, breaches: -1, errors: [] })).status).toBe(422);
    expect((await submit("cycle-invalid-errors", { observations: 3, breaches: 0, errors: ["safe", 1] })).status).toBe(422);
    expect((await submit(" padded-cycle ", { observations: 3, breaches: 0, errors: [] })).status).toBe(422);
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
    const event = { id: "evt_1", type: "invoice.payment_failed", data: { object: { customer: "customer-tenant-a", subscription: "stripe-sub-tenant-a" } } };
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

  it("keeps heartbeat during failed-payment grace, then blocks after grace ends", async () => {
    await seedTenant({ tenantId: "tenant-a", email: "a@example.com", accountKey: "ap_account_a" });
    const enrolled = await enroll(await mintEnrollment("ap_account_a"), "node-1", "host-1");
    const event = { id: "evt_failed", type: "invoice.payment_failed", data: { object: { customer: "customer-tenant-a", subscription: "stripe-sub-tenant-a" } } };
    const payload = JSON.stringify(event);
    await SELF.fetch("https://agentpulse.test/v1/stripe/webhook", { method: "POST", headers: { "Stripe-Signature": await stripeSignature(payload) }, body: payload });
    const duringGrace = await SELF.fetch("https://agentpulse.test/v1/agents/heartbeat", {
      method: "POST",
      headers: { Authorization: `Bearer ${enrolled.credential}`, "Content-Type": "application/json" },
      body: JSON.stringify({ idempotency_key: "cycle-2", observed_at: now(), summary: {}, incidents: [] }),
    });
    expect(duringGrace.status).toBe(202);
    const row = await env.DB.prepare("SELECT entitlement_status,grace_period_ends_at FROM subscriptions WHERE stripe_subscription_id='stripe-sub-tenant-a'")
      .first<{ entitlement_status: string; grace_period_ends_at: number }>();
    expect(row?.entitlement_status).toBe("grace");
    await env.DB.prepare("UPDATE subscriptions SET grace_period_ends_at=?,entitlement_status='grace' WHERE stripe_subscription_id='stripe-sub-tenant-a'")
      .bind(now() - 1).run();
    const afterGrace = await SELF.fetch("https://agentpulse.test/v1/agents/heartbeat", {
      method: "POST",
      headers: { Authorization: `Bearer ${enrolled.credential}`, "Content-Type": "application/json" },
      body: JSON.stringify({ idempotency_key: "cycle-3", observed_at: now(), summary: {}, incidents: [] }),
    });
    expect(afterGrace.status).toBe(402);
  });

  it("rejects oversized bodies before parsing JSON", async () => {
    const response = await SELF.fetch("https://agentpulse.test/v1/agents/heartbeat", {
      method: "POST",
      headers: { Authorization: "Bearer invalid", "Content-Type": "application/json", "Content-Length": "70000" },
      body: "{}",
    });
    expect(response.status).toBe(413);
  });

  it("allows credentialed CORS only for the exact configured dashboard origin", async () => {
    const trusted = await SELF.fetch("https://agentpulse.test/v1/session", {
      method: "OPTIONS",
      headers: {
        Origin: "https://app.agentpulse.test",
        "Access-Control-Request-Method": "DELETE",
        "Access-Control-Request-Headers": "x-csrf-token",
      },
    });
    expect(trusted.status).toBe(204);
    expect(trusted.headers.get("Access-Control-Allow-Origin")).toBe("https://app.agentpulse.test");
    expect(trusted.headers.get("Access-Control-Allow-Credentials")).toBe("true");
    expect(trusted.headers.get("Access-Control-Allow-Methods")).toBe("GET, POST, DELETE, OPTIONS");
    expect(trusted.headers.get("Access-Control-Allow-Headers")).toBe("Accept, Content-Type, X-CSRF-Token");
    expect(trusted.headers.get("Vary")).toContain("Origin");

    for (const headers of [
      { "Access-Control-Request-Method": "DELETE" },
      { Origin: "http://localhost:8787", "Access-Control-Request-Method": "DELETE" },
      { Origin: "https://evil.example", "Access-Control-Request-Method": "DELETE" },
    ]) {
      const denied = await SELF.fetch("https://agentpulse.test/v1/session", { method: "OPTIONS", headers });
      expect(denied.status).toBe(403);
      expect(denied.headers.get("Access-Control-Allow-Origin")).toBeNull();
    }

    for (const headers of [
      { Origin: "https://app.agentpulse.test", "Access-Control-Request-Method": "PATCH" },
      { Origin: "https://app.agentpulse.test", "Access-Control-Request-Method": "DELETE", "Access-Control-Request-Headers": "authorization" },
    ]) {
      const denied = await SELF.fetch("https://agentpulse.test/v1/session", { method: "OPTIONS", headers });
      expect(denied.status).toBe(403);
      expect(denied.headers.get("Access-Control-Allow-Origin")).toBe("https://app.agentpulse.test");
    }

    for (const origin of [undefined, "http://localhost:8787", "https://evil.example"]) {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (origin) headers.Origin = origin;
      const denied = await SELF.fetch("https://agentpulse.test/v1/onboarding/claim", {
        method: "POST",
        headers,
        body: JSON.stringify({ claim_nonce: "ap_claim_unknown_12345678901234567890" }),
      });
      expect(denied.status).toBe(403);
    }
  });

  it("adds exact-origin credentialed CORS headers to success and error responses", async () => {
    const success = await SELF.fetch("https://agentpulse.test/health", {
      headers: { Origin: "https://app.agentpulse.test" },
    });
    expect(success.status).toBe(200);
    expect(success.headers.get("Access-Control-Allow-Origin")).toBe("https://app.agentpulse.test");
    expect(success.headers.get("Access-Control-Allow-Credentials")).toBe("true");
    expect(success.headers.get("Vary")).toContain("Origin");

    const denied = await SELF.fetch("https://agentpulse.test/v1/account", {
      headers: { Origin: "https://app.agentpulse.test" },
    });
    expect(denied.status).toBe(401);
    expect(denied.headers.get("Access-Control-Allow-Origin")).toBe("https://app.agentpulse.test");
    expect(denied.headers.get("Vary")).toContain("Origin");

    const untrusted = await SELF.fetch("https://agentpulse.test/health", {
      headers: { Origin: "https://evil.example" },
    });
    expect(untrusted.status).toBe(200);
    expect(untrusted.headers.get("Access-Control-Allow-Origin")).toBeNull();
    expect(untrusted.headers.get("Vary")).toContain("Origin");
  });

  it("rotates CSRF after reload and revokes a browser session only from the exact app origin", async () => {
    const { sessionToken, csrfToken } = await seedBrowserSession();
    const cookie = `ap_session=${sessionToken}`;

    for (const origin of [undefined, "http://localhost:8787", "https://evil.example"]) {
      const headers: Record<string, string> = { Cookie: cookie };
      if (origin) headers.Origin = origin;
      const denied = await SELF.fetch("https://agentpulse.test/v1/session/csrf", { method: "POST", headers });
      expect(denied.status).toBe(403);
    }

    const refreshed = await SELF.fetch("https://agentpulse.test/v1/session/csrf", {
      method: "POST",
      headers: { Cookie: cookie, Origin: "https://app.agentpulse.test" },
    });
    expect(refreshed.status).toBe(200);
    expect(refreshed.headers.get("Cache-Control")).toBe("no-store");
    const refreshedBody = await refreshed.json<{ csrf_token: string }>();
    expect(refreshedBody.csrf_token).toMatch(/^ap_csrf_[A-Za-z0-9_-]{40,}$/);
    expect(refreshedBody.csrf_token).not.toBe(csrfToken);
    expect(await env.DB.prepare("SELECT csrf_token_hash FROM browser_sessions WHERE id='session-browser-security'").first())
      .toMatchObject({ csrf_token_hash: await sha256(refreshedBody.csrf_token) });

    const oldToken = await SELF.fetch("https://agentpulse.test/v1/session", {
      method: "DELETE",
      headers: { Cookie: cookie, Origin: "https://app.agentpulse.test", "X-CSRF-Token": csrfToken },
    });
    expect(oldToken.status).toBe(403);

    const noOrigin = await SELF.fetch("https://agentpulse.test/v1/session", {
      method: "DELETE",
      headers: { Cookie: cookie, "X-CSRF-Token": refreshedBody.csrf_token },
    });
    expect(noOrigin.status).toBe(403);
    expect(await env.DB.prepare("SELECT revoked_at FROM browser_sessions WHERE id='session-browser-security'").first())
      .toMatchObject({ revoked_at: null });

    const logout = await SELF.fetch("https://agentpulse.test/v1/session", {
      method: "DELETE",
      headers: { Cookie: cookie, Origin: "https://app.agentpulse.test", "X-CSRF-Token": refreshedBody.csrf_token },
    });
    expect(logout.status).toBe(204);
    const setCookie = logout.headers.get("Set-Cookie") ?? "";
    expect(setCookie).toContain("ap_session=");
    expect(setCookie).toContain("HttpOnly");
    expect(setCookie).toContain("Path=/");
    expect(setCookie).toContain("SameSite=Lax");
    expect(setCookie).toContain("Max-Age=0");
    expect(setCookie).not.toContain("Secure");

    const afterLogout = await SELF.fetch("https://agentpulse.test/v1/account", {
      headers: { Cookie: cookie, Origin: "https://app.agentpulse.test" },
    });
    expect(afterLogout.status).toBe(401);
  });

  it("blocks browser-session fleet reads when hosted entitlement is inactive", async () => {
    const timestamp = now();
    const sessionToken = "ap_session_blocked_fleet_123456";
    const csrfToken = "ap_csrf_blocked_fleet_12345678";
    await env.DB.batch([
      env.DB.prepare("INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)")
        .bind("tenant-blocked-fleet", "blocked-fleet@example.com", timestamp, timestamp),
      env.DB.prepare(
        "INSERT INTO subscriptions (id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit,updated_at,entitlement_status,grace_period_ends_at,stripe_event_created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
      ).bind(
        "sub-blocked-fleet",
        "tenant-blocked-fleet",
        "cus_blocked_fleet",
        "sub_blocked_fleet",
        "canceled",
        "price_test_starter",
        "starter",
        1,
        timestamp,
        "blocked",
        null,
        timestamp,
      ),
      env.DB.prepare(
        "INSERT INTO browser_sessions (id,tenant_id,session_hash,csrf_token_hash,created_at,last_seen_at,expires_at) VALUES (?,?,?,?,?,?,?)",
      ).bind(
        "session-blocked-fleet",
        "tenant-blocked-fleet",
        await sha256(sessionToken),
        await sha256(csrfToken),
        timestamp,
        timestamp,
        timestamp + 3600,
      ),
      env.DB.prepare(
        "INSERT INTO agents (id,tenant_id,agent_key,hostname,credential_hash,prefix,local_policy_ceiling,enrolled_at) VALUES (?,?,?,?,?,?,?,?)",
      ).bind(
        "agent-blocked-fleet",
        "tenant-blocked-fleet",
        "host-blocked",
        "blocked.example",
        await sha256("ap_agent_blocked_fleet"),
        "ap_agent_blo",
        "alert",
        timestamp,
      ),
    ]);
    const response = await SELF.fetch("https://agentpulse.test/v1/fleet", {
      headers: { Cookie: `ap_session=${sessionToken}` },
    });
    expect(response.status).toBe(402);
    expect(await response.json()).toMatchObject({ error: { code: "subscription_inactive" } });
  });

  it("does not renew an expired grace window from an equal-created invoice.payment_failed", async () => {
    const timestamp = now();
    const expiredGrace = timestamp - 60;
    await env.DB.batch([
      env.DB.prepare("INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)")
        .bind("tenant-expired-grace", "expired-grace@example.com", timestamp, timestamp),
      env.DB.prepare(
        "INSERT INTO subscriptions (id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit,updated_at,entitlement_status,grace_period_ends_at,stripe_event_created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
      ).bind(
        "sub-expired-grace",
        "tenant-expired-grace",
        "cus_expired_grace",
        "sub_expired_grace",
        "past_due",
        "price_test_starter",
        "starter",
        1,
        timestamp,
        "grace",
        expiredGrace,
        timestamp + 10,
      ),
    ]);
    const payload = JSON.stringify({
      id: "evt_expired_grace_renew", type: "invoice.payment_failed", created: timestamp + 10,
      data: { object: { customer: "cus_expired_grace", subscription: "sub_expired_grace" } },
    });
    const response = await SELF.fetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST", headers: { "Stripe-Signature": await stripeSignature(payload) }, body: payload,
    });
    expect(response.status).toBe(200);
    const row = await env.DB.prepare(
      "SELECT entitlement_status,grace_period_ends_at,stripe_event_created_at FROM subscriptions WHERE id='sub-expired-grace'",
    ).first<{ entitlement_status: string; grace_period_ends_at: number | null; stripe_event_created_at: number }>();
    expect(row).toMatchObject({
      entitlement_status: "grace",
      grace_period_ends_at: expiredGrace,
      stripe_event_created_at: timestamp + 10,
    });
  });

  it("does not extend an active grace window from a later distinct invoice.payment_failed", async () => {
    const timestamp = now();
    const originalGrace = timestamp + 120;
    await env.DB.batch([
      env.DB.prepare("INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)")
        .bind("tenant-active-grace", "active-grace@example.com", timestamp, timestamp),
      env.DB.prepare(
        "INSERT INTO subscriptions (id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit,updated_at,entitlement_status,grace_period_ends_at,stripe_event_created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
      ).bind(
        "sub-active-grace",
        "tenant-active-grace",
        "cus_active_grace",
        "sub_active_grace",
        "past_due",
        "price_test_starter",
        "starter",
        1,
        timestamp,
        "grace",
        originalGrace,
        timestamp,
      ),
    ]);
    const payload = JSON.stringify({
      id: "evt_active_grace_retry", type: "invoice.payment_failed", created: timestamp + 60,
      data: { object: { customer: "cus_active_grace", subscription: "sub_active_grace" } },
    });
    const response = await SELF.fetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST", headers: { "Stripe-Signature": await stripeSignature(payload) }, body: payload,
    });
    expect(response.status).toBe(200);
    const row = await env.DB.prepare(
      "SELECT entitlement_status,grace_period_ends_at,stripe_event_created_at FROM subscriptions WHERE id='sub-active-grace'",
    ).first<{ entitlement_status: string; grace_period_ends_at: number | null; stripe_event_created_at: number }>();
    expect(row).toMatchObject({
      entitlement_status: "grace",
      grace_period_ends_at: originalGrace,
      stripe_event_created_at: timestamp + 60,
    });
  });

  it("claims a paid checkout once, issues HttpOnly session cookie + CSRF, and rejects replay", async () => {
    let claimNonce = "";
    installStripeMock((method, path, body) => {
      if (method === "POST" && path === "/checkout/sessions") {
        const form = formMap(body);
        const successUrl = form.success_url;
        expect(successUrl).toBeTruthy();
        const success = new URL(successUrl!);
        claimNonce = success.searchParams.get("claim_nonce") ?? "";
        return jsonResponse({
          id: "cs_test_claim",
          livemode: false,
            url: "https://checkout.stripe.com/c/pay/cs_test_claim",
          expires_at: now() + 1800,
        });
      }
      if (method === "GET" && path === "/checkout/sessions/cs_test_claim") {
        return jsonResponse({
          id: "cs_test_claim",
          status: "complete",
          payment_status: "paid",
          customer: "cus_1",
          subscription: "sub_1",
          customer_details: { email: "owner@example.com" },
        });
      }
      if (method === "GET" && path === "/subscriptions/sub_1") {
        return jsonResponse({ id: "sub_1", customer: "cus_1", status: "active", current_period_end: now() + 86400, items: { data: [{ price: { id: "price_test_starter" } }] } });
      }
      if (method === "POST" && path === "/billing_portal/sessions") {
        const form = formMap(body);
        expect(form.customer).toBe("cus_1");
        return jsonResponse({ url: "https://billing.stripe.com/p/session/test" });
      }
      throw new Error(`unexpected stripe ${method} ${path} ${body}`);
    });

    const checkout = await workerFetch("https://agentpulse.test/v1/billing/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan: "starter" }),
    });
    expect(checkout.status).toBe(201);
    expect(claimNonce.length).toBeGreaterThan(16);

    const claim = await workerFetch("https://agentpulse.test/v1/onboarding/claim", {
      method: "POST",
      headers: { "Content-Type": "application/json", Origin: "https://app.agentpulse.test" },
      body: JSON.stringify({ claim_nonce: claimNonce }),
    });
    expect(claim.status).toBe(200);
    const setCookie = claim.headers.get("Set-Cookie") ?? "";
    expect(setCookie).toContain("ap_session=");
    expect(setCookie).toContain("HttpOnly");
    expect(setCookie).toContain("SameSite=Lax");
    expect(setCookie).not.toContain("ap_account_");
    const claimed = await claim.json() as { csrf_token: string; account: { plan: string; entitlement_status: string; agent_limit: number; email: string } };
    expect(claimed.csrf_token.length).toBeGreaterThanOrEqual(16);
    expect(claimed.account).toMatchObject({
      plan: "starter",
      entitlement_status: "active",
      agent_limit: 1,
      email: "owner@example.com",
    });
    expect(JSON.stringify(claimed)).not.toContain("ap_account_");
    expect(JSON.stringify(claimed)).not.toContain(claimNonce);

    const replay = await workerFetch("https://agentpulse.test/v1/onboarding/claim", {
      method: "POST",
      headers: { "Content-Type": "application/json", Origin: "https://app.agentpulse.test" },
      body: JSON.stringify({ claim_nonce: claimNonce }),
    });
    expect(replay.status).toBe(409);

    const sessionCookie = setCookie.split(";")[0] ?? "";
    const account = await workerFetch("https://agentpulse.test/v1/account", {
      headers: { Cookie: sessionCookie },
    });
    expect(account.status).toBe(200);
    expect(await account.json()).toMatchObject({ plan: "starter", entitlement_status: "active", agent_limit: 1 });

    const enrollment = await workerFetch("https://agentpulse.test/v1/browser/enrollment-tokens", {
      method: "POST",
      headers: {
        Cookie: sessionCookie,
        "Content-Type": "application/json",
        "X-CSRF-Token": claimed.csrf_token,
        Origin: "https://app.agentpulse.test",
      },
      body: JSON.stringify({ ttl_seconds: 300 }),
    });
    expect(enrollment.status).toBe(201);
    expect(await enrollment.json()).toMatchObject({ enrollment_token: expect.stringMatching(/^ap_enroll_/) });

    const badCsrf = await workerFetch("https://agentpulse.test/v1/billing/portal", {
      method: "POST",
      headers: { Cookie: sessionCookie, "X-CSRF-Token": "not-the-token", Origin: "https://app.agentpulse.test" },
    });
    expect(badCsrf.status).toBe(403);

    const portal = await workerFetch("https://agentpulse.test/v1/billing/portal", {
      method: "POST",
      headers: {
        Cookie: sessionCookie,
        "X-CSRF-Token": claimed.csrf_token,
        Origin: "https://app.agentpulse.test",
      },
    });
    expect(portal.status).toBe(200);
    expect(await portal.json()).toEqual({ portal_url: "https://billing.stripe.com/p/session/test" });

    const logout = await workerFetch("https://agentpulse.test/v1/session", {
      method: "DELETE",
      headers: {
        Cookie: sessionCookie,
        "X-CSRF-Token": claimed.csrf_token,
        Origin: "https://app.agentpulse.test",
      },
    });
    expect(logout.status).toBe(204);
    const afterLogout = await workerFetch("https://agentpulse.test/v1/account", {
      headers: { Cookie: sessionCookie },
    });
    expect(afterLogout.status).toBe(401);
  });

  it("processes subscription lifecycle events idempotently and never grants unknown prices", async () => {
    await env.DB.batch([
      env.DB.prepare("INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)")
        .bind("tenant-x", "x@example.com", now(), now()),
      env.DB.prepare(
        "INSERT INTO subscriptions (id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit,current_period_end,updated_at,entitlement_status,grace_period_ends_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
      ).bind("subrow", "tenant-x", "cus_x", "sub_x", "active", "price_test_pro", "pro", 5, now() + 1000, now(), "active", null),
    ]);

    installStripeMock((method, path) => {
      if (method === "GET" && path === "/customers/cus_x") return jsonResponse({ id: "cus_x", email: "x@example.com" });
      throw new Error(`unexpected stripe ${method} ${path}`);
    });

    const updated = {
      id: "evt_sub_updated",
      type: "customer.subscription.updated",
      data: {
        object: {
          id: "sub_x",
          customer: "cus_x",
          status: "active",
          current_period_end: now() + 2000,
          metadata: { plan: "business" },
          items: { data: [{ price: { id: "price_test_business" } }] },
        },
      },
    };
    const payload = JSON.stringify(updated);
    const first = await workerFetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST",
      headers: { "Stripe-Signature": await stripeSignature(payload) },
      body: payload,
    });
    const second = await workerFetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST",
      headers: { "Stripe-Signature": await stripeSignature(payload) },
      body: payload,
    });
    expect(first.status).toBe(200);
    expect(await second.json()).toMatchObject({ duplicate: true });
    const row = await env.DB.prepare("SELECT plan,agent_limit,entitlement_status FROM subscriptions WHERE stripe_subscription_id='sub_x'")
      .first<{ plan: string; agent_limit: number; entitlement_status: string }>();
    expect(row).toEqual({ plan: "business", agent_limit: 20, entitlement_status: "active" });

    const unknown = {
      id: "evt_unknown_price",
      type: "customer.subscription.updated",
      data: {
        object: {
          id: "sub_x",
          customer: "cus_x",
          status: "active",
          current_period_end: now() + 2000,
          items: { data: [{ price: { id: "price_unknown" } }] },
        },
      },
    };
    const unknownPayload = JSON.stringify(unknown);
    expect((await workerFetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST",
      headers: { "Stripe-Signature": await stripeSignature(unknownPayload) },
      body: unknownPayload,
    })).status).toBe(200);
    const blocked = await env.DB.prepare("SELECT entitlement_status FROM subscriptions WHERE stripe_subscription_id='sub_x'")
      .first<{ entitlement_status: string }>();
    expect(blocked?.entitlement_status).toBe("blocked");
  });

  it("recovers hosted entitlement after invoice.paid", async () => {
    await env.DB.batch([
      env.DB.prepare("INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)")
        .bind("tenant-y", "y@example.com", now(), now()),
      env.DB.prepare(
        "INSERT INTO subscriptions (id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit,current_period_end,updated_at,entitlement_status,grace_period_ends_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
      ).bind("subrow-y", "tenant-y", "cus_y", "sub_y", "past_due", "price_test_starter", "starter", 1, now() + 1000, now(), "grace", now() + 1000),
      env.DB.prepare("INSERT INTO account_credentials (id,tenant_id,credential_hash,prefix,created_at) VALUES (?,?,?,?,?)")
        .bind("cred-y", "tenant-y", await sha256("ap_account_y"), "ap_account_y", now()),
    ]);
    const paid = {
      id: "evt_paid",
      type: "invoice.paid",
      data: { object: { customer: "cus_y", subscription: "sub_y" } },
    };
    const payload = JSON.stringify(paid);
    expect((await workerFetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST",
      headers: { "Stripe-Signature": await stripeSignature(payload) },
      body: payload,
    })).status).toBe(200);
    const row = await env.DB.prepare("SELECT status,entitlement_status,grace_period_ends_at FROM subscriptions WHERE stripe_subscription_id='sub_y'")
      .first<{ status: string; entitlement_status: string; grace_period_ends_at: number | null }>();
    expect(row).toEqual({ status: "active", entitlement_status: "active", grace_period_ends_at: null });
  });

  it("rejects a changed payload when Stripe retries the same event ID and type", async () => {
    const timestamp = now();
    const failedPayload = JSON.stringify({
      id: "evt_payload_immutable", type: "customer.subscription.created", created: timestamp,
      data: { object: { id: "sub_payload_original", status: "active" } },
    });
    const first = await workerFetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST", headers: { "Stripe-Signature": await stripeSignature(failedPayload) }, body: failedPayload,
    });
    expect(first.status).toBe(422);
    expect(await env.DB.prepare("SELECT outcome,payload_sha256,attempt_count FROM stripe_events WHERE id='evt_payload_immutable'").first())
      .toMatchObject({ outcome: "failed", attempt_count: 1 });

    const changedPayload = JSON.stringify({
      id: "evt_payload_immutable", type: "customer.subscription.created", created: timestamp,
      data: { object: {
        id: "sub_payload_changed", customer: "cus_payload_changed", status: "active",
        current_period_end: timestamp + 1000, metadata: { plan: "starter" },
        items: { data: [{ price: { id: "price_test_starter" } }] },
      } },
    });
    const retry = await workerFetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST", headers: { "Stripe-Signature": await stripeSignature(changedPayload) }, body: changedPayload,
    });
    expect(retry.status).toBe(409);
    expect(await env.DB.prepare("SELECT outcome,attempt_count FROM stripe_events WHERE id='evt_payload_immutable'").first())
      .toMatchObject({ outcome: "failed", attempt_count: 1 });
    expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM subscriptions WHERE stripe_subscription_id='sub_payload_changed'").first())
      .toMatchObject({ count: 0 });
  });

  it("binds the first signed body for legacy terminal events and rejects later payload changes", async () => {
    const timestamp = now();
    await env.DB.prepare(
      "INSERT INTO stripe_events (id,event_type,received_at,processed_at,outcome,attempt_count,payload_sha256) VALUES (?,?,?,?,?,?,?)",
    ).bind("evt_legacy_terminal", "customer.subscription.updated", timestamp - 100, timestamp - 90, "processed", 0, "").run();

    const firstBody = JSON.stringify({
      id: "evt_legacy_terminal", type: "customer.subscription.updated", created: timestamp,
      data: { object: { id: "sub_legacy_first", customer: "cus_legacy_first", status: "active" } },
    });
    const first = await workerFetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST", headers: { "Stripe-Signature": await stripeSignature(firstBody) }, body: firstBody,
    });
    expect(first.status).toBe(200);
    expect(await first.json()).toMatchObject({ ok: true, duplicate: true });
    const bound = await env.DB.prepare("SELECT outcome,payload_sha256,attempt_count FROM stripe_events WHERE id='evt_legacy_terminal'").first<{
      outcome: string; payload_sha256: string; attempt_count: number;
    }>();
    expect(bound).toMatchObject({ outcome: "processed", attempt_count: 0 });
    expect(bound?.payload_sha256).toHaveLength(64);

    const changedBody = JSON.stringify({
      id: "evt_legacy_terminal", type: "customer.subscription.updated", created: timestamp,
      data: { object: {
        id: "sub_legacy_changed", customer: "cus_legacy_changed", status: "active",
        current_period_end: timestamp + 1000, metadata: { plan: "business" },
        items: { data: [{ price: { id: "price_test_business" } }] },
      } },
    });
    const changed = await workerFetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST", headers: { "Stripe-Signature": await stripeSignature(changedBody) }, body: changedBody,
    });
    expect(changed.status).toBe(409);
    expect(await env.DB.prepare("SELECT outcome,payload_sha256,attempt_count FROM stripe_events WHERE id='evt_legacy_terminal'").first())
      .toMatchObject({ outcome: "processed", payload_sha256: bound?.payload_sha256, attempt_count: 0 });
    expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM subscriptions WHERE stripe_subscription_id='sub_legacy_changed'").first())
      .toMatchObject({ count: 0 });
  });

});
