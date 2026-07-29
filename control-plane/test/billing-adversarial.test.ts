import { SELF } from "cloudflare:test";
import { env } from "cloudflare:workers";
import { afterEach, expect, it } from "vitest";
import worker from "../src/index";

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

function installStripeMock(handler: (method: string, path: string) => Response | Promise<Response>): void {
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    return handler((init?.method ?? "GET").toUpperCase(), url.slice("https://api.stripe.com/v1".length));
  }) as typeof fetch;
}

afterEach(() => {
  globalThis.fetch = originalFetch;
});

it("rejects a complete checkout whose payment is unpaid", async () => {
  const timestamp = now();
  const nonce = "ap_claim_unpaid_1234567890";
  await env.DB.prepare(
    "INSERT INTO checkout_sessions (stripe_checkout_session_id,claim_nonce_hash,price_id,plan,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?)",
  ).bind("cs_unpaid", await sha256(nonce), "price_test_starter", "starter", "pending", timestamp, timestamp + 1800).run();
  installStripeMock((_method, path) => {
    if (path === "/checkout/sessions/cs_unpaid") return jsonResponse({
      id: "cs_unpaid",
      status: "complete",
      payment_status: "unpaid",
      customer: "cus_unpaid",
      subscription: "sub_unpaid",
      customer_details: { email: "unpaid@example.com" },
    });
    throw new Error(`unexpected ${path}`);
  });
  const response = await SELF.fetch("https://agentpulse.test/v1/onboarding/claim", {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: "https://app.agentpulse.test" },
    body: JSON.stringify({ claim_nonce: nonce }),
  });
  expect(response.status).toBe(409);
  expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM browser_sessions").first()).toMatchObject({ count: 0 });
  expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM subscriptions").first()).toMatchObject({ count: 0 });
});

it("requires customer and subscription identifiers to agree before unknown-price blocking", async () => {
  const timestamp = now();
  await env.DB.batch([
    env.DB.prepare("INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)")
      .bind("tenant-victim", "victim2@example.com", timestamp, timestamp),
    env.DB.prepare(
      "INSERT INTO subscriptions (id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit,updated_at,entitlement_status,stripe_event_created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
    ).bind("row-victim", "tenant-victim", "cus_victim", "sub_victim", "active", "price_test_starter", "starter", 1, timestamp, "active", timestamp),
  ]);
  const payload = JSON.stringify({
    id: "evt_mismatch",
    type: "customer.subscription.updated",
    created: timestamp + 1,
    data: { object: {
      id: "sub_victim",
      customer: "cus_attacker",
      status: "active",
      items: { data: [{ price: { id: "price_unknown" } }] },
    } },
  });
  const response = await SELF.fetch("https://agentpulse.test/v1/stripe/webhook", {
    method: "POST",
    headers: { "Stripe-Signature": await stripeSignature(payload) },
    body: payload,
  });
  expect(response.status).toBe(409);
  expect(await env.DB.prepare("SELECT stripe_customer_id,entitlement_status FROM subscriptions WHERE id='row-victim'").first())
    .toMatchObject({ stripe_customer_id: "cus_victim", entitlement_status: "active" });
});

it("does not let an equal-created event restore a more permissive entitlement", async () => {
  const timestamp = now();
  await env.DB.batch([
    env.DB.prepare("INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)")
      .bind("tenant-tie", "tie@example.com", timestamp, timestamp),
    env.DB.prepare(
      "INSERT INTO subscriptions (id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit,updated_at,entitlement_status,stripe_event_created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
    ).bind("row-tie", "tenant-tie", "cus_tie", "sub_tie", "active", "price_test_starter", "starter", 1, timestamp, "active", 0),
  ]);
  installStripeMock((_method, path) => {
    if (path === "/customers/cus_tie") return jsonResponse({ id: "cus_tie", email: "tie@example.com" });
    throw new Error(`unexpected ${path}`);
  });
  const item = (status: string) => ({
    id: "sub_tie",
    customer: "cus_tie",
    status,
    current_period_end: timestamp + 1000,
    metadata: { plan: "starter" },
    items: { data: [{ price: { id: "price_test_starter" } }] },
  });
  const deleted = JSON.stringify({ id: "evt_tie_deleted", type: "customer.subscription.deleted", created: timestamp + 10, data: { object: item("canceled") } });
  const active = JSON.stringify({ id: "evt_tie_update", type: "customer.subscription.updated", created: timestamp + 10, data: { object: item("active") } });
  for (const payload of [deleted, active]) {
    expect((await SELF.fetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST",
      headers: { "Stripe-Signature": await stripeSignature(payload) },
      body: payload,
    })).status).toBe(200);
  }
  expect(await env.DB.prepare("SELECT status,entitlement_status FROM subscriptions WHERE id='row-tie'").first())
    .toMatchObject({ status: "canceled", entitlement_status: "blocked" });
});

