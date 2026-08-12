type WorkerEnv = Env & {
  STRIPE_WEBHOOK_SECRET: string;
  STRIPE_API_KEY: string;
};

type Mode = "off" | "alert" | "ask" | "auto";
type Plan = "starter" | "pro" | "business";
type EntitlementStatus = "active" | "grace" | "blocked";
type CheckoutStatus = "pending" | "ready" | "claimed" | "expired" | "canceled";
type WebhookLease = { eventId: string; token: string };

const MAX_BODY_BYTES = 65_536;
const HOSTED_OK = new Set<EntitlementStatus>(["active", "grace"]);
const MODE_RANK: Record<Mode, number> = { off: 0, alert: 1, ask: 2, auto: 3 };
const PLAN_LIMITS: Record<Plan, number> = { starter: 1, pro: 5, business: 20 };
const GRACE_SECONDS = 3 * 24 * 60 * 60;
const SESSION_TTL_SECONDS = 12 * 60 * 60;
const CHECKOUT_TTL_SECONDS = 30 * 60;
const WEBHOOK_STALE_SECONDS = 5 * 60;
const SESSION_COOKIE = "ap_session";

class HttpError extends Error {
  constructor(readonly status: number, readonly code: string, message: string) {
    super(message);
  }
}

function responseJson(value: unknown, status = 200, headers: HeadersInit = {}): Response {
  return Response.json(value, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      ...headers,
    },
  });
}

function failure(status: number, code: string, message: string): Response {
  return responseJson({ error: { code, message } }, status);
}

function appOrigin(env: WorkerEnv): string {
  try {
    const configured = new URL(env.APP_BASE_URL);
    const isHttp = configured.protocol === "http:" || configured.protocol === "https:";
    const hasOriginOnly = configured.pathname === "/" && configured.search === "" && configured.hash === "";
    if (!isHttp || configured.username !== "" || configured.password !== "" || !hasOriginOnly) throw new Error();
    return configured.origin;
  } catch {
    throw new HttpError(500, "configuration_error", "APP_BASE_URL must be an absolute HTTP(S) origin");
  }
}

function trustedCorsOrigin(env: WorkerEnv, origin: string | null): string | null {
  if (origin === null) return null;
  try {
    const parsed = new URL(origin);
    if (parsed.origin !== origin) return null;
    return parsed.origin === appOrigin(env) ? parsed.origin : null;
  } catch {
    return null;
  }
}

function appendVary(headers: Headers, value: string): void {
  const values = (headers.get("Vary") ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  if (!values.some((item) => item.toLowerCase() === value.toLowerCase())) values.push(value);
  headers.set("Vary", values.join(", "));
}

function withCors(response: Response, env: WorkerEnv, request: Request): Response {
  if (request.headers.get("Origin") === null) return response;
  const headers = new Headers(response.headers);
  appendVary(headers, "Origin");
  const origin = trustedCorsOrigin(env, request.headers.get("Origin"));
  if (origin !== null) {
    headers.set("Access-Control-Allow-Origin", origin);
    headers.set("Access-Control-Allow-Credentials", "true");
  }
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

function preflight(request: Request, env: WorkerEnv): Response {
  const origin = trustedCorsOrigin(env, request.headers.get("Origin"));
  const requestedMethod = request.headers.get("Access-Control-Request-Method")?.toUpperCase() ?? "";
  const allowedMethods = new Set(["GET", "POST", "DELETE"]);
  const allowedHeaders = new Set(["accept", "content-type", "x-csrf-token"]);
  const requestedHeaders = (request.headers.get("Access-Control-Request-Headers") ?? "")
    .split(",")
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);
  if (origin === null || !allowedMethods.has(requestedMethod) || requestedHeaders.some((value) => !allowedHeaders.has(value))) {
    return new Response(null, { status: 403, headers: { Vary: "Origin" } });
  }
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Credentials": "true",
      "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
      "Access-Control-Allow-Headers": "Accept, Content-Type, X-CSRF-Token",
      "Access-Control-Max-Age": "600",
      Vary: "Origin",
    },
  });
}

function bearer(request: Request): string {
  const value = request.headers.get("Authorization") ?? "";
  if (!value.startsWith("Bearer ") || value.length <= 7) {
    throw new HttpError(401, "unauthorized", "A bearer credential is required");
  }
  return value.slice(7);
}

function hex(buffer: ArrayBuffer): string {
  return [...new Uint8Array(buffer)]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

async function sha256(value: string | Uint8Array): Promise<string> {
  const bytes = typeof value === "string" ? new TextEncoder().encode(value) : Uint8Array.from(value);
  return hex(await crypto.subtle.digest("SHA-256", bytes));
}

function secureToken(prefix: string): string {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  const encoded = btoa(String.fromCharCode(...bytes))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replaceAll("=", "");
  return `${prefix}${encoded}`;
}

async function readBody(request: Request): Promise<Uint8Array> {
  const contentLength = request.headers.get("Content-Length");
  if (contentLength !== null) {
    const parsed = Number(contentLength);
    if (Number.isFinite(parsed) && parsed > MAX_BODY_BYTES) {
      throw new HttpError(413, "payload_too_large", "Request body exceeds 65536 bytes");
    }
  }
  if (request.body === null) return new Uint8Array();
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const item = await reader.read();
      if (item.done) break;
      total += item.value.byteLength;
      if (total > MAX_BODY_BYTES) {
        await reader.cancel();
        throw new HttpError(413, "payload_too_large", "Request body exceeds 65536 bytes");
      }
      chunks.push(item.value);
    }
  } finally {
    reader.releaseLock();
  }
  const output = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return output;
}

function parseJson(bytes: Uint8Array): unknown {
  try {
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    throw new HttpError(400, "invalid_json", "Request body must be valid JSON");
  }
}

function objectValue(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new HttpError(422, "invalid_payload", "Request body must be a JSON object");
  }
  return value as Record<string, unknown>;
}

function stringField(value: unknown, name: string, max: number): string {
  if (typeof value !== "string") {
    throw new HttpError(422, "invalid_payload", `${name} must be a non-empty string of at most ${max} characters`);
  }
  const normalized = value.trim();
  if (normalized.length < 1 || normalized.length > max || normalized !== value) {
    throw new HttpError(422, "invalid_payload", `${name} must be a trimmed, non-empty string of at most ${max} characters`);
  }
  return value;
}

function isPlan(value: unknown): value is Plan {
  return value === "starter" || value === "pro" || value === "business";
}

function isMode(value: unknown): value is Mode {
  return typeof value === "string" && value in MODE_RANK;
}

function isHostedOk(status: string): status is EntitlementStatus {
  return HOSTED_OK.has(status as EntitlementStatus);
}

function planPriceId(env: WorkerEnv, plan: Plan): string {
  const map: Record<Plan, string> = {
    starter: env.STRIPE_PRICE_STARTER,
    pro: env.STRIPE_PRICE_PRO,
    business: env.STRIPE_PRICE_BUSINESS,
  };
  return (map[plan] ?? "").trim();
}

function planFromPriceId(env: WorkerEnv, priceId: string): Plan | null {
  if (priceId && priceId === env.STRIPE_PRICE_STARTER) return "starter";
  if (priceId && priceId === env.STRIPE_PRICE_PRO) return "pro";
  if (priceId && priceId === env.STRIPE_PRICE_BUSINESS) return "business";
  return null;
}

/** First subscription item from a Stripe Subscription object, if present. */
function stripeSubscriptionFirstItem(sub: Record<string, unknown>): Record<string, unknown> | null {
  if (typeof sub.items !== "object" || sub.items === null) return null;
  const items = sub.items as Record<string, unknown>;
  if (!Array.isArray(items.data) || items.data.length === 0) return null;
  const first = items.data[0];
  return typeof first === "object" && first !== null ? first as Record<string, unknown> : null;
}

/**
 * Billing period end for a Stripe Subscription.
 * Pre-Basil APIs expose current_period_end on the subscription; Basil+ moved it
 * onto subscription items. Accept either shape.
 * When `now` is provided, only future timestamps are accepted (claim path).
 * When omitted, any finite timestamp is accepted (lifecycle webhook path).
 */
function stripeSubscriptionPeriodEnd(sub: Record<string, unknown>, now?: number): number | null {
  const candidates: unknown[] = [sub.current_period_end];
  const firstItem = stripeSubscriptionFirstItem(sub);
  if (firstItem !== null) candidates.push(firstItem.current_period_end);
  for (const value of candidates) {
    if (typeof value === "number" && Number.isFinite(value)) {
      const period = Math.floor(value);
      if (now === undefined || period > now) return period;
    }
  }
  return null;
}

/** Canonical price id from a Stripe Subscription (items.data[0].price.id). */
function stripeSubscriptionPriceId(sub: Record<string, unknown>): string {
  const firstItem = stripeSubscriptionFirstItem(sub);
  if (firstItem === null) return "";
  if (typeof firstItem.price === "object" && firstItem.price !== null) {
    const price = firstItem.price as Record<string, unknown>;
    if (typeof price.id === "string") return price.id;
  }
  if (typeof firstItem.price === "string") return firstItem.price;
  return "";
}

