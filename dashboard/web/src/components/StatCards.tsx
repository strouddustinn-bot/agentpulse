import { AlertTriangle, Ban, CheckCircle2, Clock3 } from 'lucide-react'
import type { HistoryEntry, StateSnapshot } from '../lib/types'

export function StatCards({ state, history }: { state: StateSnapshot | null; history: HistoryEntry[] }) {
  const cutoff = Date.now() / 1000 - 86400
  const recent = history.filter((h) => h.ts >= cutoff)
  const escalations = recent.filter((h) => ['escalated', 'blocked', 'failed'].includes(h.outcome)).length
  const items = [
    { label: 'Pending approvals', value: state?.pending.length ?? 0, icon: Clock3, tone: state?.pending.length ? 'warn' : 'ok' },
    { label: 'Actions · 24h', value: recent.length, icon: CheckCircle2, tone: 'neutral' },
    { label: 'Escalations · 24h', value: escalations, icon: AlertTriangle, tone: escalations ? 'err' : 'ok' },
    { label: 'Blocked IPs', value: state?.blocked_ips.length ?? 0, icon: Ban, tone: state?.blocked_ips.length ? 'warn' : 'neutral' },
  ]
  return <section className="stats-grid" aria-label="Operational summary">{items.map(({ label, value, icon: Icon, tone }) => <article className={`stat-card tone-${tone}`} key={label}><Icon size={18}/><div><span>{label}</span><strong>{value}</strong></div></article>)}</section>
}
