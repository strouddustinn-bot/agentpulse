/**
 * Date/time formatting + agent liveness helpers.
 */

/** Staleness threshold — an agent unseen for longer than this is offline. */
export const ONLINE_THRESHOLD_MS = 5 * 60 * 1000 // 5 minutes

export function parseTimestamp(value: string | null | undefined): Date | null {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

/** Derive online/offline from last_seen_at staleness. */
export function isAgentOnline(lastSeenAt: string | null | undefined): boolean {
  const seen = parseTimestamp(lastSeenAt)
  if (!seen) return false
  return Date.now() - seen.getTime() <= ONLINE_THRESHOLD_MS
}

/** Absolute local timestamp, e.g. "Jul 12, 2026, 14:03:22". */
export function formatDateTime(value: string | null | undefined): string {
  const date = parseTimestamp(value)
  if (!date) return '—'
  return date.toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/** Compact relative time, e.g. "3m ago", "2h ago". */
export function formatRelative(value: string | null | undefined): string {
  const date = parseTimestamp(value)
  if (!date) return '—'
  const deltaMs = Date.now() - date.getTime()
  if (deltaMs < 0) return 'just now'
  const seconds = Math.floor(deltaMs / 1000)
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}
