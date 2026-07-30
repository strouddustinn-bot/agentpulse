import { SELF } from "cloudflare:test";
import { env } from "cloudflare:workers";
import { afterEach, expect, it } from "vitest";

const originalFetch = globalThis.fetch;
const now = () => Math.floor(Date.now() / 1000);

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

function installStripeMock(handler: (method: string, path: string) => Response | Promise<Response>): void {
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    return handler((init?.method ?? "GET").toUpperCase(), url.slice("https://api.stripe.com/v1".length));
  }) as typeof fetch;
}

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

it("rejects claims whose canonical Stripe subscription is not active", async () => {
  const timestamp = now();
  const claimNonce = "ap_claim_incomplete_subscription_123";
  await env.DB.prepare(
    "INSERT INTO checkout_sessions (stripe_checkout_session_id,claim_nonce_hash,price_id,plan,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?)",
  ).bind("cs_incomplete_sub", await sha256(claimNonce), "price_test_starter", "starter", "pending", timestamp, timestamp + 1800).run();
  installStripeMock((_method, path) => {
    if (path === "/checkout/sessions/cs_incomplete_sub") return jsonResponse({
      id: "cs_incomplete_sub", status: "complete", payment_status: "paid", customer: "cus_incomplete_sub",
      subscription: "sub_incomplete_sub", customer_details: { email: "incomplete-sub@example.com" },
    });
    if (path === "/subscriptions/sub_incomplete_sub") return jsonResponse({
      id: "sub_incomplete_sub", customer: "cus_incomplete_sub", status: "incomplete", current_period_end: timestamp + 1000,
      items: { data: [{ price: { id: "price_test_starter" } }] },
    });
    throw new Error(`unexpected ${path}`);
  });
  const response = await workerFetch("https://agentpulse.test/v1/onboarding/claim", {
    method: "POST", headers: { "Content-Type": "application/json", Origin: "https://app.agentpulse.test" }, body: JSON.stringify({ claim_nonce: claimNonce }),
  });
  expect(response.status).toBe(409);
  expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM subscriptions WHERE stripe_subscription_id='sub_incomplete_sub'").first())
    .toMatchObject({ count: 0 });
  expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM onboarding_claims WHERE checkout_session_id='cs_incomplete_sub'").first())
    .toMatchObject({ count: 0 });
});

it("fails closed when canonical Stripe subscription retrieval fails", async () => {
  const timestamp = now();
  const claimNonce = "ap_claim_subscription_unavailable_123";
  await env.DB.prepare(
    "INSERT INTO checkout_sessions (stripe_checkout_session_id,claim_nonce_hash,price_id,plan,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?)",
  ).bind("cs_sub_unavailable", await sha256(claimNonce), "price_test_starter", "starter", "pending", timestamp, timestamp + 1800).run();
  installStripeMock((_method, path) => {
    if (path === "/checkout/sessions/cs_sub_unavailable") return jsonResponse({
      id: "cs_sub_unavailable", status: "complete", payment_status: "paid", customer: "cus_sub_unavailable",
      subscription: "sub_sub_unavailable", customer_details: { email: "sub-unavailable@example.com" },
    });
    if (path === "/subscriptions/sub_sub_unavailable") return jsonResponse({ error: { message: "down" } }, 500);
    throw new Error(`unexpected ${path}`);
  });
  const response = await workerFetch("https://agentpulse.test/v1/onboarding/claim", {
    method: "POST", headers: { "Content-Type": "application/json", Origin: "https://app.agentpulse.test" }, body: JSON.stringify({ claim_nonce: claimNonce }),
  });
  expect(response.status).toBeGreaterThanOrEqual(500);
  expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM subscriptions WHERE stripe_subscription_id='sub_sub_unavailable'").first())
    .toMatchObject({ count: 0 });
  expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM onboarding_claims WHERE checkout_session_id='cs_sub_unavailable'").first())
    .toMatchObject({ count: 0 });
});

it("requires the canonical subscription customer and price to match the paid checkout", async () => {
  const timestamp = now();
  const claimNonce = "ap_claim_subscription_mismatch_123";
  await env.DB.prepare(
    "INSERT INTO checkout_sessions (stripe_checkout_session_id,claim_nonce_hash,price_id,plan,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?)",
  ).bind("cs_sub_mismatch", await sha256(claimNonce), "price_test_starter", "starter", "pending", timestamp, timestamp + 1800).run();
  installStripeMock((_method, path) => {
    if (path === "/checkout/sessions/cs_sub_mismatch") return jsonResponse({
      id: "cs_sub_mismatch", status: "complete", payment_status: "paid", customer: "cus_checkout_owner",
      subscription: "sub_mismatch", customer_details: { email: "mismatch@example.com" },
    });
    if (path === "/subscriptions/sub_mismatch") return jsonResponse({
      id: "sub_mismatch", customer: "cus_different_owner", status: "active", current_period_end: timestamp + 1000,
      items: { data: [{ price: { id: "price_test_business" } }] },
    });
    throw new Error(`unexpected ${path}`);
  });
  const response = await workerFetch("https://agentpulse.test/v1/onboarding/claim", {
    method: "POST", headers: { "Content-Type": "application/json", Origin: "https://app.agentpulse.test" }, body: JSON.stringify({ claim_nonce: claimNonce }),
  });
  expect(response.status).toBe(409);
  expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM subscriptions WHERE stripe_subscription_id='sub_mismatch'").first())
    .toMatchObject({ count: 0 });
  expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM onboarding_claims WHERE checkout_session_id='cs_sub_mismatch'").first())
    .toMatchObject({ count: 0 });
});