/**
 * Subscription id referenced by a Stripe Invoice.
 * Classic APIs use invoice.subscription; Basil+ nests it under
 * parent.subscription_details.subscription (and sometimes subscription_details).
 */
function stripeInvoiceSubscriptionId(item: Record<string, unknown>): string {
  if (typeof item.subscription === "string" && item.subscription.length > 0) {
    return item.subscription;
  }
  const nestedRoots: unknown[] = [item.parent, item.subscription_details];
  for (const root of nestedRoots) {
    if (typeof root !== "object" || root === null) continue;
    const obj = root as Record<string, unknown>;
    if (typeof obj.subscription === "string" && obj.subscription.length > 0) {
      return obj.subscription;
    }
    if (typeof obj.subscription_details === "object" && obj.subscription_details !== null) {
      const details = obj.subscription_details as Record<string, unknown>;
      if (typeof details.subscription === "string" && details.subscription.length > 0) {
        return details.subscription;
      }
    }
  }
  return "";
}

function entitlementFromStripeStatus(status: string, graceEndsAt: number | null, now: number): EntitlementStatus {
  if (status === "active" || status === "trialing") return "active";
  if (status === "past_due" && graceEndsAt !== null && graceEndsAt > now) return "grace";
  return "blocked";
}

function entitlementRank(status: EntitlementStatus): number {
  if (status === "blocked") return 2;
  if (status === "grace") return 1;
  return 0;
}

const SUMMARY_COUNTERS = [
  "observations",
  "breaches",
  "actions",
  "queued",
  "alerts",
  "anomalies",
  "escalations",
  "blocked",
] as const;

function validateSummary(summary: Record<string, unknown>): void {
  for (const field of SUMMARY_COUNTERS) {
    const value = summary[field];
    if (value !== undefined && (typeof value !== "number" || !Number.isInteger(value) || value < 0)) {
      throw new HttpError(422, "invalid_payload", `summary.${field} must be a nonnegative integer`);
    }
  }
  const errors = summary.errors;
  if (errors !== undefined && (!Array.isArray(errors) || !errors.every((error) => typeof error === "string"))) {
    throw new HttpError(422, "invalid_payload", "summary.errors must be an array of strings");
  }
}

interface AccountAuth {
  credentialId: string;
  tenantId: string;
  entitlementStatus: EntitlementStatus;
  agentLimit: number;
}

async function accountAuth(request: Request, env: WorkerEnv): Promise<AccountAuth> {
  const hash = await sha256(bearer(request));
  const row = await env.DB.prepare(
    "SELECT c.id AS credential_id,c.tenant_id,s.entitlement_status,s.agent_limit,s.grace_period_ends_at " +
      "FROM account_credentials c JOIN subscriptions s ON s.tenant_id=c.tenant_id " +
      "WHERE c.credential_hash=? AND c.revoked_at IS NULL ORDER BY s.updated_at DESC LIMIT 1",
  ).bind(hash).first<{
    credential_id: string;
    tenant_id: string;
    entitlement_status: string;
    agent_limit: number;
    grace_period_ends_at: number | null;
  }>();
  if (row === null) throw new HttpError(401, "invalid_credential", "Account credential is invalid");
  const now = Math.floor(Date.now() / 1000);
  const entitlement = refreshEntitlement(row.entitlement_status, row.grace_period_ends_at, now);
  if (!isHostedOk(entitlement)) {
    throw new HttpError(402, "subscription_inactive", "An active subscription is required");
  }
  return {
    credentialId: row.credential_id,
    tenantId: row.tenant_id,
    entitlementStatus: entitlement,
    agentLimit: row.agent_limit,
  };
}

function refreshEntitlement(status: string, graceEndsAt: number | null, now: number): EntitlementStatus {
  if (status === "grace" && (graceEndsAt === null || graceEndsAt <= now)) return "blocked";
  if (status === "active" || status === "grace" || status === "blocked") return status;
  return "blocked";
}

interface AgentAuth {
  id: string;
  tenantId: string;
  agentKey: string;
  localCeiling: Mode;
  entitlementStatus: EntitlementStatus;
}

async function agentAuth(request: Request, env: WorkerEnv): Promise<AgentAuth> {
  const hash = await sha256(bearer(request));
  const row = await env.DB.prepare(
    "SELECT a.id,a.tenant_id,a.agent_key,a.local_policy_ceiling,s.entitlement_status,s.grace_period_ends_at " +
      "FROM agents a JOIN subscriptions s ON s.tenant_id=a.tenant_id " +
      "WHERE a.credential_hash=? AND a.revoked_at IS NULL ORDER BY s.updated_at DESC LIMIT 1",
  ).bind(hash).first<{
    id: string;
    tenant_id: string;
    agent_key: string;
    local_policy_ceiling: string;
    entitlement_status: string;
    grace_period_ends_at: number | null;
  }>();
  if (row === null || !isMode(row.local_policy_ceiling)) {
    throw new HttpError(401, "invalid_credential", "Agent credential is invalid");
  }
  const now = Math.floor(Date.now() / 1000);
  const entitlement = refreshEntitlement(row.entitlement_status, row.grace_period_ends_at, now);
  if (!isHostedOk(entitlement)) {
    throw new HttpError(402, "subscription_inactive", "An active subscription is required");
  }
  return {
    id: row.id,
    tenantId: row.tenant_id,
    agentKey: row.agent_key,
    localCeiling: row.local_policy_ceiling,
    entitlementStatus: entitlement,
  };
}

function cookieValue(request: Request, name: string): string | null {
  const header = request.headers.get("Cookie");
  if (!header) return null;
  for (const part of header.split(";")) {
    const trimmed = part.trim();
    const eq = trimmed.indexOf("=");
    if (eq < 1) continue;
    if (trimmed.slice(0, eq) === name) return decodeURIComponent(trimmed.slice(eq + 1));
  }
  return null;
}

function sessionCookie(token: string, env: WorkerEnv, maxAge: number): string {
  const parts = [
    `${SESSION_COOKIE}=${encodeURIComponent(token)}`,
    "HttpOnly",
    "Path=/",
    "SameSite=Lax",
    `Max-Age=${maxAge}`,
  ];
  if (env.ENVIRONMENT !== "development") parts.push("Secure");
  return parts.join("; ");
}

function clearSessionCookie(env: WorkerEnv): string {
  const parts = [`${SESSION_COOKIE}=`, "HttpOnly", "Path=/", "SameSite=Lax", "Max-Age=0"];
  if (env.ENVIRONMENT !== "development") parts.push("Secure");
  return parts.join("; ");
}

interface BrowserAuth {
  sessionId: string;
  tenantId: string;
  csrfHash: string;
  entitlementStatus: EntitlementStatus;
  agentLimit: number;
  email: string;
  plan: Plan;
  currentPeriodEnd: number | null;
  gracePeriodEndsAt: number | null;
}

async function browserAuth(request: Request, env: WorkerEnv): Promise<BrowserAuth> {
  const token = cookieValue(request, SESSION_COOKIE);
  if (!token || token.length < 16) throw new HttpError(401, "unauthorized", "Browser session is required");
  const hash = await sha256(token);
  const now = Math.floor(Date.now() / 1000);
  const row = await env.DB.prepare(
    "SELECT b.id,b.tenant_id,b.csrf_token_hash,b.expires_at,b.revoked_at,t.email,s.plan,s.entitlement_status," +
      "s.agent_limit,s.current_period_end,s.grace_period_ends_at " +
      "FROM browser_sessions b JOIN tenants t ON t.id=b.tenant_id " +
      "JOIN subscriptions s ON s.tenant_id=b.tenant_id " +
      "WHERE b.session_hash=? ORDER BY s.updated_at DESC LIMIT 1",
  ).bind(hash).first<{
    id: string;
    tenant_id: string;
    csrf_token_hash: string;
    expires_at: number;
    revoked_at: number | null;
    email: string;
    plan: string;
    entitlement_status: string;
    agent_limit: number;
    current_period_end: number | null;
    grace_period_ends_at: number | null;
  }>();
  if (row === null || row.revoked_at !== null || row.expires_at < now || !isPlan(row.plan)) {
    throw new HttpError(401, "unauthorized", "Browser session is invalid or expired");
  }
  await env.DB.prepare("UPDATE browser_sessions SET last_seen_at=? WHERE id=? AND tenant_id=?")
    .bind(now, row.id, row.tenant_id).run();
  return {
    sessionId: row.id,
    tenantId: row.tenant_id,
    csrfHash: row.csrf_token_hash,
    entitlementStatus: refreshEntitlement(row.entitlement_status, row.grace_period_ends_at, now),
    agentLimit: row.agent_limit,
    email: row.email,
    plan: row.plan,
    currentPeriodEnd: row.current_period_end,
    gracePeriodEndsAt: row.grace_period_ends_at,
  };
}

async function requireCsrf(request: Request, session: BrowserAuth): Promise<void> {
  const token = request.headers.get("X-CSRF-Token") ?? "";
  if (token.length < 16) throw new HttpError(403, "csrf_invalid", "CSRF token is missing or invalid");
  if ((await sha256(token)) !== session.csrfHash) {
    throw new HttpError(403, "csrf_invalid", "CSRF token is missing or invalid");
  }
}

