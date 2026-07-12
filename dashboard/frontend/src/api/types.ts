/**
 * TypeScript types for the AgentPulse backend v1 API.
 *
 * Hand-written to match the canonical Pydantic schemas in
 * backend/agentpulse_backend/schemas/__init__.py (and
 * packages/contracts/openapi.yaml). Keep in sync with those sources.
 */

// ─── Enums ────────────────────────────────────────────────────────────────

export type Severity = 'info' | 'warning' | 'critical'

export type AgentStatus = 'online' | 'offline' | 'degraded'

export type IncidentStatus = 'open' | 'acknowledged' | 'resolved' | 'suppressed'

export type Component =
  | 'agent'
  | 'backend'
  | 'worker'
  | 'dashboard'
  | 'control-plane'

// ─── Agents ───────────────────────────────────────────────────────────────

export interface Agent {
  id: string
  tenant_id: string
  hostname: string
  os: string
  architecture: string
  agent_version: string
  config_version: string
  machine_id: string
  status: AgentStatus
  enrolled_at: string
  last_seen_at: string
  policy_id: string
  tags: string[]
}

export interface AgentListResponse {
  agents: Agent[]
  next_page: string | null
  total: number
}

// ─── Incidents ────────────────────────────────────────────────────────────

export interface Incident {
  id: string
  tenant_id: string
  agent_id: string
  check_id: string
  check_type: string
  status: IncidentStatus
  severity: Severity
  title: string
  body: string
  evidence: string[]
  opened_at: string
  acknowledged_at: string | null
  acknowledged_by: string
  resolved_at: string | null
  resolved_by: string
  remediation_id: string | null
  policy_id: string
  is_baseline_anomaly: boolean
  tags: string[]
}

export interface IncidentListResponse {
  incidents: Incident[]
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

// ─── Audit ────────────────────────────────────────────────────────────────

export interface AuditEvent {
  id: number
  tenant_id: string
  timestamp: string
  component: Component
  event_type: string
  actor: string
  agent_id: string | null
  incident_id: string | null
  remediation_id: string | null
  outcome: string
  body: Record<string, unknown>
}

export interface AuditEventListResponse {
  events: AuditEvent[]
  next_page: string | null
}

// ─── Error ────────────────────────────────────────────────────────────────

export interface ApiErrorBody {
  error_code: string
  message: string
  request_id?: string
  details?: Record<string, unknown>
  retry_after?: number | null
}
