import { SELF } from "cloudflare:test";
import { env } from "cloudflare:workers";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

const now = () => Math.floor(Date.now() / 1000);
const originalFetch = globalThis.fetch;
const originalEnvironment = env.ENVIRONMENT;

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
  globalThis.fetch = originalFetch;
  env.ENVIRONMENT = originalEnvironment;
});

afterEach(async () => {
  globalThis.fetch = originalFetch;
  env.ENVIRONMENT = originalEnvironment;
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
  it("creates an allowlisted checkout session and stores only the claim hash", async () => {
    installStripeMock((method, path, body) => {
      expect(method).toBe("POST");
      expect(path).toBe("/checkout/sessions");
      const form = formMap(body);
      expect(form["line_items[0][price]"]).toBe("price_test_pro");
      expect(form.success_url).toContain("claim_nonce=");
      expect(form.billing_address_collection).toBe("required");
      return jsonResponse({
        id: "cs_test_1",
        livemode: false,
        url: "https://checkout.stripe.com/c/pay/cs_test_1",
        expires_at: now() + 1800,
      });
    });

    const response = await workerFetch("https://agentpulse.test/v1/billing/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan: "pro" }),
    });
    expect(response.status).toBe(201);
    const payload = await response.json() as { checkout_url: string; checkout_session_id: string; livemode: boolean; expires_at: number };
    expect(payload).toMatchObject({
      checkout_url: "https://checkout.stripe.com/c/pay/cs_test_1",
      checkout_session_id: "cs_test_1",
      livemode: false,
    });
    const row = await env.DB.prepare("SELECT claim_nonce_hash,status,plan,price_id FROM checkout_sessions WHERE stripe_checkout_session_id='cs_test_1'")
      .first<{ claim_nonce_hash: string; status: string; plan: string; price_id: string }>();
    expect(row).toMatchObject({ status: "pending", plan: "pro", price_id: "price_test_pro" });
    expect(row?.claim_nonce_hash).toHaveLength(64);
    expect(JSON.stringify(row)).not.toContain("ap_claim_");
  });

  it("rejects staging checkout before persistence when Stripe identity is not test-mode", async () => {
    env.ENVIRONMENT = "staging";
    installStripeMock(() => jsonResponse({
      id: "cs_live_unsafe",
      livemode: true,
      url: "https://checkout.stripe.com/c/pay/cs_live_unsafe",
      expires_at: now() + 1800,
    }));

    const response = await workerFetch("https://agentpulse.test/v1/billing/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan: "starter" }),
    });

    expect(response.status).toBe(503);
    expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM checkout_sessions").first()).toMatchObject({ count: 0 });
  });

  it("rejects unknown plans", async () => {
    const invalid = await workerFetch("https://agentpulse.test/v1/billing/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan: "enterprise" }),
    });
    expect(invalid.status).toBe(422);
  });

  it("reprocesses a failed Stripe event when Stripe retries the same event ID", async () => {
    const timestamp = now();
    await env.DB.prepare(
      "INSERT INTO checkout_sessions (stripe_checkout_session_id,claim_nonce_hash,price_id,plan,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?)",
    ).bind("cs_test_retry", await sha256("ap_claim_retry_1234567890"), "price_test_starter", "starter", "pending", timestamp, timestamp + 1800).run();

    let checkoutFetchFails = true;
    installStripeMock((method, path) => {
      if (method === "GET" && path === "/checkout/sessions/cs_test_retry") {
        if (checkoutFetchFails) return jsonResponse({ error: { message: "temporary failure" } }, 500);
        return jsonResponse({
          id: "cs_test_retry",
          status: "complete",
          payment_status: "paid",
          customer: "cus_retry",
          subscription: "sub_retry",
          customer_details: { email: "retry@example.com" },
        });
      }
      if (method === "GET" && path === "/subscriptions/sub_retry") {
        return jsonResponse({ id: "sub_retry", customer: "cus_retry", status: "active", current_period_end: timestamp + 86400, items: { data: [{ price: { id: "price_test_starter" } }] } });
      }
      throw new Error(`unexpected stripe ${method} ${path}`);
    });

    const event = {
      id: "evt_checkout_retry",
      type: "checkout.session.completed",
      data: { object: { id: "cs_test_retry" } },
    };
    const payload = JSON.stringify(event);
    const signature = await stripeSignature(payload);
    const first = await workerFetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST",
      headers: { "Stripe-Signature": signature },
      body: payload,
    });
    expect(first.status).toBeGreaterThanOrEqual(500);
    expect(await env.DB.prepare("SELECT outcome FROM stripe_events WHERE id='evt_checkout_retry'").first()).toMatchObject({ outcome: "failed" });

    checkoutFetchFails = false;
    const retry = await workerFetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST",
      headers: { "Stripe-Signature": signature },
      body: payload,
    });
    expect(retry.status).toBe(200);
    expect(await retry.json()).toMatchObject({ ok: true, duplicate: false });
    expect(await env.DB.prepare("SELECT outcome FROM stripe_events WHERE id='evt_checkout_retry'").first()).toMatchObject({ outcome: "processed" });
    expect(await env.DB.prepare("SELECT status FROM checkout_sessions WHERE stripe_checkout_session_id='cs_test_retry'").first()).toMatchObject({ status: "ready" });
  });

  it("does not process the same Stripe event while an active lease is pending", async () => {
    const timestamp = now();
    const payload = JSON.stringify({
      id: "evt_checkout_inflight",
      type: "checkout.session.completed",
      data: { object: { id: "cs_test_inflight" } },
    });
    await env.DB.prepare(
      "INSERT INTO stripe_events (id,event_type,received_at,outcome,lease_token,lease_expires_at,attempt_count,payload_sha256) VALUES (?,?,?,?,?,?,?,?)",
    ).bind("evt_checkout_inflight", "checkout.session.completed", timestamp, "pending", "active-owner", timestamp + 300, 1, await sha256(payload)).run();

    let stripeFetches = 0;
    installStripeMock((method, path) => {
      stripeFetches += 1;
      throw new Error(`unexpected stripe ${method} ${path}`);
    });

    const concurrent = await workerFetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST",
      headers: { "Stripe-Signature": await stripeSignature(payload) },
      body: payload,
    });

    expect(concurrent.status).toBe(409);
    expect(stripeFetches).toBe(0);
    expect(await env.DB.prepare("SELECT outcome,lease_token FROM stripe_events WHERE id='evt_checkout_inflight'").first())
      .toMatchObject({ outcome: "pending", lease_token: "active-owner" });
  });

  it("maps incomplete_expired to canceled/blocked without CHECK failure", async () => {
    const timestamp = now();
    await env.DB.prepare(
      "INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)",
    ).bind("tenant_expired", "expired@example.com", timestamp, timestamp).run();
    await env.DB.prepare(
      "INSERT INTO subscriptions (id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit,current_period_end,updated_at,entitlement_status,grace_period_ends_at,stripe_event_created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
    ).bind(
      "subrow_expired",
      "tenant_expired",
      "cus_expired",
      "sub_expired",
      "active",
      "price_test_starter",
      "starter",
      1,
      timestamp + 86400,
      timestamp,
      "active",
      null,
      timestamp - 10,
    ).run();

    installStripeMock((method, path) => {
      if (method === "GET" && path === "/customers/cus_expired") {
        return jsonResponse({ id: "cus_expired", email: "expired@example.com" });
      }
      throw new Error(`unexpected stripe ${method} ${path}`);
    });

    const event = {
      id: "evt_incomplete_expired",
      type: "customer.subscription.updated",
      created: timestamp,
      data: {
        object: {
          id: "sub_expired",
          customer: "cus_expired",
          status: "incomplete_expired",
          current_period_end: timestamp + 86400,
          items: { data: [{ price: { id: "price_test_starter" } }] },
        },
      },
    };
    const payload = JSON.stringify(event);
    const response = await workerFetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST",
      headers: { "Stripe-Signature": await stripeSignature(payload) },
      body: payload,
    });
    expect(response.status).toBe(200);
    expect(await env.DB.prepare(
      "SELECT status,entitlement_status,grace_period_ends_at FROM subscriptions WHERE stripe_subscription_id='sub_expired'",
    ).first()).toMatchObject({ status: "canceled", entitlement_status: "blocked", grace_period_ends_at: null });
  });

  it("derives plan only from configured Price IDs and blocks metadata/price disagreement", async () => {
    const timestamp = now();
    await env.DB.prepare(
      "INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)",
    ).bind("tenant_meta", "meta@example.com", timestamp, timestamp).run();
    await env.DB.prepare(
      "INSERT INTO subscriptions (id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit,current_period_end,updated_at,entitlement_status,grace_period_ends_at,stripe_event_created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
    ).bind(
      "subrow_meta",
      "tenant_meta",
      "cus_meta",
      "sub_meta",
      "active",
      "price_test_starter",
      "starter",
      1,
      timestamp + 86400,
      timestamp,
      "active",
      null,
      timestamp - 10,
    ).run();

    installStripeMock((method, path) => {
      if (method === "GET" && path === "/customers/cus_meta") {
        return jsonResponse({ id: "cus_meta", email: "meta@example.com" });
      }
      throw new Error(`unexpected stripe ${method} ${path}`);
    });

    const event = {
      id: "evt_metadata_disagreement",
      type: "customer.subscription.updated",
      created: timestamp,
      data: {
        object: {
          id: "sub_meta",
          customer: "cus_meta",
          status: "active",
          metadata: { plan: "business" },
          current_period_end: timestamp + 86400,
          items: { data: [{ price: { id: "price_test_starter" } }] },
        },
      },
    };
    const payload = JSON.stringify(event);
    const response = await workerFetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST",
      headers: { "Stripe-Signature": await stripeSignature(payload) },
      body: payload,
    });
    expect(response.status).toBe(200);
    expect(await env.DB.prepare(
      "SELECT plan,agent_limit,entitlement_status FROM subscriptions WHERE stripe_subscription_id='sub_meta'",
    ).first()).toMatchObject({ plan: "starter", agent_limit: 1, entitlement_status: "blocked" });
  });
});