function requireTrustedAppOrigin(request: Request, env: WorkerEnv): void {
  if (trustedCorsOrigin(env, request.headers.get("Origin")) === null) {
    throw new HttpError(403, "origin_untrusted", "Request origin is not trusted");
  }
}

async function requireBrowserMutation(request: Request, env: WorkerEnv): Promise<BrowserAuth> {
  const session = await browserAuth(request, env);
  await requireCsrf(request, session);
  requireTrustedAppOrigin(request, env);
  return session;
}

async function stripeRequest(
  env: WorkerEnv,
  method: string,
  path: string,
  form?: URLSearchParams,
): Promise<Record<string, unknown>> {
  if (!env.STRIPE_API_KEY) throw new HttpError(503, "stripe_unavailable", "Stripe is not configured");
  const headers: Record<string, string> = {
    Authorization: `Bearer ${env.STRIPE_API_KEY}`,
  };
  const init: RequestInit = { method, headers };
  if (form) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    init.body = form.toString();
  }
  const response = await fetch(`https://api.stripe.com/v1${path}`, init);
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new HttpError(503, "stripe_unavailable", "Stripe request failed");
  }
  if (!response.ok) {
    throw new HttpError(503, "stripe_unavailable", "Stripe request failed");
  }
  return objectValue(payload);
}

async function createBillingCheckout(request: Request, env: WorkerEnv): Promise<Response> {
  if (env.CHECKOUT_MODE === "closed") {
    throw new HttpError(404, "not_found", "Route not found");
  }
  if (env.CHECKOUT_MODE !== "public") {
    throw new HttpError(500, "configuration_error", "Checkout mode is invalid");
  }
  const body = objectValue(parseJson(await readBody(request)));
  if (!isPlan(body.plan)) throw new HttpError(422, "invalid_plan", "plan must be starter, pro, or business");
  const priceId = planPriceId(env, body.plan);
  if (!priceId) throw new HttpError(503, "price_unmapped", "Plan is not mapped to a Stripe Price ID");
  const claimNonce = secureToken("ap_claim_");
  const claimHash = await sha256(claimNonce);
  const now = Math.floor(Date.now() / 1000);
  const expiresAt = now + CHECKOUT_TTL_SECONDS;
  const appBase = env.APP_BASE_URL.replace(/\/$/, "");
  const form = new URLSearchParams();
  form.set("mode", "subscription");
  form.set("success_url", `${appBase}/claim?claim_nonce=${encodeURIComponent(claimNonce)}`);
  form.set("cancel_url", `${appBase}/signup?canceled=1`);
  form.set("line_items[0][price]", priceId);
  form.set("line_items[0][quantity]", "1");
  form.set("client_reference_id", claimHash.slice(0, 32));
  form.set("metadata[plan]", body.plan);
  form.set("metadata[claim_nonce_hash]", claimHash);
  form.set("subscription_data[metadata][plan]", body.plan);
  form.set("billing_address_collection", "required");
  form.set("expires_at", String(expiresAt));
  const session = await stripeRequest(env, "POST", "/checkout/sessions", form);
  const checkoutId = stringField(session.id, "checkout.id", 255);
  const livemode = session.livemode === true;
  if (env.ENVIRONMENT === "staging" && (livemode || !checkoutId.startsWith("cs_test_"))) {
    throw new HttpError(503, "stripe_mode_mismatch", "Staging checkout must use a Stripe test-mode Checkout Session");
  }
  const url = stringField(session.url, "checkout.url", 2048);
  const stripeExpires = typeof session.expires_at === "number" ? session.expires_at : expiresAt;
  await env.DB.prepare(
    "INSERT INTO checkout_sessions (stripe_checkout_session_id,claim_nonce_hash,price_id,plan,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?)",
  ).bind(checkoutId, claimHash, priceId, body.plan, "pending", now, stripeExpires).run();
  return responseJson({ checkout_url: url, checkout_session_id: checkoutId, livemode, expires_at: stripeExpires }, 201);
}

async function webhookLeaseOwned(env: WorkerEnv, lease?: WebhookLease): Promise<boolean> {
  if (!lease) return true;
  const timestamp = Math.floor(Date.now() / 1000);
  const row = await env.DB.prepare(
    "SELECT 1 AS owned FROM stripe_events WHERE id=? AND outcome='pending' AND lease_token=? AND COALESCE(lease_expires_at,0)>?",
  ).bind(lease.eventId, lease.token, timestamp).first<{ owned: number }>();
  return row?.owned === 1;
}

