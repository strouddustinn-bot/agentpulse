/**
 * Thin fetch client for the pulse_server REST API.
 *
 * Mutations carry `Authorization: Bearer <token>`; the token lives in
 * localStorage and is set deliberately by the operator via the top bar.
 */

import type { HistoryEntry, MetricsResponse } from './types'

const TOKEN_KEY = 'pulse_token'

export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? ''
  } catch {
    return ''
  }
}

export function setToken(token: string): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // storage unavailable (private mode etc.) — token just won't persist
  }
}

export interface ApiResult {
  ok: boolean
  /** HTTP status, or 0 when the request never reached the server. */
  status: number
  error?: string
  output?: string
}

async function post(path: string): Promise<ApiResult> {
  let res: Response
  try {
    res = await fetch(path, {
      method: 'POST',
      headers: { Authorization: `Bearer ${getToken()}` },
    })
  } catch {
    return { ok: false, status: 0, error: 'Network error — is the dashboard service running?' }
  }
  const body = (await res.json().catch(() => null)) as
    | { detail?: string; output?: string }
    | null
  if (res.ok) return { ok: true, status: res.status, output: body?.output }
  return {
    ok: false,
    status: res.status,
    error: typeof body?.detail === 'string' && body.detail ? body.detail : res.statusText,
  }
}

export const approvePending = (id: string) =>
  post(`/api/pending/${encodeURIComponent(id)}/approve`)

export const denyPending = (id: string) =>
  post(`/api/pending/${encodeURIComponent(id)}/deny`)

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`GET ${path} → ${res.status} ${res.statusText}`)
  return (await res.json()) as T
}

export async function fetchHistory(opts: {
  limit?: number
  beforeTs?: number
}): Promise<HistoryEntry[]> {
  const params = new URLSearchParams()
  params.set('limit', String(opts.limit ?? 50))
  if (opts.beforeTs !== undefined) params.set('before_ts', String(opts.beforeTs))
  const body = await getJson<{ history: HistoryEntry[] }>(`/api/history?${params}`)
  return Array.isArray(body.history) ? body.history : []
}

export async function fetchMetrics(hours: number): Promise<MetricsResponse> {
  const body = await getJson<MetricsResponse>(`/api/metrics?hours=${hours}`)
  return body && typeof body === 'object' ? body : {}
}
