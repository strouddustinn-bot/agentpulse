/**
 * Typed, read-only API client for the AgentPulse backend v1 API.
 *
 * STRICTLY READ-ONLY: only GET requests are performed. No mutation
 * endpoints (acknowledge/resolve/etc.) are exposed here by design.
 *
 * Base URL is configurable via the Vite env var VITE_API_BASE_URL
 * (default: http://localhost:8088).
 */

import type {
  AgentListResponse,
  Agent,
  AuditEventListResponse,
  IncidentEventListResponse,
  IncidentListResponse,
  Incident,
  ApiErrorBody,
} from './types'

const DEFAULT_BASE_URL = 'http://localhost:8088'

export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, '') || DEFAULT_BASE_URL

/** Error thrown for non-2xx responses, carrying status + backend error body. */
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

async function getJson<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(`${API_BASE_URL}/v1${path}`)
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== '') url.searchParams.set(key, String(value))
    }
  }

  let res: Response
  try {
    res = await fetch(url.toString(), {
      method: 'GET',
      headers: { Accept: 'application/json' },
    })
  } catch {
    throw new ApiError(0, `Could not reach the AgentPulse API at ${API_BASE_URL}`)
  }

  if (!res.ok) {
    let body: ApiErrorBody | null = null
    let message = `Request failed with status ${res.status}`
    try {
      const parsed: unknown = await res.json()
      if (parsed && typeof parsed === 'object') {
        if ('message' in parsed && typeof (parsed as ApiErrorBody).message === 'string') {
          body = parsed as ApiErrorBody
          message = body.message
        } else if ('detail' in parsed && typeof (parsed as { detail: unknown }).detail === 'string') {
          message = (parsed as { detail: string }).detail
        }
      }
    } catch {
      // Non-JSON error body — keep the status-based message.
    }
    throw new ApiError(res.status, message, body)
  }

  return (await res.json()) as T
}

// ─── Agents ───────────────────────────────────────────────────────────────

export function listAgents(): Promise<AgentListResponse> {
  return getJson<AgentListResponse>('/agents')
}

export function getAgent(agentId: string): Promise<Agent> {
  return getJson<Agent>(`/agents/${encodeURIComponent(agentId)}`)
}

// ─── Incidents ────────────────────────────────────────────────────────────

export interface ListIncidentsParams {
  status?: string
  agent_id?: string
  severity?: string
  limit?: number
}

export function listIncidents(params?: ListIncidentsParams): Promise<IncidentListResponse> {
  return getJson<IncidentListResponse>('/incidents', {
    status: params?.status,
    agent_id: params?.agent_id,
    severity: params?.severity,
    limit: params?.limit,
  })
}

export function getIncident(incidentId: string): Promise<Incident> {
  return getJson<Incident>(`/incidents/${encodeURIComponent(incidentId)}`)
}

export function listIncidentEvents(incidentId: string): Promise<IncidentEventListResponse> {
  return getJson<IncidentEventListResponse>(
    `/incidents/${encodeURIComponent(incidentId)}/events`,
  )
}

// ─── Audit ────────────────────────────────────────────────────────────────

export interface ListAuditEventsParams {
  agent_id?: string
  incident_id?: string
  event_type?: string
  limit?: number
}

export function listAuditEvents(params?: ListAuditEventsParams): Promise<AuditEventListResponse> {
  return getJson<AuditEventListResponse>('/audit-events', {
    agent_id: params?.agent_id,
    incident_id: params?.incident_id,
    event_type: params?.event_type,
    limit: params?.limit,
  })
}