async function upsertTenantSubscription(env: WorkerEnv, input: {
  email: string;
  customerId: string;
  subscriptionId: string;
  status: string;
  priceId: string;
  plan: Plan;
  periodEnd: number | null;
  graceEndsAt: number | null;
  eventCreated: number;
  now: number;
}, lease?: WebhookLease): Promise<string> {
  const entitlement = entitlementFromStripeStatus(input.status, input.graceEndsAt, input.now);
  const findByStripeIds = () => env.DB.prepare(
    "SELECT id,tenant_id,stripe_customer_id,stripe_subscription_id FROM subscriptions " +
      "WHERE stripe_subscription_id=? OR stripe_customer_id=?",
  ).bind(input.subscriptionId, input.customerId).all<{
    id: string;
    tenant_id: string;
    stripe_customer_id: string;
    stripe_subscription_id: string;
  }>();
  let subRows = (await findByStripeIds()).results;
  if (subRows.length === 0) {
    const byEmail = await env.DB.prepare("SELECT id FROM tenants WHERE email=? COLLATE NOCASE")
      .bind(input.email).first<{ id: string }>();
    if (byEmail !== null) {
      throw new HttpError(409, "subscription_conflict", "Email already belongs to another account");
    }
    const tenantId = crypto.randomUUID();
    const subscriptionValues = [
      crypto.randomUUID(),
      tenantId,
      input.customerId,
      input.subscriptionId,
      input.status,
      input.priceId,
      input.plan,
      PLAN_LIMITS[input.plan],
      input.periodEnd,
      input.now,
      entitlement,
      input.graceEndsAt,
      input.eventCreated,
    ];
    const tenantInsert = lease
      ? env.DB.prepare(
          "INSERT INTO tenants (id,email,created_at,updated_at) SELECT ?,?,?,? " +
            "WHERE EXISTS (SELECT 1 FROM stripe_events WHERE id=? AND outcome='pending' AND lease_token=?)",
        ).bind(tenantId, input.email, input.now, input.now, lease.eventId, lease.token)
      : env.DB.prepare("INSERT INTO tenants (id,email,created_at,updated_at) VALUES (?,?,?,?)")
        .bind(tenantId, input.email, input.now, input.now);
    const subscriptionInsert = lease
      ? env.DB.prepare(
          "INSERT INTO subscriptions (id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit," +
            "current_period_end,updated_at,entitlement_status,grace_period_ends_at,stripe_event_created_at) " +
            "SELECT ?,?,?,?,?,?,?,?,?,?,?,?,? WHERE EXISTS (SELECT 1 FROM tenants WHERE id=?) " +
            "AND EXISTS (SELECT 1 FROM stripe_events WHERE id=? AND outcome='pending' AND lease_token=?)",
        ).bind(...subscriptionValues, tenantId, lease.eventId, lease.token)
      : env.DB.prepare(
          "INSERT INTO subscriptions (id,tenant_id,stripe_customer_id,stripe_subscription_id,status,price_id,plan,agent_limit," +
            "current_period_end,updated_at,entitlement_status,grace_period_ends_at,stripe_event_created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ).bind(...subscriptionValues);
    try {
      // Plain INSERTs make uniqueness conflicts roll back both rows atomically.
      await env.DB.batch([tenantInsert, subscriptionInsert]);
    } catch {
      // A concurrent exact-identifier event may have won. Re-read below.
    }
    // A same-customer Stripe event may have won the race. Only exact
    // identifier convergence is safe; shared email is never account proof.
    subRows = (await findByStripeIds()).results;
    if (subRows.length === 0 && !(await webhookLeaseOwned(env, lease))) {
      throw new HttpError(409, "event_lease_lost", "Stripe event processing lease was superseded");
    }
  }
  const subRow = subRows[0];
  if (
    subRows.length !== 1 ||
    subRow === undefined ||
    subRow.stripe_customer_id !== input.customerId ||
    subRow.stripe_subscription_id !== input.subscriptionId
  ) {
    throw new HttpError(409, "subscription_conflict", "Stripe subscription identifiers conflict with an existing account");
  }
  const updateSql =
    "UPDATE subscriptions SET status=?,price_id=?,plan=?,agent_limit=?,current_period_end=?," +
      "entitlement_status=?,grace_period_ends_at=?,updated_at=?,stripe_event_created_at=? " +
      "WHERE id=? AND (stripe_event_created_at<? OR (stripe_event_created_at=? AND " +
      "(CASE entitlement_status WHEN 'blocked' THEN 2 WHEN 'grace' THEN 1 ELSE 0 END<? OR " +
      "(CASE entitlement_status WHEN 'blocked' THEN 2 WHEN 'grace' THEN 1 ELSE 0 END=? " +
      "AND (agent_limit>? OR (agent_limit=? AND " +
      "(COALESCE(current_period_end,0)>COALESCE(?,0) OR " +
      "(COALESCE(current_period_end,0)=COALESCE(?,0) AND " +
      "(COALESCE(grace_period_ends_at,0)>COALESCE(?,0) OR " +
      "(COALESCE(grace_period_ends_at,0)=COALESCE(?,0) AND price_id>=?))))))))))" +
      (lease ? " AND EXISTS (SELECT 1 FROM stripe_events WHERE id=? AND outcome='pending' AND lease_token=?)" : "");
  const updateValues: unknown[] = [
    input.status,
    input.priceId,
    input.plan,
    PLAN_LIMITS[input.plan],
    input.periodEnd,
    entitlement,
    input.graceEndsAt,
    input.now,
    input.eventCreated,
    subRow.id,
    input.eventCreated,
    input.eventCreated,
    entitlementRank(entitlement),
    entitlementRank(entitlement),
    PLAN_LIMITS[input.plan],
    PLAN_LIMITS[input.plan],
    input.periodEnd,
    input.periodEnd,
    input.graceEndsAt,
    input.graceEndsAt,
    input.priceId,
  ];
  if (lease) updateValues.push(lease.eventId, lease.token);
  await env.DB.prepare(updateSql).bind(...updateValues).run();
  return subRow.tenant_id;
}

async function markCheckoutReady(
  env: WorkerEnv,
  checkoutId: string,
  tenantId: string,
  now: number,
  lease?: WebhookLease,
): Promise<void> {
  const sql =
    "UPDATE checkout_sessions SET status='ready',tenant_id=?,ready_at=? WHERE stripe_checkout_session_id=? " +
    "AND status IN ('pending','ready')" +
    (lease ? " AND EXISTS (SELECT 1 FROM stripe_events WHERE id=? AND outcome='pending' AND lease_token=?)" : "");
  const values: unknown[] = [tenantId, now, checkoutId];
  if (lease) values.push(lease.eventId, lease.token);
  await env.DB.prepare(sql).bind(...values).run();
}

async function materializePaidCheckout(
  env: WorkerEnv,
  checkoutId: string,
  stripeEventCreated?: number,
  lease?: WebhookLease,
): Promise<{
  tenantId: string;
  plan: Plan;
  email: string;
}> {
  const local = await env.DB.prepare(
    "SELECT stripe_checkout_session_id,claim_nonce_hash,price_id,plan,status,tenant_id,expires_at FROM checkout_sessions WHERE stripe_checkout_session_id=?",
  ).bind(checkoutId).first<{
    stripe_checkout_session_id: string;
    claim_nonce_hash: string;
    price_id: string;
    plan: string;
    status: CheckoutStatus;
    tenant_id: string | null;
    expires_at: number;
  }>();
  if (local === null || !isPlan(local.plan)) throw new HttpError(401, "invalid_claim", "Claim nonce is invalid or unknown");
  const now = Math.floor(Date.now() / 1000);
  const eventCreated = stripeEventCreated ?? now;
  if (local.status === "claimed") throw new HttpError(409, "already_claimed", "Checkout was already claimed");
  if (local.status === "canceled" || local.status === "expired" || local.expires_at < now) {
    throw new HttpError(409, "checkout_unavailable", "Checkout is expired or canceled");
  }
  const session = await stripeRequest(env, "GET", `/checkout/sessions/${encodeURIComponent(checkoutId)}`);
  const paymentStatus = typeof session.payment_status === "string" ? session.payment_status : "";
  const status = typeof session.status === "string" ? session.status : "";
  if (paymentStatus !== "paid" || status !== "complete") {
    throw new HttpError(409, "checkout_incomplete", "Checkout is not yet completed");
  }
  const customerId = typeof session.customer === "string" ? session.customer : "";
  const subscriptionId = typeof session.subscription === "string" ? session.subscription : "";
  if (!customerId || !subscriptionId) throw new HttpError(409, "checkout_incomplete", "Checkout is not yet completed");
  let email = "";
  if (typeof session.customer_details === "object" && session.customer_details !== null) {
    const details = session.customer_details as Record<string, unknown>;
    if (typeof details.email === "string") email = details.email;
  }
  if (!email && typeof session.customer_email === "string") email = session.customer_email;
  if (!email) email = `customer+${customerId.slice(-8)}@users.agentpulse.invalid`;
  const priceId = local.price_id;
  const plan = planFromPriceId(env, priceId);
  if (plan === null) throw new HttpError(503, "price_unmapped", "Plan is not mapped to a Stripe Price ID");
  const sub = await stripeRequest(env, "GET", `/subscriptions/${encodeURIComponent(subscriptionId)}`);
  const canonicalPriceId = stripeSubscriptionPriceId(sub);
  if (
    sub.id !== subscriptionId ||
    sub.customer !== customerId ||
    sub.status !== "active" ||
    canonicalPriceId !== priceId
  ) {
    throw new HttpError(409, "subscription_conflict", "Canonical Stripe subscription does not match the paid checkout");
  }
  const periodEnd = stripeSubscriptionPeriodEnd(sub, now);
  if (periodEnd === null) {
    throw new HttpError(409, "subscription_inactive", "Canonical Stripe subscription period is invalid");
  }
  if (!(await webhookLeaseOwned(env, lease))) {
    throw new HttpError(409, "event_lease_lost", "Stripe event processing lease was superseded");
  }
  const tenantId = await upsertTenantSubscription(env, {
    email,
    customerId,
    subscriptionId,
    status: "active",
    priceId,
    plan,
    periodEnd,
    graceEndsAt: null,
    eventCreated,
    now,
  }, lease);
  await markCheckoutReady(env, checkoutId, tenantId, now, lease);
  return { tenantId, plan, email };
}

async function issueClaimedBrowserSession(
  env: WorkerEnv,
  tenantId: string,
  checkoutId: string,
  credential: { id: string; hash: string | null; prefix: string | null },
  now: number,
): Promise<{
  cookie: string;
  csrfToken: string;
  account: Record<string, unknown>;
}> {
  const sessionToken = secureToken("ap_sess_");
  const csrfToken = secureToken("ap_csrf_");
  const sessionId = crypto.randomUUID();
  const expires = now + SESSION_TTL_SECONDS;
  const statements = [
    env.DB.prepare(
      "UPDATE checkout_sessions SET status='claimed',claimed_at=?,tenant_id=? " +
        "WHERE stripe_checkout_session_id=? AND status='ready' AND tenant_id=?",
    ).bind(now, tenantId, checkoutId, tenantId),
  ];
  if (credential.hash !== null && credential.prefix !== null) {
    statements.push(env.DB.prepare(
      "INSERT INTO account_credentials (id,tenant_id,credential_hash,prefix,created_at) " +
        "SELECT ?,?,?,?,? WHERE EXISTS (SELECT 1 FROM checkout_sessions WHERE stripe_checkout_session_id=? AND status='claimed' AND tenant_id=?)",
    ).bind(credential.id, tenantId, credential.hash, credential.prefix, now, checkoutId, tenantId));
  }
  statements.push(
    env.DB.prepare(
      "INSERT INTO onboarding_claims (checkout_session_id,tenant_id,claimed_at,account_credential_id) " +
        "SELECT ?,?,?,? WHERE EXISTS (SELECT 1 FROM checkout_sessions WHERE stripe_checkout_session_id=? AND status='claimed' AND tenant_id=?)",
    ).bind(checkoutId, tenantId, now, credential.id, checkoutId, tenantId),
    env.DB.prepare(
      "INSERT INTO browser_sessions (id,tenant_id,session_hash,csrf_token_hash,created_at,expires_at,last_seen_at) " +
        "SELECT ?,?,?,?,?,?,? WHERE EXISTS (SELECT 1 FROM onboarding_claims WHERE checkout_session_id=? AND tenant_id=?)",
    ).bind(
      sessionId,
      tenantId,
      await sha256(sessionToken),
      await sha256(csrfToken),
      now,
      expires,
      now,
      checkoutId,
      tenantId,
    ),
  );
  let results: D1Result[];
  try {
    results = await env.DB.batch(statements);
  } catch (error) {
    const checkout = await env.DB.prepare("SELECT status FROM checkout_sessions WHERE stripe_checkout_session_id=?")
      .bind(checkoutId).first<{ status: string }>();
    if (checkout?.status === "claimed") {
      throw new HttpError(409, "already_claimed", "Checkout was already claimed");
    }
    throw error;
  }
  if ((results[0]?.meta.changes ?? 0) !== 1) {
    throw new HttpError(409, "already_claimed", "Checkout was already claimed");
  }
  const account = await env.DB.prepare(
    "SELECT t.id AS tenant_id,t.email,s.plan,s.entitlement_status,s.agent_limit,s.current_period_end,s.grace_period_ends_at " +
      "FROM tenants t JOIN subscriptions s ON s.tenant_id=t.id WHERE t.id=? ORDER BY s.updated_at DESC LIMIT 1",
  ).bind(tenantId).first<{
    tenant_id: string;
    email: string;
    plan: string;
    entitlement_status: string;
    agent_limit: number;
    current_period_end: number | null;
    grace_period_ends_at: number | null;
  }>();
  if (account === null) throw new HttpError(500, "internal_error", "Account materialization failed");
  return {
    cookie: sessionCookie(sessionToken, env, SESSION_TTL_SECONDS),
    csrfToken,
    account: {
      tenant_id: account.tenant_id,
      email: account.email,
      plan: account.plan,
      entitlement_status: refreshEntitlement(account.entitlement_status, account.grace_period_ends_at, now),
      agent_limit: account.agent_limit,
      current_period_end: account.current_period_end,
      grace_period_ends_at: account.grace_period_ends_at,
    },
  };
}

async function claimOnboarding(request: Request, env: WorkerEnv): Promise<Response> {
  requireTrustedAppOrigin(request, env);
  const body = objectValue(parseJson(await readBody(request)));
  const claimNonce = stringField(body.claim_nonce, "claim_nonce", 255);
  if (claimNonce.length < 16) throw new HttpError(422, "invalid_payload", "claim_nonce must be at least 16 characters");
  const claimHash = await sha256(claimNonce);
  const local = await env.DB.prepare(
    "SELECT stripe_checkout_session_id,status FROM checkout_sessions WHERE claim_nonce_hash=?",
  ).bind(claimHash).first<{ stripe_checkout_session_id: string; status: string }>();
  if (local === null) throw new HttpError(401, "invalid_claim", "Claim nonce is invalid or unknown");
  if (local.status === "claimed") throw new HttpError(409, "already_claimed", "Checkout was already claimed");
  const materialized = await materializePaidCheckout(env, local.stripe_checkout_session_id);
  const now = Math.floor(Date.now() / 1000);
  // Ensure an account credential exists for legacy enrollment (server-side only; never returned to browser).
  const existingCred = await env.DB.prepare(
    "SELECT id FROM account_credentials WHERE tenant_id=? AND revoked_at IS NULL LIMIT 1",
  ).bind(materialized.tenantId).first<{ id: string }>();
  let credential: { id: string; hash: string | null; prefix: string | null };
  if (existingCred) {
    credential = { id: existingCred.id, hash: null, prefix: null };
  } else {
    const accountKey = secureToken("ap_account_");
    credential = {
      id: crypto.randomUUID(),
      hash: await sha256(accountKey),
      prefix: accountKey.slice(0, 12),
    };
  }
  const issued = await issueClaimedBrowserSession(
    env,
    materialized.tenantId,
    local.stripe_checkout_session_id,
    credential,
    now,
  );
  return responseJson({ csrf_token: issued.csrfToken, account: issued.account }, 200, {
    "Set-Cookie": issued.cookie,
  });
}

async function getAccount(request: Request, env: WorkerEnv): Promise<Response> {
  const session = await browserAuth(request, env);
  return responseJson({
    tenant_id: session.tenantId,
    email: session.email,
    plan: session.plan,
    entitlement_status: session.entitlementStatus,
    agent_limit: session.agentLimit,
    current_period_end: session.currentPeriodEnd,
    grace_period_ends_at: session.gracePeriodEndsAt,
  });
}

async function refreshSessionCsrf(request: Request, env: WorkerEnv): Promise<Response> {
  if (trustedCorsOrigin(env, request.headers.get("Origin")) === null) {
    throw new HttpError(403, "origin_untrusted", "Request origin is not trusted");
  }
  const session = await browserAuth(request, env);
  const csrfToken = secureToken("ap_csrf_");
  await env.DB.prepare("UPDATE browser_sessions SET csrf_token_hash=? WHERE id=? AND tenant_id=?")
    .bind(await sha256(csrfToken), session.sessionId, session.tenantId).run();
  return responseJson({ csrf_token: csrfToken });
}

async function deleteSession(request: Request, env: WorkerEnv): Promise<Response> {
  const session = await requireBrowserMutation(request, env);
  const now = Math.floor(Date.now() / 1000);
  await env.DB.prepare("UPDATE browser_sessions SET revoked_at=? WHERE id=? AND tenant_id=?")
    .bind(now, session.sessionId, session.tenantId).run();
  return new Response(null, {
    status: 204,
    headers: {
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "Set-Cookie": clearSessionCookie(env),
    },
  });
}

async function createBillingPortal(request: Request, env: WorkerEnv): Promise<Response> {
  const session = await requireBrowserMutation(request, env);
  const sub = await env.DB.prepare(
    "SELECT stripe_customer_id FROM subscriptions WHERE tenant_id=? ORDER BY updated_at DESC LIMIT 1",
  ).bind(session.tenantId).first<{ stripe_customer_id: string }>();
  if (sub === null) throw new HttpError(503, "stripe_unavailable", "Billing portal is unavailable");
  const form = new URLSearchParams();
  form.set("customer", sub.stripe_customer_id);
  form.set("return_url", `${env.APP_BASE_URL.replace(/\/$/, "")}/account`);
  const portal = await stripeRequest(env, "POST", "/billing_portal/sessions", form);
  const url = stringField(portal.url, "portal.url", 2048);
  return responseJson({ portal_url: url });
}

async function createEnrollmentToken(request: Request, env: WorkerEnv): Promise<Response> {
  const account = await accountAuth(request, env);
  return mintEnrollmentToken(request, env, account.tenantId, account.credentialId);
}

async function createBrowserEnrollmentToken(request: Request, env: WorkerEnv): Promise<Response> {
  const session = await requireBrowserMutation(request, env);
  if (!isHostedOk(session.entitlementStatus)) {
    throw new HttpError(402, "subscription_inactive", "An active subscription is required");
  }
  const credential = await env.DB.prepare(
    "SELECT id FROM account_credentials WHERE tenant_id=? AND revoked_at IS NULL LIMIT 1",
  ).bind(session.tenantId).first<{ id: string }>();
  if (credential === null) throw new HttpError(500, "internal_error", "Account credential is unavailable");
  return mintEnrollmentToken(request, env, session.tenantId, credential.id);
}

async function mintEnrollmentToken(
  request: Request,
  env: WorkerEnv,
  tenantId: string,
  credentialId: string,
): Promise<Response> {
  const body = objectValue(parseJson(await readBody(request)));
  const ttl = body.ttl_seconds;
  if (!Number.isInteger(ttl) || typeof ttl !== "number" || ttl < 60 || ttl > 900) {
    throw new HttpError(422, "invalid_ttl", "ttl_seconds must be an integer between 60 and 900");
  }
  const token = secureToken("ap_enroll_");
  const created = Math.floor(Date.now() / 1000);
  const expires = created + ttl;
  await env.DB.prepare(
    "INSERT INTO enrollment_tokens (id,tenant_id,token_hash,created_by_credential_id,created_at,expires_at) VALUES (?,?,?,?,?,?)",
  ).bind(crypto.randomUUID(), tenantId, await sha256(token), credentialId, created, expires).run();
  return responseJson({ enrollment_token: token, expires_at: expires }, 201);
}

async function enrollAgent(request: Request, env: WorkerEnv): Promise<Response> {
  const rawToken = bearer(request);
  const tokenHash = await sha256(rawToken);
  const body = objectValue(parseJson(await readBody(request)));
  const agentKey = stringField(body.agent_key, "agent_key", 128);
  const hostname = stringField(body.hostname, "hostname", 255);
  const ceiling = body.local_policy_ceiling;
  if (!isMode(ceiling)) throw new HttpError(422, "invalid_policy_ceiling", "local_policy_ceiling is invalid");
  const timestamp = Math.floor(Date.now() / 1000);
  const token = await env.DB.prepare(
    "SELECT e.id,e.tenant_id,e.expires_at,e.consumed_at,s.entitlement_status,s.grace_period_ends_at,s.agent_limit FROM enrollment_tokens e " +
      "JOIN subscriptions s ON s.tenant_id=e.tenant_id WHERE e.token_hash=? " +
      "ORDER BY s.updated_at DESC LIMIT 1",
  ).bind(tokenHash).first<{
    id: string;
    tenant_id: string;
    expires_at: number;
    consumed_at: number | null;
    entitlement_status: string;
    grace_period_ends_at: number | null;
    agent_limit: number;
  }>();
  if (token === null) throw new HttpError(401, "invalid_enrollment_token", "Enrollment token is invalid");
  if (token.expires_at < timestamp) throw new HttpError(401, "expired_enrollment_token", "Enrollment token is expired");
  if (token.consumed_at !== null) throw new HttpError(409, "enrollment_token_consumed", "Enrollment token was already consumed");
  if (!isHostedOk(refreshEntitlement(token.entitlement_status, token.grace_period_ends_at, timestamp))) {
    throw new HttpError(402, "subscription_inactive", "An active subscription is required");
  }
  const agentId = crypto.randomUUID();
  const credential = secureToken("ap_agent_");
  try {
    const results = await env.DB.batch([
      env.DB.prepare(
        "UPDATE enrollment_tokens SET consumed_at=?,consumed_by_agent_id=? " +
          "WHERE id=? AND consumed_at IS NULL AND expires_at>=? " +
          "AND (SELECT COUNT(*) FROM agents WHERE tenant_id=? AND revoked_at IS NULL) < ?",
      ).bind(timestamp, agentId, token.id, timestamp, token.tenant_id, token.agent_limit),
      env.DB.prepare(
        "INSERT INTO agents (id,tenant_id,agent_key,hostname,credential_hash,prefix,local_policy_ceiling,enrolled_at) " +
          "SELECT ?,?,?,?,?,?,?,? WHERE changes()=1",
      ).bind(agentId, token.tenant_id, agentKey, hostname, await sha256(credential), credential.slice(0, 12), ceiling, timestamp),
    ]);
    if ((results[0]?.meta.changes ?? 0) !== 1 || (results[1]?.meta.changes ?? 0) !== 1) {
      throw new HttpError(409, "enrollment_token_unavailable", "Enrollment token is expired, consumed, or the plan limit is reached");
    }
  } catch (error) {
    if (error instanceof HttpError) throw error;
    throw new HttpError(409, "agent_already_enrolled", "Agent identity is already enrolled");
  }
  return responseJson({ agent_id: agentId, agent_credential: credential, agent_key: agentKey }, 201);
}

type IncidentStatus = "open" | "resolved" | "escalated";
type IncidentSeverity = "info" | "warning" | "critical";

interface NormalizedIncident {
  fingerprint: string;
  kind: string;
  status: IncidentStatus;
  severity: IncidentSeverity;
  detail: string;
}

function normalizeIncident(value: unknown, index: number): NormalizedIncident {
  const item = objectValue(value);
  const kind = stringField(item.kind ?? `incident-${index}`, "incident.kind", 128);
  const detail = typeof item.detail === "string" ? item.detail.slice(0, 2048) : "";
  const rawStatus = typeof item.status === "string" ? item.status : "open";
  const status: IncidentStatus = rawStatus === "succeeded" ? "resolved" : rawStatus === "escalated" ? "escalated" : rawStatus === "resolved" ? "resolved" : "open";
  const rawSeverity = item.severity;
  const severity: IncidentSeverity = rawSeverity === "critical" || status === "escalated" ? "critical" : rawSeverity === "info" ? "info" : "warning";
  const suppliedFingerprint = typeof item.fingerprint === "string" ? item.fingerprint : `${kind}:${detail}`;
  const fingerprint = stringField(suppliedFingerprint || `incident-${index}`, "incident.fingerprint", 255);
  return { fingerprint, kind, status, severity, detail };
}

async function heartbeat(request: Request, env: WorkerEnv): Promise<Response> {
  const agent = await agentAuth(request, env);
  const body = objectValue(parseJson(await readBody(request)));
  const idempotency = stringField(body.idempotency_key, "idempotency_key", 128);
  if (typeof body.observed_at !== "number" || !Number.isFinite(body.observed_at)) {
    throw new HttpError(422, "invalid_payload", "observed_at must be a finite timestamp");
  }
  const summary = objectValue(body.summary);
  validateSummary(summary);
  if (!Array.isArray(body.incidents) || body.incidents.length > 50) {
    throw new HttpError(422, "invalid_payload", "incidents must be an array of at most 50 items");
  }
  const incidents = body.incidents.map((value, index) => normalizeIncident(value, index));
  const received = Math.floor(Date.now() / 1000);
  const heartbeatStatement = env.DB.prepare(
    "INSERT OR IGNORE INTO heartbeat_events (id,tenant_id,agent_id,observed_at,received_at,payload,idempotency_key) VALUES (?,?,?,?,?,?,?)",
  ).bind(crypto.randomUUID(), agent.tenantId, agent.id, Math.floor(body.observed_at), received, JSON.stringify(body), idempotency);
  const inserted = await heartbeatStatement.run();
  const first = (inserted.meta.changes ?? 0) === 1;
  if (first) {
    const statements: D1PreparedStatement[] = [
      env.DB.prepare("UPDATE agents SET last_seen_at=? WHERE id=? AND tenant_id=?").bind(received, agent.id, agent.tenantId),
      ...incidents.map((incident) => env.DB.prepare(
        "INSERT INTO incidents (id,tenant_id,agent_id,fingerprint,kind,status,severity,detail,opened_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?) " +
          "ON CONFLICT(agent_id,fingerprint) DO UPDATE SET kind=excluded.kind,status=excluded.status,severity=excluded.severity,detail=excluded.detail,updated_at=excluded.updated_at",
      ).bind(crypto.randomUUID(), agent.tenantId, agent.id, incident.fingerprint, incident.kind, incident.status, incident.severity, incident.detail, received, received)),
    ];
    await env.DB.batch(statements);
  }
  return responseJson({ ok: true, duplicate: !first }, first ? 202 : 200);
}

function narrowPolicy(value: unknown, ceiling: Mode): unknown {
  if (Array.isArray(value)) return value.map((item) => narrowPolicy(item, ceiling));
  if (typeof value !== "object" || value === null) return value;
  const output: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value)) {
    if (key === "mode" && isMode(item)) {
      output[key] = MODE_RANK[item] > MODE_RANK[ceiling] ? ceiling : item;
    } else {
      output[key] = narrowPolicy(item, ceiling);
    }
  }
  return output;
}

