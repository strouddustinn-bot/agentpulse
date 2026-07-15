export type Mode = 'off' | 'alert' | 'ask' | 'auto'
export type IncidentSeverity = 'info' | 'warning' | 'critical'
export type Severity = IncidentSeverity
export type IncidentStatus = 'open' | 'acknowledged' | 'resolved' | 'suppressed' | 'escalated'
export type AgentStatus = 'online' | 'offline' | 'degraded'

export interface FleetIncident {
  id: string
  agent_id: string
  fingerprint: string
  kind: string
  status: IncidentStatus
  severity: IncidentSeverity
  detail: string
  opened_at: number
  updated_at: number
  title: string
  body: string
  evidence: string[]
  opened_at_iso: string
  resolved_at: string | null
  acknowledged_at: string | null
  acknowledged_by: string
  resolved_by: string
  check_id: string
  check_type: string
  is_baseline_anomaly: boolean
  tags: string[]
}

export interface FleetAgent {
  id: string
  agent_key: string
  hostname: string
  enrolled_at: number
  last_seen_at: number | null
  local_policy_ceiling: Mode
  incidents: FleetIncident[]
  status: AgentStatus
  os: string
  architecture: string
  agent_version: string
  config_version: string
  machine_id: string
  tags: string[]
}

export interface FleetResponse {
  agents: Array<{
    agent_key: string
    hostname: string
    enrolled_at: number
    last_seen_at: number | null
    local_policy_ceiling: Mode
    incidents: Array<{
      id: string
      fingerprint: string
      kind: string
      status: IncidentStatus
      severity: IncidentSeverity
      detail: string
      opened_at: number
      updated_at: number
    }>
  }>
}

export interface AgentListResponse {
  agents: FleetAgent[]
  next_page: string | null
  total: number
}

export interface IncidentListResponse {
  incidents: FleetIncident[]
  next_page: string | null
  total: number
}

export interface IncidentEvent {
  id: number
  incident_id: string
  event_type: string
  actor: string
  actor_id: string
  body: Record<string, unknown>
  created_at: string
}

export interface IncidentEventListResponse {
  events: IncidentEvent[]
}

export interface ApiErrorBody {
  error?: { code?: string; message?: string }
  message?: string
  detail?: string
}
