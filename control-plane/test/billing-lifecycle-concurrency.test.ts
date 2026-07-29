import { SELF } from "cloudflare:test";
import { env } from "cloudflare:workers";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

const now = () => Math.floor(Date.now() / 1000);
const originalFetch = globalThis.fetch;

async function sha256(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
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
    if (!url.startsWith("https://api.stripe.com/v1")) {
      throw new Error(`unexpected outbound fetch: ${url}`);
    }
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.slice("https://api.stripe.com/v1".length);
    const body = typeof init?.body === "string" ? init.body : "";
    return handler(method, path, body);
  }) as typeof fetch;
}

function formMap(body: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of new URLSearchParams(body).entries()) out[key] = value;
  return out;
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

beforeEach(() => {
  // The Workers Vitest pool provides isolated D1 storage for each test.
  globalThis.fetch = originalFetch;
});

afterEach(async () => {
  globalThis.fetch = originalFetch;
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

describe("billing lifecycle", () => {
  it("prevents an expired webhook worker from overwriting a retry owner", async () => {
    const timestamp = now();
    const payload = JSON.stringify({
      id: "evt_checkout_lease",
      type: "unhandled.test",
      data: { object: {} },
    });
    await env.DB.prepare(
      "INSERT INTO stripe_events (id,event_type,received_at,outcome,lease_token,lease_expires_at,attempt_count) VALUES (?,?,?,?,?,?,?)",
    ).bind("evt_checkout_lease", "unhandled.test", timestamp - 600, "pending", "old-owner", timestamp - 1, 1).run();
    const retry = await workerFetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST",
      headers: { "Stripe-Signature": await stripeSignature(payload) },
      body: payload,
    });
    expect(retry.status).toBe(200);
    expect(await env.DB.prepare("SELECT outcome,lease_token,attempt_count FROM stripe_events WHERE id='evt_checkout_lease'").first())
      .toMatchObject({ outcome: "skipped", lease_token: null, attempt_count: 2 });

    const staleFinalize = await env.DB.prepare(
      "UPDATE stripe_events SET outcome='failed' WHERE id='evt_checkout_lease' AND outcome='pending' AND lease_token='old-owner'",
    ).run();
    expect(staleFinalize.meta.changes).toBe(0);
    expect(await env.DB.prepare("SELECT outcome FROM stripe_events WHERE id='evt_checkout_lease'").first())
      .toMatchObject({ outcome: "skipped" });
  });

  it("concurrent Stripe events converge on one ready checkout subscription", async () => {
    const timestamp = now();
    await env.DB.prepare(
      "INSERT INTO checkout_sessions (stripe_checkout_session_id,claim_nonce_hash,price_id,plan,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?)",
    ).bind("cs_test_race", await sha256("ap_claim_race_1234567890"), "price_test_starter", "starter", "pending", timestamp, timestamp + 1800).run();

    installStripeMock(async (method, path) => {
      if (method === "GET" && path === "/checkout/sessions/cs_test_race") {
        return jsonResponse({
          id: "cs_test_race",
          status: "complete",
          payment_status: "paid",
          customer: "cus_race",
          subscription: "sub_race",
          customer_details: { email: "race@example.com" },
        });
      }
      if (method === "GET" && path === "/subscriptions/sub_race") {
        return jsonResponse({ id: "sub_race", customer: "cus_race", status: "active", current_period_end: timestamp + 86400, items: { data: [{ price: { id: "price_test_starter" } }] } });
      }
      if (method === "GET" && path === "/customers/cus_race") {
        return jsonResponse({ id: "cus_race", email: "race@example.com" });
      }
      throw new Error(`unexpected stripe ${method} ${path}`);
    });

    const checkoutEvent = JSON.stringify({
      id: "evt_checkout_race",
      type: "checkout.session.completed",
      data: { object: { id: "cs_test_race" } },
    });
    const subscriptionEvent = JSON.stringify({
      id: "evt_subscription_race",
      type: "customer.subscription.created",
      data: {
        object: {
          id: "sub_race",
          customer: "cus_race",
          status: "active",
          current_period_end: timestamp + 86400,
          metadata: { plan: "starter" },
          items: { data: [{ price: { id: "price_test_starter" } }] },
        },
      },
    });
    const [checkoutResponse, subscriptionResponse] = await Promise.all([
      workerFetch("https://agentpulse.test/v1/stripe/webhook", {
        method: "POST",
        headers: { "Stripe-Signature": await stripeSignature(checkoutEvent) },
        body: checkoutEvent,
      }),
      workerFetch("https://agentpulse.test/v1/stripe/webhook", {
        method: "POST",
        headers: { "Stripe-Signature": await stripeSignature(subscriptionEvent) },
        body: subscriptionEvent,
      }),
    ]);

    expect(checkoutResponse.status).toBe(200);
    expect(subscriptionResponse.status).toBe(200);
    expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM tenants WHERE email='race@example.com'").first()).toMatchObject({ count: 1 });
    expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM subscriptions WHERE stripe_customer_id='cus_race' AND stripe_subscription_id='sub_race'").first()).toMatchObject({ count: 1 });
    expect(await env.DB.prepare("SELECT status FROM checkout_sessions WHERE stripe_checkout_session_id='cs_test_race'").first()).toMatchObject({ status: "ready" });
  });

  it("never binds attacker-controlled Stripe identifiers to an existing tenant by email", async () => {
    const timestamp = now();
    await env.DB.batch([
      env.DB.prepare("INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)")
        .bind("tenant-victim", "victim@example.com", timestamp, timestamp),
      env.DB.prepare(
        "INSERT INTO subscriptions (id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit,current_period_end,updated_at,entitlement_status,grace_period_ends_at) " +
          "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
      ).bind("subscription-victim", "tenant-victim", "cus_victim", "sub_victim", "active", "price_test_starter", "starter", 1, timestamp + 86400, timestamp, "active", null),
      env.DB.prepare(
        "INSERT INTO checkout_sessions (stripe_checkout_session_id,claim_nonce_hash,price_id,plan,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?)",
      ).bind("cs_test_attacker", await sha256("ap_claim_attacker_1234567890"), "price_test_starter", "starter", "pending", timestamp, timestamp + 1800),
    ]);

    installStripeMock((method, path) => {
      if (method === "GET" && path === "/checkout/sessions/cs_test_attacker") {
        return jsonResponse({
          id: "cs_test_attacker",
          status: "complete",
          payment_status: "paid",
          customer: "cus_attacker",
          subscription: "sub_attacker",
          customer_details: { email: "victim@example.com" },
        });
      }
      if (method === "GET" && path === "/subscriptions/sub_attacker") {
        return jsonResponse({ id: "sub_attacker", customer: "cus_attacker", status: "active", current_period_end: timestamp + 86400, items: { data: [{ price: { id: "price_test_starter" } }] } });
      }
      throw new Error(`unexpected stripe ${method} ${path}`);
    });

    const claim = await workerFetch("https://agentpulse.test/v1/onboarding/claim", {
      method: "POST",
      headers: { "Content-Type": "application/json", Origin: "https://app.agentpulse.test" },
      body: JSON.stringify({ claim_nonce: "ap_claim_attacker_1234567890" }),
    });
    expect(claim.status).toBe(409);
    expect(await env.DB.prepare("SELECT stripe_customer_id,stripe_subscription_id FROM subscriptions WHERE id='subscription-victim'").first())
      .toMatchObject({ stripe_customer_id: "cus_victim", stripe_subscription_id: "sub_victim" });
    expect(await env.DB.prepare("SELECT status,tenant_id FROM checkout_sessions WHERE stripe_checkout_session_id='cs_test_attacker'").first())
      .toMatchObject({ status: "pending", tenant_id: null });
    expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM browser_sessions").first()).toMatchObject({ count: 0 });
  });

  it("does not let an older Stripe event roll subscription state backward", async () => {
    const timestamp = now();
    installStripeMock((method, path) => {
      if (method === "GET" && path === "/customers/cus_ordered") {
        return jsonResponse({ id: "cus_ordered", email: "ordered@example.com" });
      }
      throw new Error(`unexpected stripe ${method} ${path}`);
    });
    const subscription = (status: string) => ({
      id: "sub_ordered",
      customer: "cus_ordered",
      status,
      current_period_end: timestamp + 86400,
      metadata: { plan: "starter" },
      items: { data: [{ price: { id: "price_test_starter" } }] },
    });
    const newer = JSON.stringify({
      id: "evt_ordered_newer",
      type: "customer.subscription.deleted",
      created: timestamp + 20,
      data: { object: subscription("canceled") },
    });
    const older = JSON.stringify({
      id: "evt_ordered_older",
      type: "customer.subscription.updated",
      created: timestamp + 10,
      data: { object: subscription("active") },
    });

    for (const payload of [newer, older]) {
      const response = await workerFetch("https://agentpulse.test/v1/stripe/webhook", {
        method: "POST",
        headers: { "Stripe-Signature": await stripeSignature(payload) },
        body: payload,
      });
      expect(response.status).toBe(200);
    }
    expect(await env.DB.prepare(
      "SELECT status,entitlement_status,stripe_event_created_at FROM subscriptions WHERE stripe_subscription_id='sub_ordered'",
    ).first()).toMatchObject({
      status: "canceled",
      entitlement_status: "blocked",
      stripe_event_created_at: timestamp + 20,
    });
  });

});