async function policy(request: Request, env: WorkerEnv): Promise<Response> {
  const agent = await agentAuth(request, env);
  const row = await env.DB.prepare(
    "SELECT version,document FROM policies WHERE tenant_id=? ORDER BY version DESC LIMIT 1",
  ).bind(agent.tenantId).first<{ version: number; document: string }>();
  if (row === null) return responseJson({ version: 0, policy: { checks: {} } });
  let document: unknown;
  try {
    document = JSON.parse(row.document);
  } catch {
    throw new HttpError(500, "invalid_stored_policy", "Stored policy is invalid");
  }
  return responseJson({ version: row.version, policy: narrowPolicy(document, agent.localCeiling) });
}

async function fleet(request: Request, env: WorkerEnv): Promise<Response> {
  let tenantId: string;
  const cookie = cookieValue(request, SESSION_COOKIE);
  if (cookie) {
    const session = await browserAuth(request, env);
    if (!isHostedOk(session.entitlementStatus)) {
      throw new HttpError(402, "subscription_inactive", "An active subscription is required");
    }
    tenantId = session.tenantId;
  } else {
    const account = await accountAuth(request, env);
    tenantId = account.tenantId;
  }
  const result = await env.DB.prepare(
    "SELECT id,agent_key,hostname,enrolled_at,last_seen_at,local_policy_ceiling FROM agents " +
      "WHERE tenant_id=? AND revoked_at IS NULL ORDER BY agent_key",
  ).bind(tenantId).all<{ id: string; agent_key: string; hostname: string; enrolled_at: number; last_seen_at: number | null; local_policy_ceiling: string }>();
  const agents = [];
  for (const agent of result.results) {
    const incidents = await env.DB.prepare(
      "SELECT id,fingerprint,kind,status,severity,detail,opened_at,updated_at FROM incidents " +
        "WHERE tenant_id=? AND agent_id=? ORDER BY updated_at DESC LIMIT 50",
    ).bind(tenantId, agent.id).all();
    agents.push({
      agent_key: agent.agent_key,
      hostname: agent.hostname,
      enrolled_at: agent.enrolled_at,
      last_seen_at: agent.last_seen_at,
      local_policy_ceiling: agent.local_policy_ceiling,
      incidents: incidents.results,
    });
  }
  return responseJson({ agents });
}