it("rolls back the checkout claim when browser-session issuance fails", async () => {
  const timestamp = now();
  const nonce = "ap_claim_partial_1234567890";
  await env.DB.prepare(
    "INSERT INTO checkout_sessions (stripe_checkout_session_id,claim_nonce_hash,price_id,plan,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?)",
  ).bind("cs_partial", await sha256(nonce), "price_test_starter", "starter", "pending", timestamp, timestamp + 1800).run();
  await env.DB.prepare(
    "CREATE TRIGGER reject_browser_session BEFORE INSERT ON browser_sessions BEGIN SELECT RAISE(ABORT, 'synthetic session failure'); END",
  ).run();
  installStripeMock((_method, path) => {
    if (path === "/checkout/sessions/cs_partial") return jsonResponse({
      id: "cs_partial",
      status: "complete",
      payment_status: "paid",
      customer: "cus_partial",
      subscription: "sub_partial",
      customer_details: { email: "partial@example.com" },
    });
    if (path === "/subscriptions/sub_partial") return jsonResponse({ id: "sub_partial", customer: "cus_partial", status: "active", current_period_end: timestamp + 1000, items: { data: [{ price: { id: "price_test_starter" } }] } });
    throw new Error(`unexpected ${path}`);
  });
  const claim = () => SELF.fetch("https://agentpulse.test/v1/onboarding/claim", {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: "https://app.agentpulse.test" },
    body: JSON.stringify({ claim_nonce: nonce }),
  });
  expect((await claim()).status).toBe(500);
  expect(await env.DB.prepare("SELECT status FROM checkout_sessions WHERE stripe_checkout_session_id='cs_partial'").first())
    .toMatchObject({ status: "ready" });
  expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM onboarding_claims WHERE checkout_session_id='cs_partial'").first())
    .toMatchObject({ count: 0 });
  expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM browser_sessions").first()).toMatchObject({ count: 0 });
  expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM account_credentials").first()).toMatchObject({ count: 0 });
  await env.DB.prepare("DROP TRIGGER reject_browser_session").run();
  expect((await claim()).status).toBe(200);
});

