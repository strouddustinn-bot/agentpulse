/**
 * Read-only client for the authenticated Cloudflare Worker fleet contract.
 *
 * The beta dashboard stores the account credential in sessionStorage only.
 * No mutation, remote command, or legacy FastAPI endpoint is exposed here.
 */

import { getCredential } from '../auth/credential'
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
  const credential = getCredential()
  if (!credential) throw new ApiError(401, 'Connect an AgentPulse account credential first')

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${credential}`,
      },
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