function parseStripeSignature(value: string): { timestamp: number; signatures: string[] } {
  let timestamp = 0;
  const signatures: string[] = [];
  for (const part of value.split(",")) {
    const separator = part.indexOf("=");
    if (separator < 1) continue;
    const key = part.slice(0, separator);
    const item = part.slice(separator + 1);
    if (key === "t") timestamp = Number(item);
    if (key === "v1") signatures.push(item);
  }
  return { timestamp, signatures };
}

function constantTimeEqual(left: Uint8Array, right: Uint8Array): boolean {
  if (left.length !== right.length) return false;
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) {
    difference |= (left[index] ?? 0) ^ (right[index] ?? 0);
  }
  return difference === 0;
}

async function stripeSignatureValid(raw: Uint8Array, header: string, secret: string): Promise<boolean> {
  const parsed = parseStripeSignature(header);
  const current = Math.floor(Date.now() / 1000);
  if (!Number.isInteger(parsed.timestamp) || Math.abs(current - parsed.timestamp) > 300 || parsed.signatures.length === 0 || !secret) return false;
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const prefix = new TextEncoder().encode(`${parsed.timestamp}.`);
  const signed = new Uint8Array(prefix.length + raw.length);
  signed.set(prefix);
  signed.set(raw, prefix.length);
  const expected = new Uint8Array(await crypto.subtle.sign("HMAC", key, signed));
  return parsed.signatures.some((candidate) => {
    if (!/^[0-9a-f]{64}$/i.test(candidate)) return false;
    const actual = new Uint8Array(candidate.match(/.{2}/g)?.map((part) => Number.parseInt(part, 16)) ?? []);
    return constantTimeEqual(actual, expected);
  });
}

