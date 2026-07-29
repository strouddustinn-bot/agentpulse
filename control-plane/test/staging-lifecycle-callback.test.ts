import { afterEach, describe, expect, it, vi } from "vitest";
import worker, { type Env } from "../../scripts/staging-lifecycle-callback/worker";

class FakeKv {
  value: string | null = null;
  writes: Array<{ key: string; value: string; ttl?: number }> = [];

  async get(key: string): Promise<string | null> {
    expect(key).toBe("latest");
    return this.value;
  }

  async put(key: string, value: string, options?: { expirationTtl?: number }): Promise<void> {
    this.value = value;
    const ttl = options?.expirationTtl;
    this.writes.push(ttl === undefined ? { key, value } : { key, value, ttl });
  }
}

function env(kv: FakeKv): Env {
  return {
    CONTROL_PLANE_BASE: "https://staging-api.agentpulse.ca",
    RECEIPTS: kv as unknown as KVNamespace,
  };
}

const sensitive = {
  claimNonce: "ap_claim_sensitive_value_123456789",
  csrf: "ap_csrf_sensitive_value",
  cookie: "ap_session=sensitive_cookie_value",
  enrollment: "ap_enroll_sensitive_value",
  credential: "ap_agent_sensitive_value",
  email: "private@example.test",
  portal: "https://billing.stripe.com/p/session/sensitive_capability",
};

