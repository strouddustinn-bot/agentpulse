/**
 * Shared UI primitives for the read-only dashboard screens:
 * loading, empty, and error states plus badges and cards.
 */

import type { ReactNode } from 'react'
import { AlertTriangle, Inbox, Loader2, RefreshCw } from 'lucide-react'
import type { AgentStatus, IncidentStatus, Severity } from '../api/types'

// ─── Panel ────────────────────────────────────────────────────────────────

export function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`bg-[#111318] border border-[#1f2937] rounded-3xl ${className}`}>
      {children}
    </div>
  )
}

// ─── States ───────────────────────────────────────────────────────────────

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-[#64748b]">
      <Loader2 className="w-6 h-6 animate-spin text-[#7c6af7]" />
      <div className="text-sm">{label}</div>
    </div>
  )
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <Inbox className="w-8 h-8 text-[#334155]" />
      <div className="text-[#94a3b8] font-medium">{title}</div>
      {hint ? <div className="text-sm text-[#64748b] max-w-sm">{hint}</div> : null}
    </div>
  )
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string
  onRetry: () => void
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-16 text-center">
      <AlertTriangle className="w-8 h-8 text-[#f59e0b]" />
      <div>
        <div className="text-[#e2e8f0] font-medium mb-1">Something went wrong</div>
        <div className="text-sm text-[#64748b] max-w-md">{message}</div>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#1a1d27] border border-[#2d3048] text-sm text-[#e2e8f0] hover:border-[#7c6af7] transition-colors"
      >
        <RefreshCw className="w-4 h-4" />
        Retry
      </button>
    </div>
  )
}

// ─── Badges ───────────────────────────────────────────────────────────────

const SEVERITY_STYLES: Record<Severity, string> = {
  critical: 'bg-[#450a0a] text-[#f87171]',
  warning: 'bg-[#451a03] text-[#fbbf24]',
  info: 'bg-[#172554] text-[#60a5fa]',
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const style = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.info
  return (
    <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium uppercase tracking-wide ${style}`}>
      {severity}
    </span>
  )
}

const INCIDENT_STATUS_STYLES: Record<IncidentStatus, string> = {
  open: 'bg-[#450a0a] text-[#f87171]',
  acknowledged: 'bg-[#451a03] text-[#fbbf24]',
  resolved: 'bg-[#052e16] text-[#22c55e]',
  suppressed: 'bg-[#1e293b] text-[#94a3b8]',
}

export function IncidentStatusBadge({ status }: { status: IncidentStatus }) {
  const style = INCIDENT_STATUS_STYLES[status] ?? INCIDENT_STATUS_STYLES.suppressed
  return (
    <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium uppercase tracking-wide ${style}`}>
      {status}
    </span>
  )
}

const AGENT_STATUS_STYLES: Record<AgentStatus, { dot: string; text: string }> = {
  online: { dot: 'bg-[#22c55e]', text: 'text-[#22c55e]' },
  degraded: { dot: 'bg-[#f59e0b]', text: 'text-[#f59e0b]' },
  offline: { dot: 'bg-[#64748b]', text: 'text-[#94a3b8]' },
}

export function AgentStatusBadge({ status }: { status: AgentStatus }) {
  const style = AGENT_STATUS_STYLES[status] ?? AGENT_STATUS_STYLES.offline
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide ${style.text}`}>
      <span className={`w-2 h-2 rounded-full ${style.dot}`} />
      {status}
    </span>
  )
}

export function OnlineBadge({ online }: { online: boolean }) {
  return online ? (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-[#22c55e]">
      <span className="w-2 h-2 rounded-full bg-[#22c55e]" />
      Online
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-[#94a3b8]">
      <span className="w-2 h-2 rounded-full bg-[#64748b]" />
      Offline
    </span>
  )
}
