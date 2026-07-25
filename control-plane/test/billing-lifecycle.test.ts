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

beforeEach(async () => {
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
  globalThis.fetch = originalFetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
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
        url: "https://checkout.stripe.com/c/pay/cs_test_1",
        expires_at: now() + 1800,
      });
    });

    const response = await SELF.fetch("https://agentpulse.test/v1/billing/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan: "pro" }),
    });
    expect(response.status).toBe(201);
    const payload = await response.json<{ checkout_url: string; expires_at: number }>();
    expect(payload.checkout_url).toBe("https://checkout.stripe.com/c/pay/cs_test_1");
    const row = await env.DB.prepare("SELECT claim_nonce_hash,status,plan,price_id FROM checkout_sessions WHERE stripe_checkout_session_id='cs_test_1'")
      .first<{ claim_nonce_hash: string; status: string; plan: string; price_id: string }>();
    expect(row).toMatchObject({ status: "pending", plan: "pro", price_id: "price_test_pro" });
    expect(row?.claim_nonce_hash).toHaveLength(64);
    expect(JSON.stringify(row)).not.toContain("ap_claim_");
  });

  it("rejects unknown plans", async () => {
    const invalid = await SELF.fetch("https://agentpulse.test/v1/billing/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan: "enterprise" }),
    });
    expect(invalid.status).toBe(422);
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
        return jsonResponse({ id: "sub_1", status: "active", current_period_end: now() + 86400 });
      }
      if (method === "POST" && path === "/billing_portal/sessions") {
        const form = formMap(body);
        expect(form.customer).toBe("cus_1");
        return jsonResponse({ url: "https://billing.stripe.com/p/session/test" });
      }
      throw new Error(`unexpected stripe ${method} ${path} ${body}`);
    });

    const checkout = await SELF.fetch("https://agentpulse.test/v1/billing/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan: "starter" }),
    });
    expect(checkout.status).toBe(201);
    expect(claimNonce.length).toBeGreaterThan(16);

    const claim = await SELF.fetch("https://agentpulse.test/v1/onboarding/claim", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ claim_nonce: claimNonce }),
    });
    expect(claim.status).toBe(200);
    const setCookie = claim.headers.get("Set-Cookie") ?? "";
    expect(setCookie).toContain("ap_session=");
    expect(setCookie).toContain("HttpOnly");
    expect(setCookie).toContain("SameSite=Lax");
    expect(setCookie).not.toContain("ap_account_");
    const claimed = await claim.json<{ csrf_token: string; account: { plan: string; entitlement_status: string; agent_limit: number; email: string } }>();
    expect(claimed.csrf_token.length).toBeGreaterThanOrEqual(16);
    expect(claimed.account).toMatchObject({
      plan: "starter",
      entitlement_status: "active",
      agent_limit: 1,
      email: "owner@example.com",
    });
    expect(JSON.stringify(claimed)).not.toContain("ap_account_");
    expect(JSON.stringify(claimed)).not.toContain(claimNonce);

    const replay = await SELF.fetch("https://agentpulse.test/v1/onboarding/claim", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ claim_nonce: claimNonce }),
    });
    expect(replay.status).toBe(409);

    const sessionCookie = setCookie.split(";")[0] ?? "";
    const account = await SELF.fetch("https://agentpulse.test/v1/account", {
      headers: { Cookie: sessionCookie },
    });
    expect(account.status).toBe(200);
    expect(await account.json()).toMatchObject({ plan: "starter", entitlement_status: "active", agent_limit: 1 });

    const enrollment = await SELF.fetch("https://agentpulse.test/v1/browser/enrollment-tokens", {
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

    const badCsrf = await SELF.fetch("https://agentpulse.test/v1/billing/portal", {
      method: "POST",
      headers: { Cookie: sessionCookie, "X-CSRF-Token": "not-the-token", Origin: "https://app.agentpulse.test" },
    });
    expect(badCsrf.status).toBe(403);

    const portal = await SELF.fetch("https://agentpulse.test/v1/billing/portal", {
      method: "POST",
      headers: {
        Cookie: sessionCookie,
        "X-CSRF-Token": claimed.csrf_token,
        Origin: "https://app.agentpulse.test",
      },
    });
    expect(portal.status).toBe(200);
    expect(await portal.json()).toEqual({ portal_url: "https://billing.stripe.com/p/session/test" });

    const logout = await SELF.fetch("https://agentpulse.test/v1/session", {
      method: "DELETE",
      headers: {
        Cookie: sessionCookie,
        "X-CSRF-Token": claimed.csrf_token,
        Origin: "https://app.agentpulse.test",
      },
    });
    expect(logout.status).toBe(204);
    const afterLogout = await SELF.fetch("https://agentpulse.test/v1/account", {
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
    const first = await SELF.fetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST",
      headers: { "Stripe-Signature": await stripeSignature(payload) },
      body: payload,
    });
    const second = await SELF.fetch("https://agentpulse.test/v1/stripe/webhook", {
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
    expect((await SELF.fetch("https://agentpulse.test/v1/stripe/webhook", {
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
      data: { object: { subscription: "sub_y" } },
    };
    const payload = JSON.stringify(paid);
    expect((await SELF.fetch("https://agentpulse.test/v1/stripe/webhook", {
      method: "POST",
      headers: { "Stripe-Signature": await stripeSignature(payload) },
      body: payload,
    })).status).toBe(200);
    const row = await env.DB.prepare("SELECT status,entitlement_status,grace_period_ends_at FROM subscriptions WHERE stripe_subscription_id='sub_y'")
      .first<{ status: string; entitlement_status: string; grace_period_ends_at: number | null }>();
    expect(row).toEqual({ status: "active", entitlement_status: "active", grace_period_ends_at: null });
  });
});
