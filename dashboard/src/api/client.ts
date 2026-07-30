/**
 * Client for the authenticated Cloudflare Worker contract.
 *
 * Browser authentication uses the Worker HttpOnly session cookie. The CSRF
 * token is kept in memory only for state-changing requests.
 */

import { clearCredential, getCsrfToken, setCsrfToken } from '../auth/credential'
import type {
  AgentListResponse,
  ApiErrorBody,
  FleetAgent,
  FleetIncident,
  FleetResponse,
  IncidentEventListResponse,
  IncidentListResponse,
} from './types'

const DEFAULT_BASE_URL = 'http://localhost:8787'
export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, '')

export class ApiError extends Error {
  readonly status: number
  readonly body: ApiErrorBody | null

  constructor(status: number, message: string, body: ApiErrorBody | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function getJson<T>(path: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'GET',
      credentials: 'include',
      headers: { Accept: 'application/json' },
    })
  } catch {
    throw new ApiError(0, `Could not reach the AgentPulse API at ${API_BASE_URL}`)
  }

  if (!response.ok) {
    let body: ApiErrorBody | null = null
    let message = `Request failed with status ${response.status}`
    try {
      body = (await response.json()) as ApiErrorBody
      message = body.error?.message || body.message || body.detail || message
    } catch {
      // Preserve the status-based message for non-JSON responses.
    }
    throw new ApiError(response.status, message, body)
  }
  return (await response.json()) as T
}

function normalizeIncident(agentId: string, value: FleetResponse['agents'][number]['incidents'][number]): FleetIncident {
  return {
    ...value,
    agent_id: agentId,
    title: value.kind,
    body: value.detail,
    evidence: value.detail ? [value.detail] : [],
    opened_at_iso: new Date(value.opened_at * 1000).toISOString(),
    resolved_at: value.status === 'resolved' ? new Date(value.updated_at * 1000).toISOString() : null,
    acknowledged_at: null,
    acknowledged_by: '',
    resolved_by: '',
    check_id: value.fingerprint,
    check_type: value.kind,
    is_baseline_anomaly: false,
    tags: [],
  }
}

function normalizeAgent(value: FleetResponse['agents'][number]): FleetAgent {
  const id = value.agent_key
  const incidents = value.incidents.map((incident) => normalizeIncident(id, incident))
  const online = value.last_seen_at !== null && Date.now() / 1000 - value.last_seen_at <= 300
  return {
    ...value,
    id,
    incidents,
    status: online ? 'online' : 'offline',
    os: 'unknown',
    architecture: 'unknown',
    agent_version: 'unknown',
    config_version: 'unknown',
    machine_id: id,
    tags: [],
  }
}

export interface AccountResponse {
  tenant_id: string
  email: string
  plan: string
  entitlement_status: string
  agent_limit: number
  current_period_end: number | null
  grace_period_ends_at: number | null
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody | null = null
  let message = `Request failed with status ${response.status}`
  try {
    body = (await response.json()) as ApiErrorBody
    message = body.error?.message || body.message || body.detail || message
  } catch {
    // Preserve the status-based message for non-JSON responses.
  }
  return new ApiError(response.status, message, body)
}

export async function claimAccount(claimNonce: string): Promise<AccountResponse> {
  const response = await fetch(`${API_BASE_URL}/v1/onboarding/claim`, {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ claim_nonce: claimNonce }),
  })
  if (!response.ok) throw await toApiError(response)
  const payload = (await response.json()) as { csrf_token: string; account: AccountResponse }
  setCsrfToken(payload.csrf_token)
  return payload.account
}

export async function getAccount(): Promise<AccountResponse> {
  return getJson<AccountResponse>('/v1/account')
}

