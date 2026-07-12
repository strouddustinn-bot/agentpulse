/** Time formatting helpers shared across components. */

/** "just now", "42s ago", "5m ago", "3h ago", "2d ago". */
export function relTime(tsSeconds: number | null | undefined, now = Date.now()): string {
  if (tsSeconds == null || !Number.isFinite(tsSeconds)) return '—'
  const delta = Math.max(0, Math.floor(now / 1000 - tsSeconds))
  if (delta < 5) return 'just now'
  if (delta < 60) return `${delta}s ago`
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`
  return `${Math.floor(delta / 86400)}d ago`
}

/** Compact absolute stamp for tooltips/details: "Jul 10, 14:32:05". */
export function absTime(tsSeconds: number | null | undefined): string {
  if (tsSeconds == null || !Number.isFinite(tsSeconds)) return 'unknown time'
  return new Date(tsSeconds * 1000).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/** Axis label for charts, granularity by window size. */
export function axisTime(tsSeconds: number, hours: number): string {
  const d = new Date(tsSeconds * 1000)
  if (hours <= 24) {
    return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
