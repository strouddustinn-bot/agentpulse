export interface Env {
  CONTROL_PLANE_BASE: string;
  RECEIPTS?: KVNamespace;
}

type Check = { status: number; ok: boolean };

type Receipt = {
  schema_version: 1;
  complete: boolean;
  passed: boolean;
  claim?: Check;
  claim_replay?: Check;
  account?: Check;
  csrf_missing?: Check;
  csrf_invalid?: Check;
  portal?: Check & { stripe_url: boolean };
  browser_enrollment_token?: Check;
  agent_enrollment?: Check;
  enrollment_replay?: Check;
  heartbeat_first?: Check;
  heartbeat_duplicate?: Check;
  fleet?: Check & { agent_present: boolean };
  logout?: Check;
  post_logout_denied?: Check;
  plan?: string;
  entitlement?: string;
  host_limit?: number;
};

type JsonRecord = Record<string, unknown>;

const RECEIPT_KEY = "latest";
const RECEIPT_TTL_SECONDS = 900;
const API_TIMEOUT_MS = 15_000;
const JSON_HEADERS = { Accept: "application/json", "Content-Type": "application/json" };

class LifecycleFailure extends Error {}

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "application/json; charset=utf-8",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

function asObject(value: unknown): JsonRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new LifecycleFailure();
  return value as JsonRecord;
}

function requiredString(value: unknown): string {
  if (typeof value !== "string" || value.length === 0) throw new LifecycleFailure();
  return value;
}

function requiredNumber(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new LifecycleFailure();
  return value;
}

function controlPlaneBase(env: Env): string {
  const url = new URL(env.CONTROL_PLANE_BASE);
  if (url.protocol !== "https:" || url.hostname !== "staging-api.agentpulse.ca" || url.username || url.password || url.search || url.hash) {
    throw new LifecycleFailure();
  }
  return url.origin;
}

