/**
 * Types mirroring the pulse_server API payloads.
 *
 * Sources of truth:
 *  - agent/agentpulse/state.py  (pending, blocked_ips, history shapes)
 *  - agent/agentpulse/decision_loop.py  (CycleRecord.as_dict → history raw)
 *  - dashboard/pulse_server/main.py  (route envelopes, SSE messages)
 *
 * The backend normalizes keyed maps (pending, blocked_ips) into arrays
 * before they reach the client.
 */

export interface Pending {
  id: string
  action: string
  target: string
  reason: string
  check: string
  metadata?: Record<string, unknown>
  queued_at: number
}

/**
 * History rows come from two producers:
 *  - decision loop cycles (rich: expectation, gate, verify, notes…)
 *  - deny records (minimal: action/target/outcome/reason/ts)
 * Everything beyond the core four fields is optional.
 */
export interface HistoryEntry {
  ts: number
  action: string
  target: string
  outcome: string
  reason?: string
  expectation?: string
  gate_allowed?: boolean
  gate_reasons?: string[]
  simulated?: boolean
  executed?: boolean
  verified?: boolean | null
  notes?: string[]
  dry_run?: boolean
  approved?: boolean
  [extra: string]: unknown
}

export interface BlockedIp {
  ip: string
  blocked_at: number
  /** Current agent field; 0 = permanent. */
  duration_seconds?: number
  /** Legacy field name kept for older state files. */
  duration?: number
  reason?: string
}

export interface FleetAgent {
  agent_id?: string
  hostname?: string
  last_seen?: number
  state?: unknown
  [extra: string]: unknown
}

export interface StateSnapshot {
  last_run: number | null
  pending: Pending[]
  blocked_ips: BlockedIp[]
  fleet: Record<string, FleetAgent>
  /** Present on SSE state pushes: rows newly mirrored to SQLite this poll. */
  new_history?: number
}

export interface MetricPoint {
  ts: number
  value: number
}

/** GET /api/metrics → series keyed by metric name (mem, load1, disk:/…). */
export type MetricsResponse = Record<string, MetricPoint[]>

/** One live sample pushed over SSE (all metrics captured at one instant). */
export interface LiveMetricSample {
  ts: number
  values: Record<string, number>
}

export type SseMsg =
  | { type: 'state'; data: StateSnapshot }
  | { type: 'history'; data: HistoryEntry[] }
  | { type: 'metrics'; data: LiveMetricSample }

/** Stable identity for a history row (backend dedupes on the same triple). */
export function historyKey(e: HistoryEntry): string {
  return `${e.ts}:${e.action}:${e.target}`
}
