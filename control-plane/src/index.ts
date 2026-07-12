interface WorkerEnv extends Env {
  STRIPE_WEBHOOK_SECRET: string;
  STRIPE_API_KEY: string;
}

type Mode = "off" | "alert" | "ask" | "auto";

const MAX_BODY_BYTES = 65_536;
const ACTIVE_SUBSCRIPTIONS = new Set(["active", "trialing"]);
const MODE_RANK: Record<Mode, number> = { off: 0, alert: 1, ask: 2, auto: 3 };

class HttpError extends Error {
  constructor(readonly status: number, readonly code: string, message: string) {
    super(message);
  }
}

function responseJson(value: unknown, status = 200): Response {
  return Response.json(value, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

function failure(status: number, code: string, message: string): Response {
  return responseJson({ error: { code, message } }, status);
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

async function sha256(value: string): Promise<string> {
  return hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)));
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
  if (typeof value !== "string" || value.length < 1 || value.length > max) {
    throw new HttpError(422, "invalid_payload", `${name} must be a non-empty string of at most ${max} characters`);
  }
  return value;
}

function isMode(value: unknown): value is Mode {
  return typeof value === "string" && value in MODE_RANK;
}

interface AccountAuth {
  credentialId: string;
  tenantId: string;
  status: string;
  agentLimit: number;
}

async function accountAuth(request: Request, env: WorkerEnv): Promise<AccountAuth> {
  const hash = await sha256(bearer(request));
  const row = await env.DB.prepare(
    "SELECT c.id AS credential_id,c.tenant_id,s.status,s.agent_limit " +
      "FROM account_credentials c JOIN subscriptions s ON s.tenant_id=c.tenant_id " +
      "WHERE c.credential_hash=? AND c.revoked_at IS NULL ORDER BY s.updated_at DESC LIMIT 1",
  ).bind(hash).first<{ credential_id: string; tenant_id: string; status: string; agent_limit: number }>();
  if (row === null) throw new HttpError(401, "invalid_credential", "Account credential is invalid");
  if (!ACTIVE_SUBSCRIPTIONS.has(row.status)) {
    throw new HttpError(402, "subscription_inactive", "An active subscription is required");
  }
  return { credentialId: row.credential_id, tenantId: row.tenant_id, status: row.status, agentLimit: row.agent_limit };
}

interface AgentAuth {
  id: string;
  tenantId: string;
  agentKey: string;
  localCeiling: Mode;
  status: string;
}

async function agentAuth(request: Request, env: WorkerEnv): Promise<AgentAuth> {
  const hash = await sha256(bearer(request));
  const row = await env.DB.prepare(
    "SELECT a.id,a.tenant_id,a.agent_key,a.local_policy_ceiling,s.status " +
      "FROM agents a JOIN subscriptions s ON s.tenant_id=a.tenant_id " +
      "WHERE a.credential_hash=? AND a.revoked_at IS NULL ORDER BY s.updated_at DESC LIMIT 1",
  ).bind(hash).first<{ id: string; tenant_id: string; agent_key: string; local_policy_ceiling: string; status: string }>();
  if (row === null || !isMode(row.local_policy_ceiling)) {
    throw new HttpError(401, "invalid_credential", "Agent credential is invalid");
  }
  if (!ACTIVE_SUBSCRIPTIONS.has(row.status)) {
    throw new HttpError(402, "subscription_inactive", "An active subscription is required");
  }
  return { id: row.id, tenantId: row.tenant_id, agentKey: row.agent_key, localCeiling: row.local_policy_ceiling, status: row.status };
}