it("does not claim a checkout whose stored price is no longer configured", async () => {
  const timestamp = now();
  const claimNonce = "ap_claim_unmapped_checkout_price_123";
  await env.DB.prepare(
    "INSERT INTO checkout_sessions (stripe_checkout_session_id,claim_nonce_hash,price_id,plan,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?)",
  ).bind("cs_unmapped_price", await sha256(claimNonce), "price_unmapped", "starter", "pending", timestamp, timestamp + 1800).run();
  installStripeMock((_method, path) => {
    if (path === "/checkout/sessions/cs_unmapped_price") return jsonResponse({
      id: "cs_unmapped_price", status: "complete", payment_status: "paid", customer: "cus_unmapped_price",
      subscription: "sub_unmapped_price", customer_details: { email: "unmapped@example.com" },
    });
    throw new Error(`unexpected ${path}`);
  });
  const response = await workerFetch("https://agentpulse.test/v1/onboarding/claim", {
    method: "POST", headers: { "Content-Type": "application/json", Origin: "https://app.agentpulse.test" }, body: JSON.stringify({ claim_nonce: claimNonce }),
  });
  expect(response.status).toBe(503);
  expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM subscriptions WHERE stripe_subscription_id='sub_unmapped_price'").first())
    .toMatchObject({ count: 0 });
  expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM onboarding_claims WHERE checkout_session_id='cs_unmapped_price'").first())
    .toMatchObject({ count: 0 });
});

it("resolves equal-created active plan changes to the lower capacity regardless of delivery order", async () => {
  const timestamp = now();
  installStripeMock((_method, path) => {
    if (path.startsWith("/customers/")) {
      const customer = path.slice("/customers/".length);
      return jsonResponse({ id: customer, email: `${customer}@example.com` });
    }
    throw new Error(`unexpected ${path}`);
  });
  async function send(customer: string, subscription: string, plan: "starter" | "business", eventId: string): Promise<void> {
    const payload = JSON.stringify({
      id: eventId, type: "customer.subscription.updated", created: timestamp + 10,
      data: { object: {
        // The lower-capacity plan is longer-lived so equal-created ordering
        // must use a deterministic tuple rather than incomparable AND checks.
        id: subscription, customer, status: "active", current_period_end: timestamp + (plan === "starter" ? 2000 : 1000),
        metadata: { plan }, items: { data: [{ price: { id: `price_test_${plan}` } }] },
      } },
    });
    const response = await workerFetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST", headers: { "Stripe-Signature": await stripeSignature(payload) }, body: payload,
    });
    expect(response.status).toBe(200);
  }
  await send("cus_equal_a", "sub_equal_a", "starter", "evt_equal_a1");
  await send("cus_equal_a", "sub_equal_a", "business", "evt_equal_a2");
  await send("cus_equal_b", "sub_equal_b", "business", "evt_equal_b1");
  await send("cus_equal_b", "sub_equal_b", "starter", "evt_equal_b2");
  expect(await env.DB.prepare("SELECT plan,agent_limit FROM subscriptions WHERE stripe_subscription_id='sub_equal_a'").first())
    .toMatchObject({ plan: "starter", agent_limit: 1 });
  expect(await env.DB.prepare("SELECT plan,agent_limit FROM subscriptions WHERE stripe_subscription_id='sub_equal_b'").first())
    .toMatchObject({ plan: "starter", agent_limit: 1 });
});

it("rejects invoice events whose customer does not own the subscription", async () => {
  const timestamp = now();
  await env.DB.batch([
    env.DB.prepare("INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)")
      .bind("invoice-victim", "invoice-victim@example.com", timestamp, timestamp),
    env.DB.prepare("INSERT INTO subscriptions (id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit,updated_at,entitlement_status,stripe_event_created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)")
      .bind("invoice-victim-sub", "invoice-victim", "cus_invoice_victim", "sub_invoice_victim", "past_due", "price_test_starter", "starter", 1, timestamp, "grace", 0),
  ]);
  const payload = JSON.stringify({
    id: "evt_invoice_mismatch", type: "invoice.paid", created: timestamp + 1,
    data: { object: { customer: "cus_invoice_attacker", subscription: "sub_invoice_victim" } },
  });
  const response = await workerFetch("https://agentpulse.test/v1/stripe/webhook", {
    method: "POST", headers: { "Stripe-Signature": await stripeSignature(payload) }, body: payload,
  });
  expect(response.status).toBe(409);
  expect(await env.DB.prepare("SELECT stripe_customer_id,status,entitlement_status FROM subscriptions WHERE id='invoice-victim-sub'").first())
    .toMatchObject({ stripe_customer_id: "cus_invoice_victim", status: "past_due", entitlement_status: "grace" });
});