async function applySubscriptionObject(
  env: WorkerEnv,
  item: Record<string, unknown>,
  now: number,
  eventCreated: number,
  forceGrace = false,
  lease?: WebhookLease,
): Promise<void> {
  const subscriptionId = stringField(item.id, "subscription.id", 255);
  const customerId = stringField(item.customer, "subscription.customer", 255);
  const status = stringField(item.status, "subscription.status", 64);
  const identifierRows = (await env.DB.prepare(
    "SELECT stripe_customer_id,stripe_subscription_id FROM subscriptions " +
      "WHERE stripe_subscription_id=? OR stripe_customer_id=?",
  ).bind(subscriptionId, customerId).all<{
    stripe_customer_id: string;
    stripe_subscription_id: string;
  }>()).results;
  if (
    identifierRows.length > 0 &&
    (
      identifierRows.length !== 1 ||
      identifierRows[0]?.stripe_customer_id !== customerId ||
      identifierRows[0]?.stripe_subscription_id !== subscriptionId
    )
  ) {
    throw new HttpError(409, "subscription_conflict", "Stripe subscription identifiers conflict with an existing account");
  }
  let priceId = "";
  if (typeof item.items === "object" && item.items !== null) {
    const items = item.items as Record<string, unknown>;
    if (Array.isArray(items.data) && items.data[0] && typeof items.data[0] === "object") {
      const first = items.data[0] as Record<string, unknown>;
      if (typeof first.price === "object" && first.price !== null) {
        const price = first.price as Record<string, unknown>;
        if (typeof price.id === "string") priceId = price.id;
      } else if (typeof first.price === "string") {
        priceId = first.price;
      }
    }
  }
  // Entitlement plan is derived only from configured Stripe Price IDs.
  // Metadata plan labels are never trusted for capacity.
  let plan: Plan | null = priceId ? planFromPriceId(env, priceId) : null;
  const metadataPlan = (() => {
    if (typeof item.metadata === "object" && item.metadata !== null) {
      const metadata = item.metadata as Record<string, unknown>;
      if (isPlan(metadata.plan)) return metadata.plan;
    }
    return null;
  })();
  if (metadataPlan && plan && metadataPlan !== plan) {
    // Price and metadata disagree: fail closed by blocking capacity.
    plan = null;
  }
  // Normalize provider statuses that the local schema does not store.
  // incomplete_expired is a terminal Stripe status and must block entitlement.
  const normalizedStatus = status === "incomplete_expired" ? "canceled" : status;
  // Unknown Price IDs never grant capacity.
  if (priceId && !plan) {
    const sql =
      "UPDATE subscriptions SET status=?,entitlement_status='blocked',grace_period_ends_at=NULL,updated_at=?,stripe_event_created_at=? " +
        "WHERE stripe_subscription_id=? AND stripe_customer_id=? " +
        "AND (stripe_event_created_at<? OR (stripe_event_created_at=? AND " +
        "CASE entitlement_status WHEN 'blocked' THEN 2 WHEN 'grace' THEN 1 ELSE 0 END<=2))" +
        (lease ? " AND EXISTS (SELECT 1 FROM stripe_events WHERE id=? AND outcome='pending' AND lease_token=?)" : "");
    const values: unknown[] = [
      normalizedStatus === "canceled" || !["incomplete","trialing","active","past_due","canceled","unpaid","paused"].includes(normalizedStatus)
        ? "canceled"
        : normalizedStatus,
      now,
      eventCreated,
      subscriptionId,
      customerId,
      eventCreated,
      eventCreated,
    ];
    if (lease) values.push(lease.eventId, lease.token);
    await env.DB.prepare(sql).bind(...values).run();
    return;
  }
  if (!plan || !priceId) {
    const existing = await env.DB.prepare("SELECT tenant_id,price_id,plan FROM subscriptions WHERE stripe_subscription_id=?").bind(subscriptionId)
      .first<{ tenant_id: string; price_id: string; plan: string }>();
    if (!existing || !isPlan(existing.plan)) return;
    // Keep existing mapped price/plan only when the event carries no usable price.
    if (!priceId) priceId = existing.price_id;
    if (!plan) plan = existing.plan;
    // If the event carries a price that is unmapped/conflicted, already returned above.
  }
  // Basil+ moves current_period_end onto items; accept classic top-level too.
  // Lifecycle updates store missing periods as null; claim requires a future period.
  const periodEnd = stripeSubscriptionPeriodEnd(item);
  const existing = await env.DB.prepare(
    "SELECT grace_period_ends_at,entitlement_status FROM subscriptions WHERE stripe_subscription_id=?",
  ).bind(subscriptionId).first<{ grace_period_ends_at: number | null; entitlement_status: string }>();
  let graceEndsAt: number | null = existing?.grace_period_ends_at ?? null;
  if (normalizedStatus === "active" || normalizedStatus === "trialing") graceEndsAt = null;
  if (forceGrace || normalizedStatus === "past_due") {
    if (graceEndsAt === null) graceEndsAt = now + GRACE_SECONDS;
  }
  if (
    normalizedStatus === "canceled" ||
    normalizedStatus === "unpaid" ||
    normalizedStatus === "incomplete" ||
    normalizedStatus === "paused" ||
    status === "incomplete_expired"
  ) {
    graceEndsAt = null;
  }
  let email = `customer+${customerId.slice(-8)}@users.agentpulse.invalid`;
  try {
    const customer = await stripeRequest(env, "GET", `/customers/${encodeURIComponent(customerId)}`);
    if (typeof customer.email === "string" && customer.email) email = customer.email;
  } catch {
    // Keep synthetic email if customer fetch fails.
  }
  await upsertTenantSubscription(env, {
    email,
    customerId,
    subscriptionId,
    status: normalizedStatus,
    priceId,
    plan,
    periodEnd,
    graceEndsAt,
    eventCreated,
    now,
  }, lease);
}

async function invoiceStripeIdentifiers(
  env: WorkerEnv,
  item: Record<string, unknown>,
): Promise<{ customerId: string; subscriptionId: string }> {
  const customerId = stringField(item.customer, "invoice.customer", 255);
  const nestedSubscriptionId = stripeInvoiceSubscriptionId(item);
  const subscriptionId = stringField(nestedSubscriptionId, "invoice.subscription", 255);
  const rows = (await env.DB.prepare(
    "SELECT stripe_customer_id,stripe_subscription_id FROM subscriptions " +
      "WHERE stripe_subscription_id=? OR stripe_customer_id=?",
  ).bind(subscriptionId, customerId).all<{
    stripe_customer_id: string;
    stripe_subscription_id: string;
  }>()).results;
  if (
    rows.length > 0 &&
    (
      rows.length !== 1 ||
      rows[0]?.stripe_customer_id !== customerId ||
      rows[0]?.stripe_subscription_id !== subscriptionId
    )
  ) {
    throw new HttpError(409, "subscription_conflict", "Invoice customer does not own the Stripe subscription");
  }
  return { customerId, subscriptionId };
}

async function handleStripeEvent(
  env: WorkerEnv,
  eventType: string,
  event: Record<string, unknown>,
  now: number,
  lease: WebhookLease,
): Promise<"processed" | "skipped"> {
  const data = objectValue(event.data);
  const item = objectValue(data.object);
  const eventCreated = typeof event.created === "number" && Number.isFinite(event.created)
    ? Math.floor(event.created)
    : now;
  if (eventType === "checkout.session.completed") {
    const checkoutId = stringField(item.id, "checkout.id", 255);
    try {
      await materializePaidCheckout(env, checkoutId, eventCreated, lease);
    } catch (error) {
      if (error instanceof HttpError && error.status === 409 && error.code === "already_claimed") return "processed";
      if (error instanceof HttpError && error.status === 401) return "skipped";
      throw error;
    }
    return "processed";
  }
  if (
    eventType === "customer.subscription.created" ||
    eventType === "customer.subscription.updated" ||
    eventType === "customer.subscription.deleted"
  ) {
    if (eventType === "customer.subscription.deleted") {
      item.status = "canceled";
    }
    await applySubscriptionObject(env, item, now, eventCreated, false, lease);
    return "processed";
  }
  if (eventType === "invoice.paid") {
    const { customerId, subscriptionId } = await invoiceStripeIdentifiers(env, item);
    await env.DB.prepare(
      "UPDATE subscriptions SET status='active',entitlement_status='active',grace_period_ends_at=NULL,updated_at=?,stripe_event_created_at=? " +
        "WHERE stripe_subscription_id=? AND stripe_customer_id=? AND (stripe_event_created_at<? OR (stripe_event_created_at=? AND " +
        "CASE entitlement_status WHEN 'blocked' THEN 2 WHEN 'grace' THEN 1 ELSE 0 END<=0)) " +
        "AND EXISTS (SELECT 1 FROM stripe_events WHERE id=? AND outcome='pending' AND lease_token=?)",
    ).bind(now, eventCreated, subscriptionId, customerId, eventCreated, eventCreated, lease.eventId, lease.token).run();
    return "processed";
  }
  if (eventType === "invoice.payment_failed") {
    const { customerId, subscriptionId } = await invoiceStripeIdentifiers(env, item);
    const existing = await env.DB.prepare(
      "SELECT grace_period_ends_at FROM subscriptions WHERE stripe_subscription_id=? AND stripe_customer_id=?",
    ).bind(subscriptionId, customerId).first<{ grace_period_ends_at: number | null }>();
    // The first failed-payment event starts grace. Retries and later distinct
    // failures preserve that fixed deadline so repeated failures cannot defer denial.
    // A successful invoice clears the deadline, allowing a future billing cycle to
    // start a new grace window if it later fails.
    const graceEndsAt = existing?.grace_period_ends_at ?? (now + GRACE_SECONDS);
    await env.DB.prepare(
      "UPDATE subscriptions SET status='past_due',entitlement_status='grace',grace_period_ends_at=?,updated_at=?,stripe_event_created_at=? " +
        "WHERE stripe_subscription_id=? AND stripe_customer_id=? AND (stripe_event_created_at<? OR (stripe_event_created_at=? AND (" +
        "CASE entitlement_status WHEN 'blocked' THEN 2 WHEN 'grace' THEN 1 ELSE 0 END<1 OR " +
        "(CASE entitlement_status WHEN 'blocked' THEN 2 WHEN 'grace' THEN 1 ELSE 0 END=1 AND " +
        "COALESCE(grace_period_ends_at,0)>=?)))) " +
        "AND EXISTS (SELECT 1 FROM stripe_events WHERE id=? AND outcome='pending' AND lease_token=?)",
    ).bind(
      graceEndsAt,
      now,
      eventCreated,
      subscriptionId,
      customerId,
      eventCreated,
      eventCreated,
      graceEndsAt,
      lease.eventId,
      lease.token,
    ).run();
    return "processed";
  }
  return "skipped";
}