async function api(env: Env, path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${controlPlaneBase(env)}${path}`, {
    ...init,
    redirect: "manual",
    signal: AbortSignal.timeout(API_TIMEOUT_MS),
  });
}

async function readJson(response: Response): Promise<JsonRecord> {
  return asObject(await response.json());
}

function check(receipt: Receipt, key: keyof Receipt, response: Response, expectedStatus: number): void {
  const ok = response.status === expectedStatus;
  (receipt as Record<string, unknown>)[key] = { status: response.status, ok };
  if (!ok) throw new LifecycleFailure();
}

function validateStripePortalUrl(value: unknown): boolean {
  try {
    const url = new URL(requiredString(value));
    return url.protocol === "https:" && !url.username && !url.password &&
      (url.hostname === "billing.stripe.com" || url.hostname.endsWith(".stripe.com"));
  } catch {
    return false;
  }
}

function cookiePair(response: Response): string {
  const setCookie = requiredString(response.headers.get("set-cookie"));
  const pair = setCookie.split(";", 1)[0]?.trim() ?? "";
  if (!pair.startsWith("ap_session=")) {
    throw new LifecycleFailure();
  }
  return pair;
}

function receiptCacheKey(request: Request): Request {
  return new Request(new URL("/receipt", request.url), { method: "GET" });
}

async function saveReceipt(request: Request, env: Env, receipt: Receipt): Promise<void> {
  const body = JSON.stringify(receipt);
  if (env.RECEIPTS) {
    await env.RECEIPTS.put(RECEIPT_KEY, body, { expirationTtl: RECEIPT_TTL_SECONDS });
    return;
  }
  const edgeCache = (caches as unknown as { default: Cache }).default;
  await edgeCache.put(receiptCacheKey(request), new Response(body, {
    headers: {
      "Cache-Control": `public, max-age=${RECEIPT_TTL_SECONDS}`,
      "Content-Type": "application/json; charset=utf-8",
    },
  }));
}

async function readReceipt(request: Request, env: Env): Promise<string | null> {
  if (env.RECEIPTS) return env.RECEIPTS.get(RECEIPT_KEY);
  const edgeCache = (caches as unknown as { default: Cache }).default;
  const cached = await edgeCache.match(receiptCacheKey(request));
  return cached == null ? null : cached.text();
}

async function runLifecycle(request: Request, env: Env, claimNonce: string): Promise<void> {
  const receipt: Receipt = { schema_version: 1, complete: false, passed: false };
  await saveReceipt(request, env, receipt);
  const origin = new URL(request.url).origin;
  const originHeaders = { ...JSON_HEADERS, Origin: origin };
  const claimBody = JSON.stringify({ claim_nonce: claimNonce });

  try {
    const claimResponse = await api(env, "/v1/onboarding/claim", {
      method: "POST",
      headers: originHeaders,
      body: claimBody,
    });
    check(receipt, "claim", claimResponse, 200);
    const claim = await readJson(claimResponse);
    const csrfToken = requiredString(claim.csrf_token);
    const account = asObject(claim.account);
    const plan = requiredString(account.plan);
    const entitlement = requiredString(account.entitlement_status);
    const hostLimit = requiredNumber(account.agent_limit);
    if (!Number.isInteger(hostLimit) || hostLimit < 1 || !["active", "grace"].includes(entitlement)) {
      receipt.claim = { status: claimResponse.status, ok: false };
      throw new LifecycleFailure();
    }
    const cookie = cookiePair(claimResponse);
    receipt.plan = plan;
    receipt.entitlement = entitlement;
    receipt.host_limit = hostLimit;

    const claimReplay = await api(env, "/v1/onboarding/claim", {
      method: "POST",
      headers: originHeaders,
      body: claimBody,
    });
    check(receipt, "claim_replay", claimReplay, 409);

    const accountResponse = await api(env, "/v1/account", {
      headers: { Accept: "application/json", Cookie: cookie },
    });
    check(receipt, "account", accountResponse, 200);
    const accountRead = await readJson(accountResponse);
    if (accountRead.plan !== plan || accountRead.entitlement_status !== entitlement || accountRead.agent_limit !== hostLimit) {
      receipt.account = { status: accountResponse.status, ok: false };
      throw new LifecycleFailure();
    }

    const missingCsrf = await api(env, "/v1/billing/portal", {
      method: "POST",
      headers: { ...JSON_HEADERS, Cookie: cookie, Origin: origin },
      body: "{}",
    });
    check(receipt, "csrf_missing", missingCsrf, 403);

    const invalidCsrf = await api(env, "/v1/billing/portal", {
      method: "POST",
      headers: { ...JSON_HEADERS, Cookie: cookie, Origin: origin, "X-CSRF-Token": "invalid" },
      body: "{}",
    });
    check(receipt, "csrf_invalid", invalidCsrf, 403);

    const mutationHeaders = {
      ...JSON_HEADERS,
      Cookie: cookie,
      Origin: origin,
      "X-CSRF-Token": csrfToken,
    };
    const portalResponse = await api(env, "/v1/billing/portal", {
      method: "POST",
      headers: mutationHeaders,
      body: "{}",
    });
    const portalOk = portalResponse.status === 200;
    receipt.portal = { status: portalResponse.status, ok: false, stripe_url: false };
    if (!portalOk) throw new LifecycleFailure();
    const portal = await readJson(portalResponse);
    const stripeUrl = validateStripePortalUrl(portal.portal_url);
    receipt.portal = { status: portalResponse.status, ok: stripeUrl, stripe_url: stripeUrl };
    if (!stripeUrl) throw new LifecycleFailure();

    const enrollmentTokenResponse = await api(env, "/v1/browser/enrollment-tokens", {
      method: "POST",
      headers: mutationHeaders,
      body: JSON.stringify({ ttl_seconds: 300 }),
    });
    check(receipt, "browser_enrollment_token", enrollmentTokenResponse, 201);
    const enrollment = await readJson(enrollmentTokenResponse);
    const enrollmentToken = requiredString(enrollment.enrollment_token);

    const proofSuffix = crypto.randomUUID().replaceAll("-", "").slice(0, 16);
    const agentKey = `agentpulse-proof-${proofSuffix}`;
    const hostname = `agentpulse-proof-host-${proofSuffix}`;
    const enrollBody = JSON.stringify({ agent_key: agentKey, hostname, local_policy_ceiling: "alert" });
    const enrollmentHeaders = { ...JSON_HEADERS, Authorization: `Bearer ${enrollmentToken}` };
    const agentResponse = await api(env, "/v1/agents/enroll", {
      method: "POST",
      headers: enrollmentHeaders,
      body: enrollBody,
    });
    check(receipt, "agent_enrollment", agentResponse, 201);
    const agent = await readJson(agentResponse);
    const agentCredential = requiredString(agent.agent_credential);
    if (agent.agent_key !== agentKey) {
      receipt.agent_enrollment = { status: agentResponse.status, ok: false };
      throw new LifecycleFailure();
    }

    const enrollmentReplay = await api(env, "/v1/agents/enroll", {
      method: "POST",
      headers: enrollmentHeaders,
      body: enrollBody,
    });
    check(receipt, "enrollment_replay", enrollmentReplay, 409);

    const idempotencyKey = `agentpulse-proof-${crypto.randomUUID()}`;
    const heartbeatBody = JSON.stringify({
      idempotency_key: idempotencyKey,
      observed_at: Math.floor(Date.now() / 1000),
      summary: { observations: 1, breaches: 0 },
      incidents: [],
    });
    const heartbeatHeaders = { ...JSON_HEADERS, Authorization: `Bearer ${agentCredential}` };
    const firstHeartbeat = await api(env, "/v1/agents/heartbeat", {
      method: "POST",
      headers: heartbeatHeaders,
      body: heartbeatBody,
    });
    check(receipt, "heartbeat_first", firstHeartbeat, 202);

    const duplicateHeartbeat = await api(env, "/v1/agents/heartbeat", {
      method: "POST",
      headers: heartbeatHeaders,
      body: heartbeatBody,
    });
    check(receipt, "heartbeat_duplicate", duplicateHeartbeat, 200);

    const fleetResponse = await api(env, "/v1/fleet", {
      headers: { Accept: "application/json", Cookie: cookie },
    });
    receipt.fleet = { status: fleetResponse.status, ok: false, agent_present: false };
    if (fleetResponse.status !== 200) throw new LifecycleFailure();
    const fleet = await readJson(fleetResponse);
    if (!Array.isArray(fleet.agents)) throw new LifecycleFailure();
    const agentPresent = fleet.agents.some((value) => {
      try {
        return asObject(value).agent_key === agentKey;
      } catch {
        return false;
      }
    });
    receipt.fleet = { status: fleetResponse.status, ok: agentPresent, agent_present: agentPresent };
    if (!agentPresent) throw new LifecycleFailure();

    const logoutResponse = await api(env, "/v1/session", {
      method: "DELETE",
      headers: mutationHeaders,
    });
    check(receipt, "logout", logoutResponse, 204);

    const deniedResponse = await api(env, "/v1/account", {
      headers: { Accept: "application/json", Cookie: cookie },
    });
    check(receipt, "post_logout_denied", deniedResponse, 401);

    receipt.passed = true;
  } catch {
    receipt.passed = false;
  } finally {
    receipt.complete = true;
    await saveReceipt(request, env, receipt);
  }
}

async function handleClaim(request: Request, env: Env): Promise<Response> {
  if (request.method !== "GET") return json({ complete: false, passed: false, schema_version: 1 }, 405);
  const nonce = new URL(request.url).searchParams.get("claim_nonce") ?? "";
  if (nonce.length >= 16 && nonce.length <= 512) {
    await runLifecycle(request, env, nonce);
  } else {
    await saveReceipt(request, env, { schema_version: 1, complete: true, passed: false });
  }
  return new Response(null, {
    status: 303,
    headers: {
      "Cache-Control": "no-store",
      Location: "/receipt",
      "Referrer-Policy": "no-referrer",
    },
  });
}

async function handleReceipt(request: Request, env: Env): Promise<Response> {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return json({ schema_version: 1, complete: false, passed: false }, 405);
  }
  const value = await readReceipt(request, env);
  const body = value ?? JSON.stringify({ schema_version: 1, complete: false, passed: false });
  return new Response(request.method === "HEAD" ? null : body, {
    status: value === null ? 202 : 200,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "application/json; charset=utf-8",
      "Referrer-Policy": "no-referrer",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const pathname = new URL(request.url).pathname;
    if (pathname === "/claim") return handleClaim(request, env);
    if (pathname === "/receipt") return handleReceipt(request, env);
    return json({ schema_version: 1, complete: false, passed: false }, 404);
  },
};