it("fences subscription side effects from a displaced webhook worker", async () => {
  const timestamp = now();
  await env.DB.prepare(
    "INSERT INTO checkout_sessions (stripe_checkout_session_id,claim_nonce_hash,price_id,plan,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?)",
  ).bind("cs_lease_side_effect", await sha256("ap_claim_lease_side_effect_123"), "price_test_starter", "starter", "pending", timestamp, timestamp + 1800).run();
  let subFetches = 0;
  let signalFirst: (() => void) | undefined;
  const firstReached = new Promise<void>((resolve) => { signalFirst = resolve; });
  let signalSecond: (() => void) | undefined;
  const secondReached = new Promise<void>((resolve) => { signalSecond = resolve; });
  let releaseFirst: (() => void) | undefined;
  const firstGate = new Promise<void>((resolve) => { releaseFirst = resolve; });
  installStripeMock(async (_method, path) => {
    if (path === "/checkout/sessions/cs_lease_side_effect") return jsonResponse({
      id: "cs_lease_side_effect",
      status: "complete",
      payment_status: "paid",
      customer: "cus_lease_side",
      subscription: "sub_lease_side",
      customer_details: { email: "lease-side@example.com" },
    });
    if (path === "/subscriptions/sub_lease_side") {
      subFetches += 1;
      if (subFetches === 1) {
        signalFirst?.();
        await firstGate;
        return jsonResponse({ id: "sub_lease_side", customer: "cus_lease_side", status: "active", current_period_end: timestamp + 100, items: { data: [{ price: { id: "price_test_starter" } }] } });
      }
      signalSecond?.();
      return jsonResponse({ id: "sub_lease_side", customer: "cus_lease_side", status: "active", current_period_end: timestamp + 1000, items: { data: [{ price: { id: "price_test_starter" } }] } });
    }
    throw new Error(`unexpected ${path}`);
  });
  const payload = JSON.stringify({
    id: "evt_lease_side",
    type: "checkout.session.completed",
    created: timestamp,
    data: { object: { id: "cs_lease_side_effect" } },
  });
  const signature = await stripeSignature(payload);
  const first = worker.fetch(new Request("https://agentpulse.test/v1/stripe/webhook", {
    method: "POST",
    headers: { "Stripe-Signature": signature },
    body: payload,
  }), env as never);
  await firstReached;
  await env.DB.prepare("UPDATE stripe_events SET lease_expires_at=? WHERE id='evt_lease_side'").bind(timestamp - 1).run();
  const second = worker.fetch(new Request("https://agentpulse.test/v1/stripe/webhook", {
    method: "POST",
    headers: { "Stripe-Signature": signature },
    body: payload,
  }), env as never);
  await secondReached;
  releaseFirst?.();
  const secondResponse = await second;
  expect(secondResponse.status).toBe(200);
  await secondResponse.arrayBuffer();
  expect(await env.DB.prepare("SELECT current_period_end FROM subscriptions WHERE stripe_subscription_id='sub_lease_side'").first())
    .toMatchObject({ current_period_end: timestamp + 1000 });
  const firstResponse = await first;
  expect(firstResponse.status).toBe(409);
  await firstResponse.arrayBuffer();
  expect(await env.DB.prepare("SELECT current_period_end FROM subscriptions WHERE stripe_subscription_id='sub_lease_side'").first())
    .toMatchObject({ current_period_end: timestamp + 1000 });
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
  const response = await SELF.fetch("https://agentpulse.test/v1/onboarding/claim", {
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
  const response = await SELF.fetch("https://agentpulse.test/v1/onboarding/claim", {
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
  const response = await SELF.fetch("https://agentpulse.test/v1/onboarding/claim", {
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
  const response = await SELF.fetch("https://agentpulse.test/v1/onboarding/claim", {
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
    const response = await SELF.fetch("https://agentpulse.test/v1/stripe/webhook", {
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
  const response = await SELF.fetch("https://agentpulse.test/v1/stripe/webhook", {
    method: "POST", headers: { "Stripe-Signature": await stripeSignature(payload) }, body: payload,
  });
  expect(response.status).toBe(409);
  expect(await env.DB.prepare("SELECT stripe_customer_id,status,entitlement_status FROM subscriptions WHERE id='invoice-victim-sub'").first())
    .toMatchObject({ stripe_customer_id: "cus_invoice_victim", status: "past_due", entitlement_status: "grace" });
});

it("rejects a changed payload when Stripe retries the same event ID and type", async () => {
  const timestamp = now();
  const failedPayload = JSON.stringify({
    id: "evt_payload_immutable", type: "customer.subscription.created", created: timestamp,
    data: { object: { id: "sub_payload_original", status: "active" } },
  });
  const first = await SELF.fetch("https://agentpulse.test/v1/stripe/webhook", {
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
  const retry = await SELF.fetch("https://agentpulse.test/v1/stripe/webhook", {
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
  const first = await SELF.fetch("https://agentpulse.test/v1/stripe/webhook", {
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
  const changed = await SELF.fetch("https://agentpulse.test/v1/stripe/webhook", {
    method: "POST", headers: { "Stripe-Signature": await stripeSignature(changedBody) }, body: changedBody,
  });
  expect(changed.status).toBe(409);
  expect(await env.DB.prepare("SELECT outcome,payload_sha256,attempt_count FROM stripe_events WHERE id='evt_legacy_terminal'").first())
    .toMatchObject({ outcome: "processed", payload_sha256: bound?.payload_sha256, attempt_count: 0 });
  expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM subscriptions WHERE stripe_subscription_id='sub_legacy_changed'").first())
    .toMatchObject({ count: 0 });
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