async function stripeWebhook(request: Request, env: WorkerEnv): Promise<Response> {
  const raw = await readBody(request);
  const signature = request.headers.get("Stripe-Signature") ?? "";
  if (!(await stripeSignatureValid(raw, signature, env.STRIPE_WEBHOOK_SECRET))) {
    throw new HttpError(400, "invalid_stripe_signature", "Stripe signature is invalid");
  }
  const event = objectValue(parseJson(raw));
  const eventId = stringField(event.id, "event.id", 255);
  const eventType = stringField(event.type, "event.type", 255);
  const payloadHash = await sha256(raw);
  const timestamp = Math.floor(Date.now() / 1000);
  const leaseToken = crypto.randomUUID();
  const leaseExpiresAt = timestamp + WEBHOOK_STALE_SECONDS;
  const inserted = await env.DB.prepare(
    "INSERT OR IGNORE INTO stripe_events (id,event_type,received_at,outcome,lease_token,lease_expires_at,attempt_count,payload_sha256) " +
      "VALUES (?,?,?,?,?,?,1,?)",
  ).bind(eventId, eventType, timestamp, "pending", leaseToken, leaseExpiresAt, payloadHash).run();
  if ((inserted.meta.changes ?? 0) !== 1) {
    const existing = await env.DB.prepare(
      "SELECT event_type,outcome,lease_expires_at,payload_sha256 FROM stripe_events WHERE id=?",
    ).bind(eventId).first<{
      event_type: string;
      outcome: string;
      lease_expires_at: number | null;
      payload_sha256: string;
    }>();
    if (existing === null || existing.event_type !== eventType) {
      throw new HttpError(409, "event_conflict", "Stripe event ID conflicts with an existing event");
    }
    if (existing.payload_sha256 !== "" && existing.payload_sha256 !== payloadHash) {
      throw new HttpError(409, "event_conflict", "Stripe event ID was retried with a different payload");
    }
    if (existing.outcome === "processed" || existing.outcome === "skipped") {
      // Bind the first signed body for legacy rows that predate payload fingerprints.
      // After binding, later retries with a different body fail closed.
      if (existing.payload_sha256 === "") {
        const bound = await env.DB.prepare(
          "UPDATE stripe_events SET payload_sha256=? WHERE id=? AND payload_sha256='' AND outcome IN ('processed','skipped')",
        ).bind(payloadHash, eventId).run();
        if ((bound.meta.changes ?? 0) !== 1) {
          const current = await env.DB.prepare("SELECT payload_sha256 FROM stripe_events WHERE id=?")
            .bind(eventId)
            .first<{ payload_sha256: string }>();
          if (current === null || (current.payload_sha256 !== "" && current.payload_sha256 !== payloadHash)) {
            throw new HttpError(409, "event_conflict", "Stripe event ID was retried with a different payload");
          }
        }
      }
      return responseJson({ ok: true, duplicate: true });
    }
    if (existing.outcome === "pending" && (existing.lease_expires_at ?? 0) > timestamp) {
      throw new HttpError(409, "event_in_progress", "Stripe event is already being processed");
    }
    const acquired = await env.DB.prepare(
      "UPDATE stripe_events SET received_at=?,processed_at=NULL,outcome='pending',processing_error=NULL," +
        "lease_token=?,lease_expires_at=?,attempt_count=attempt_count+1,payload_sha256=? " +
        "WHERE id=? AND (payload_sha256='' OR payload_sha256=?) " +
        "AND (outcome='failed' OR (outcome='pending' AND COALESCE(lease_expires_at,0)<=?))",
    ).bind(timestamp, leaseToken, leaseExpiresAt, payloadHash, eventId, payloadHash, timestamp).run();
    if ((acquired.meta.changes ?? 0) !== 1) {
      throw new HttpError(409, "event_in_progress", "Stripe event is already being processed");
    }
  }
  try {
    const outcome = await handleStripeEvent(env, eventType, event, timestamp, { eventId, token: leaseToken });
    const finalized = await env.DB.prepare(
      "UPDATE stripe_events SET processed_at=?,outcome=?,processing_error=NULL,lease_token=NULL,lease_expires_at=NULL " +
        "WHERE id=? AND outcome='pending' AND lease_token=?",
    ).bind(timestamp, outcome, eventId, leaseToken).run();
    if ((finalized.meta.changes ?? 0) !== 1) {
      throw new HttpError(409, "event_lease_lost", "Stripe event processing lease was superseded");
    }
    return responseJson({ ok: true, duplicate: false });
  } catch (error) {
    const message = error instanceof Error ? error.message.slice(0, 500) : "processing failed";
    const failed = await env.DB.prepare(
      "UPDATE stripe_events SET processed_at=?,outcome='failed',processing_error=?,lease_token=NULL,lease_expires_at=NULL " +
        "WHERE id=? AND outcome='pending' AND lease_token=?",
    ).bind(timestamp, message, eventId, leaseToken).run();
    if ((failed.meta.changes ?? 0) !== 1) {
      throw new HttpError(409, "event_lease_lost", "Stripe event processing lease was superseded");
    }
    throw error instanceof HttpError ? error : new HttpError(500, "internal_error", "Internal server error");
  }
}

async function route(request: Request, env: WorkerEnv): Promise<Response> {
  if (request.method === "OPTIONS") return preflight(request, env);
  const url = new URL(request.url);
  const contentLength = request.headers.get("Content-Length");
  if (contentLength !== null && Number(contentLength) > MAX_BODY_BYTES) {
    throw new HttpError(413, "payload_too_large", "Request body exceeds 65536 bytes");
  }
  if (request.method === "GET" && url.pathname === "/health") {
    return responseJson({ ok: true, service: "agentpulse-control-plane", version: env.AGENTPULSE_VERSION, environment: env.ENVIRONMENT });
  }
  if (request.method === "POST" && url.pathname === "/v1/billing/checkout") return createBillingCheckout(request, env);
  if (request.method === "POST" && url.pathname === "/v1/onboarding/claim") return claimOnboarding(request, env);
  if (request.method === "GET" && url.pathname === "/v1/account") return getAccount(request, env);
  if (request.method === "POST" && url.pathname === "/v1/session/csrf") return refreshSessionCsrf(request, env);
  if (request.method === "DELETE" && url.pathname === "/v1/session") return deleteSession(request, env);
  if (request.method === "POST" && url.pathname === "/v1/billing/portal") return createBillingPortal(request, env);
  if (request.method === "POST" && url.pathname === "/v1/browser/enrollment-tokens") return createBrowserEnrollmentToken(request, env);
  if (request.method === "POST" && url.pathname === "/v1/enrollment-tokens") return createEnrollmentToken(request, env);
  if (request.method === "POST" && url.pathname === "/v1/agents/enroll") return enrollAgent(request, env);
  if (request.method === "POST" && url.pathname === "/v1/agents/heartbeat") return heartbeat(request, env);
  if (request.method === "GET" && url.pathname === "/v1/agents/policy") return policy(request, env);
  if (request.method === "GET" && url.pathname === "/v1/fleet") return fleet(request, env);
  if (request.method === "POST" && url.pathname === "/v1/stripe/webhook") return stripeWebhook(request, env);
  return failure(404, "not_found", "Route not found");
}

export default {
  async fetch(request: Request, env: WorkerEnv): Promise<Response> {
    try {
      return withCors(await route(request, env), env, request);
    } catch (error) {
      if (error instanceof HttpError) return withCors(failure(error.status, error.code, error.message), env, request);
      console.error(JSON.stringify({ message: "unhandled_error", path: new URL(request.url).pathname }));
      return withCors(failure(500, "internal_error", "Internal server error"), env, request);
    }
  },
} satisfies ExportedHandler<WorkerEnv>;