async function createEnrollmentToken(request: Request, env: WorkerEnv): Promise<Response> {
  const account = await accountAuth(request, env);
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
  ).bind(crypto.randomUUID(), account.tenantId, await sha256(token), account.credentialId, created, expires).run();
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
    "SELECT e.id,e.tenant_id,e.expires_at,e.consumed_at,s.status,s.agent_limit FROM enrollment_tokens e " +
      "JOIN subscriptions s ON s.tenant_id=e.tenant_id WHERE e.token_hash=? " +
      "ORDER BY s.updated_at DESC LIMIT 1",
  ).bind(tokenHash).first<{ id: string; tenant_id: string; expires_at: number; consumed_at: number | null; status: string; agent_limit: number }>();
  if (token === null) throw new HttpError(401, "invalid_enrollment_token", "Enrollment token is invalid");
  if (token.expires_at < timestamp) throw new HttpError(401, "expired_enrollment_token", "Enrollment token is expired");
  if (token.consumed_at !== null) throw new HttpError(409, "enrollment_token_consumed", "Enrollment token was already consumed");
  if (!ACTIVE_SUBSCRIPTIONS.has(token.status)) {
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

async function heartbeat(request: Request, env: WorkerEnv): Promise<Response> {
  const agent = await agentAuth(request, env);
  const body = objectValue(parseJson(await readBody(request)));
  const idempotency = stringField(body.idempotency_key, "idempotency_key", 128);
  if (typeof body.observed_at !== "number" || !Number.isFinite(body.observed_at)) {
    throw new HttpError(422, "invalid_payload", "observed_at must be a finite timestamp");
  }
  if (typeof body.summary !== "object" || body.summary === null || Array.isArray(body.summary)) {
    throw new HttpError(422, "invalid_payload", "summary must be an object");
  }
  if (!Array.isArray(body.incidents) || body.incidents.length > 50) {
    throw new HttpError(422, "invalid_payload", "incidents must be an array of at most 50 items");
  }
  const received = Math.floor(Date.now() / 1000);
  const inserted = await env.DB.prepare(
    "INSERT OR IGNORE INTO heartbeat_events (id,tenant_id,agent_id,observed_at,received_at,payload,idempotency_key) VALUES (?,?,?,?,?,?,?)",
  ).bind(crypto.randomUUID(), agent.tenantId, agent.id, Math.floor(body.observed_at), received, JSON.stringify(body), idempotency).run();
  await env.DB.prepare("UPDATE agents SET last_seen_at=? WHERE id=? AND tenant_id=?")
    .bind(received, agent.id, agent.tenantId).run();
  const first = (inserted.meta.changes ?? 0) === 1;
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
  const account = await accountAuth(request, env);
  const result = await env.DB.prepare(
    "SELECT agent_key,hostname,enrolled_at,last_seen_at,local_policy_ceiling FROM agents " +
      "WHERE tenant_id=? AND revoked_at IS NULL ORDER BY agent_key",
  ).bind(account.tenantId).all<{ agent_key: string; hostname: string; enrolled_at: number; last_seen_at: number | null; local_policy_ceiling: string }>();
  return responseJson({ agents: result.results });
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

async function stripeWebhook(request: Request, env: WorkerEnv): Promise<Response> {
  const raw = await readBody(request);
  const signature = request.headers.get("Stripe-Signature") ?? "";
  if (!(await stripeSignatureValid(raw, signature, env.STRIPE_WEBHOOK_SECRET))) {
    throw new HttpError(400, "invalid_stripe_signature", "Stripe signature is invalid");
  }
  const event = objectValue(parseJson(raw));
  const eventId = stringField(event.id, "event.id", 255);
  const eventType = stringField(event.type, "event.type", 255);
  const existing = await env.DB.prepare("SELECT 1 AS found FROM stripe_events WHERE id=?").bind(eventId).first<{ found: number }>();
  if (existing !== null) return responseJson({ ok: true, duplicate: true });
  const timestamp = Math.floor(Date.now() / 1000);
  const statements: D1PreparedStatement[] = [
    env.DB.prepare("INSERT OR IGNORE INTO stripe_events (id,event_type,received_at,processed_at) VALUES (?,?,?,?)")
      .bind(eventId, eventType, timestamp, timestamp),
  ];
  if (eventType === "invoice.payment_failed") {
    const data = objectValue(event.data);
    const item = objectValue(data.object);
    const subscriptionId = stringField(item.subscription, "subscription", 255);
    statements.push(env.DB.prepare("UPDATE subscriptions SET status='past_due',updated_at=? WHERE stripe_subscription_id=?")
      .bind(timestamp, subscriptionId));
  }
  await env.DB.batch(statements);
  return responseJson({ ok: true, duplicate: false });
}

async function route(request: Request, env: WorkerEnv): Promise<Response> {
  const url = new URL(request.url);
  const contentLength = request.headers.get("Content-Length");
  if (contentLength !== null && Number(contentLength) > MAX_BODY_BYTES) {
    throw new HttpError(413, "payload_too_large", "Request body exceeds 65536 bytes");
  }
  if (request.method === "GET" && url.pathname === "/health") {
    return responseJson({ ok: true, service: "agentpulse-control-plane", version: env.AGENTPULSE_VERSION, environment: env.ENVIRONMENT });
  }
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
      return await route(request, env);
    } catch (error) {
      if (error instanceof HttpError) return failure(error.status, error.code, error.message);
      console.error(JSON.stringify({ message: "unhandled_error", path: new URL(request.url).pathname }));
      return failure(500, "internal_error", "Internal server error");
    }
  },
} satisfies ExportedHandler<WorkerEnv>;