function response(body: unknown, status: number, headers: HeadersInit = {}): Response {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

function installSuccessfulControlPlane() {
  let claimCount = 0;
  let enrollmentCount = 0;
  let heartbeatCount = 0;
  let loggedOut = false;
  let agentKey = "";

  const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const request = new Request(input, init);
    const url = new URL(request.url);
    expect(url.origin).toBe("https://staging-api.agentpulse.ca");

    if (request.method === "POST" && url.pathname === "/v1/onboarding/claim") {
      const body = await request.json() as { claim_nonce: string };
      expect(body.claim_nonce).toBe(sensitive.claimNonce);
      expect(request.headers.get("origin")).toBe("https://callback.example.workers.dev");
      claimCount += 1;
      if (claimCount === 2) return response({ error: { code: "already_claimed" } }, 409);
      return response({
        csrf_token: sensitive.csrf,
        account: {
          tenant_id: "sensitive-tenant-id",
          email: sensitive.email,
          plan: "starter",
          entitlement_status: "active",
          agent_limit: 1,
        },
      }, 200, { "Set-Cookie": `${sensitive.cookie}; HttpOnly; Secure; SameSite=None` });
    }

    if (request.method === "GET" && url.pathname === "/v1/account") {
      expect(request.headers.get("cookie")).toBe(sensitive.cookie);
      if (loggedOut) return response({ error: { code: "invalid_session" } }, 401);
      return response({
        tenant_id: "sensitive-tenant-id",
        email: sensitive.email,
        plan: "starter",
        entitlement_status: "active",
        agent_limit: 1,
      }, 200);
    }

    if (request.method === "POST" && url.pathname === "/v1/billing/portal") {
      expect(request.headers.get("cookie")).toBe(sensitive.cookie);
      expect(request.headers.get("origin")).toBe("https://callback.example.workers.dev");
      const csrf = request.headers.get("x-csrf-token");
      if (csrf === null || csrf === "invalid") return response({ error: { code: "csrf_rejected" } }, 403);
      expect(csrf).toBe(sensitive.csrf);
      return response({ portal_url: sensitive.portal }, 200);
    }

    if (request.method === "POST" && url.pathname === "/v1/browser/enrollment-tokens") {
      expect(request.headers.get("x-csrf-token")).toBe(sensitive.csrf);
      expect(await request.json()).toEqual({ ttl_seconds: 300 });
      return response({ enrollment_token: sensitive.enrollment, expires_at: 9999999999 }, 201);
    }

    if (request.method === "POST" && url.pathname === "/v1/agents/enroll") {
      expect(request.headers.get("authorization")).toBe(`Bearer ${sensitive.enrollment}`);
      const body = await request.json() as { agent_key: string; hostname: string; local_policy_ceiling: string };
      expect(body.hostname).toMatch(/^agentpulse-proof-host-/);
      expect(body.local_policy_ceiling).toBe("alert");
      agentKey = body.agent_key;
      enrollmentCount += 1;
      if (enrollmentCount === 2) return response({ error: { code: "enrollment_token_consumed" } }, 409);
      return response({
        agent_id: "sensitive-agent-id",
        agent_key: agentKey,
        agent_credential: sensitive.credential,
      }, 201);
    }

    if (request.method === "POST" && url.pathname === "/v1/agents/heartbeat") {
      expect(request.headers.get("authorization")).toBe(`Bearer ${sensitive.credential}`);
      const body = await request.json() as { idempotency_key: string };
      expect(body.idempotency_key).toMatch(/^agentpulse-proof-/);
      heartbeatCount += 1;
      return response({ ok: true, duplicate: heartbeatCount === 2 }, heartbeatCount === 1 ? 202 : 200);
    }

    if (request.method === "GET" && url.pathname === "/v1/fleet") {
      expect(request.headers.get("cookie")).toBe(sensitive.cookie);
      return response({ agents: [{ agent_key: agentKey, hostname: "sensitive-hostname", incidents: [] }] }, 200);
    }

    if (request.method === "DELETE" && url.pathname === "/v1/session") {
      expect(request.headers.get("cookie")).toBe(sensitive.cookie);
      expect(request.headers.get("x-csrf-token")).toBe(sensitive.csrf);
      loggedOut = true;
      return new Response(null, { status: 204 });
    }

    throw new Error(`unexpected mocked request: ${request.method} ${url.pathname}`);
  });

  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("disposable callback Worker", () => {
  it("runs the full lifecycle and persists only the redacted receipt", async () => {
    const kv = new FakeKv();
    const fetchMock = installSuccessfulControlPlane();
    const request = new Request(`https://callback.example.workers.dev/claim?claim_nonce=${sensitive.claimNonce}`);

    const callbackResponse = await worker.fetch(request, env(kv));
    expect(callbackResponse.status).toBe(303);
    expect(callbackResponse.headers.get("location")).toBe("/receipt");
    expect(callbackResponse.headers.get("cache-control")).toBe("no-store");
    expect(callbackResponse.headers.get("referrer-policy")).toBe("no-referrer");
    expect(await callbackResponse.text()).toBe("");
    expect(fetchMock).toHaveBeenCalledTimes(14);

    const receiptResponse = await worker.fetch(new Request("https://callback.example.workers.dev/receipt"), env(kv));
    expect(receiptResponse.status).toBe(200);
    const receipt = await receiptResponse.json();
    expect(receipt).toEqual({
      schema_version: 1,
      complete: true,
      passed: true,
      claim: { status: 200, ok: true },
      claim_replay: { status: 409, ok: true },
      account: { status: 200, ok: true },
      csrf_missing: { status: 403, ok: true },
      csrf_invalid: { status: 403, ok: true },
      portal: { status: 200, ok: true, stripe_url: true },
      browser_enrollment_token: { status: 201, ok: true },
      agent_enrollment: { status: 201, ok: true },
      enrollment_replay: { status: 409, ok: true },
      heartbeat_first: { status: 202, ok: true },
      heartbeat_duplicate: { status: 200, ok: true },
      fleet: { status: 200, ok: true, agent_present: true },
      logout: { status: 204, ok: true },
      post_logout_denied: { status: 401, ok: true },
      plan: "starter",
      entitlement: "active",
      host_limit: 1,
    });

    expect(kv.writes.length).toBe(2);
    expect(kv.writes.every((write) => write.ttl === 900)).toBe(true);
    const persisted = kv.writes.map((write) => write.value).join("\n");
    for (const forbidden of Object.values(sensitive)) expect(persisted).not.toContain(forbidden);
    expect(persisted).not.toContain("tenant");
    expect(persisted).not.toContain("hostname");
    expect(persisted).not.toContain("url\":\"https://");
  });

  it("records a fail-closed redacted receipt when a response shape is unsafe", async () => {
    const kv = new FakeKv();
    installSuccessfulControlPlane();
    const baseFetch = globalThis.fetch;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = new Request(input, init);
      if (new URL(request.url).pathname === "/v1/billing/portal" && request.headers.get("x-csrf-token") === sensitive.csrf) {
        return response({ portal_url: "https://evil.example/private-capability" }, 200);
      }
      return baseFetch(input, init);
    }));

    const result = await worker.fetch(
      new Request(`https://callback.example.workers.dev/claim?claim_nonce=${sensitive.claimNonce}`),
      env(kv),
    );
    expect(result.status).toBe(303);
    const receipt = JSON.parse(kv.value ?? "null");
    expect(receipt.complete).toBe(true);
    expect(receipt.passed).toBe(false);
    expect(receipt.portal).toEqual({ status: 200, ok: false, stripe_url: false });
    expect(kv.value).not.toContain("evil.example");
    expect(kv.value).not.toContain(sensitive.claimNonce);
  });

  it("does not call the control plane for malformed callback material", async () => {
    const kv = new FakeKv();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const result = await worker.fetch(new Request("https://callback.example.workers.dev/claim?claim_nonce=short"), env(kv));
    expect(result.status).toBe(303);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(JSON.parse(kv.value ?? "null")).toEqual({ schema_version: 1, complete: true, passed: false });
  });

  it("fails closed before fetch when the control-plane origin is not exact staging", async () => {
    const kv = new FakeKv();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const badEnv: Env = {
      CONTROL_PLANE_BASE: "https://staging-api.agentpulse.ca.evil.example",
      RECEIPTS: kv as unknown as KVNamespace,
    };

    const result = await worker.fetch(
      new Request(`https://callback.example.workers.dev/claim?claim_nonce=${sensitive.claimNonce}`),
      badEnv,
    );
    expect(result.status).toBe(303);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(JSON.parse(kv.value ?? "null")).toEqual({ schema_version: 1, complete: true, passed: false });
  });

  it("uses the edge cache when no KV binding is configured", async () => {
    let stored: Response | undefined;
    vi.stubGlobal("caches", {
      default: {
        put: async (_request: Request, response: Response) => { stored = response.clone(); },
        match: async () => stored ? stored.clone() : null,
      },
    });
    const cacheEnv: Env = { CONTROL_PLANE_BASE: "https://staging-api.agentpulse.ca" };

    const empty = await worker.fetch(new Request("https://callback.example.workers.dev/receipt"), cacheEnv);
    expect(empty.status).toBe(202);
    const claim = await worker.fetch(
      new Request("https://callback.example.workers.dev/claim?claim_nonce=short"),
      cacheEnv,
    );
    expect(claim.status).toBe(303);
    expect(stored?.headers.get("Cache-Control")).toBe("public, max-age=900");
    const receipt = await worker.fetch(new Request("https://callback.example.workers.dev/receipt"), cacheEnv);
    expect(receipt.status).toBe(200);
    expect(await receipt.json()).toEqual({ schema_version: 1, complete: true, passed: false });
  });

  it("exposes only GET /claim and read-only /receipt", async () => {
    const kv = new FakeKv();

    const unknown = await worker.fetch(new Request("https://callback.example.workers.dev/health"), env(kv));
    expect(unknown.status).toBe(404);

    const claimPost = await worker.fetch(new Request("https://callback.example.workers.dev/claim", { method: "POST" }), env(kv));
    expect(claimPost.status).toBe(405);

    const emptyReceipt = await worker.fetch(new Request("https://callback.example.workers.dev/receipt"), env(kv));
    expect(emptyReceipt.status).toBe(202);
    expect(await emptyReceipt.json()).toEqual({ schema_version: 1, complete: false, passed: false });

    const receiptPost = await worker.fetch(new Request("https://callback.example.workers.dev/receipt", { method: "POST" }), env(kv));
    expect(receiptPost.status).toBe(405);
  });
});