export async function bootstrapCsrf(): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/v1/session/csrf`, {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw await toApiError(response)
  const payload = (await response.json()) as { csrf_token: string }
  setCsrfToken(payload.csrf_token)
}

export async function disconnectSession(): Promise<void> {
  try {
    if (!getCsrfToken()) await bootstrapCsrf()
    const response = await fetch(`${API_BASE_URL}/v1/session`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { 'X-CSRF-Token': getCsrfToken() ?? '' },
    })
    if (!response.ok) throw await toApiError(response)
  } finally {
    clearCredential()
  }
}

async function ensureCsrfToken(): Promise<string> {
  const existing = getCsrfToken()
  if (existing) return existing
  await bootstrapCsrf()
  const token = getCsrfToken()
  if (!token) throw new ApiError(401, 'CSRF token is unavailable')
  return token
}

async function mutateJson<T>(
  path: string,
  method: 'POST' | 'DELETE',
  body?: unknown,
  expectedStatus = 200,
): Promise<T> {
  const csrf = await ensureCsrfToken()
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      credentials: 'include',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, `Could not reach the AgentPulse API at ${API_BASE_URL}`)
  }
  if (response.status === 401 || response.status === 403) {
    // Session/CSRF may be stale after reload; one bootstrap retry.
    clearCredential()
    const retryCsrf = await ensureCsrfToken()
    try {
      response = await fetch(`${API_BASE_URL}${path}`, {
        method,
        credentials: 'include',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-CSRF-Token': retryCsrf,
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
    } catch {
      throw new ApiError(0, `Could not reach the AgentPulse API at ${API_BASE_URL}`)
    }
  }
  if (response.status !== expectedStatus) throw await toApiError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export interface EnrollmentTokenResponse {
  enrollment_token: string
  expires_at: number
}

export interface BillingPortalResponse {
  portal_url: string
}

/** Create a one-time browser enrollment token (cookie + CSRF). Token is returned once. */
export async function createBrowserEnrollmentToken(
  ttlSeconds = 600,
): Promise<EnrollmentTokenResponse> {
  if (!Number.isInteger(ttlSeconds) || ttlSeconds < 60 || ttlSeconds > 900) {
    throw new ApiError(422, 'ttl_seconds must be an integer between 60 and 900')
  }
  return mutateJson<EnrollmentTokenResponse>(
    '/v1/browser/enrollment-tokens',
    'POST',
    { ttl_seconds: ttlSeconds },
    201,
  )
}

/** Open Stripe Customer Portal for the authenticated paid account. */
export async function createBillingPortalSession(): Promise<BillingPortalResponse> {
  return mutateJson<BillingPortalResponse>('/v1/billing/portal', 'POST', {})
}

/**
 * Truthful enrollment guidance. Token is never embedded in a shell one-liner
 * (CLI rejects argv tokens). Operator pastes via prompt or stdin.
 */
export function buildEnrollmentGuidance(apiBaseUrl: string = API_BASE_URL): {
  configureHint: string
  enrollCommand: string
  stdinCommand: string
} {
  const base = apiBaseUrl.replace(/\/+$/, '')
  return {
    configureHint: `Set control_plane.enabled=true and control_plane.base_url=${base} in the agent config before enroll.`,
    enrollCommand: 'agentpulse enroll /etc/agentpulse/config.json',
    stdinCommand: 'agentpulse enroll /etc/agentpulse/config.json --token-stdin',
  }
}

export async function getFleet(): Promise<FleetAgent[]> {
  const response = await getJson<FleetResponse>('/v1/fleet')
  return response.agents.map(normalizeAgent)
}

export async function listAgents(): Promise<AgentListResponse> {
  const agents = await getFleet()
  return { agents, next_page: null, total: agents.length }
}

export async function getAgent(agentId: string): Promise<FleetAgent> {
  const agent = (await getFleet()).find((item) => item.id === agentId)
  if (!agent) throw new ApiError(404, 'Server not found')
  return agent
}

export interface ListIncidentsParams {
  agent_id?: string
  severity?: string
  status?: string
}

export async function listIncidents(params: ListIncidentsParams = {}): Promise<IncidentListResponse> {
  const agents = await getFleet()
  const incidents = agents
    .flatMap((agent) => agent.incidents)
    .filter((incident) => !params.agent_id || incident.agent_id === params.agent_id)
    .filter((incident) => !params.severity || incident.severity === params.severity)
    .filter((incident) => !params.status || incident.status === params.status)
    .sort((left, right) => right.updated_at - left.updated_at)
  return { incidents, next_page: null, total: incidents.length }
}

export async function getIncident(incidentId: string): Promise<FleetIncident> {
  const incidents = (await listIncidents()).incidents
  const incident = incidents.find((item) => item.id === incidentId)
  if (!incident) throw new ApiError(404, 'Incident not found')
  return incident
}

export async function listIncidentEvents(_incidentId: string): Promise<IncidentEventListResponse> {
  // The current Worker contract is read-only fleet state; lifecycle events are deferred.
  return { events: [] }
}
