/**
 * Incident detail — read-only view of a single incident: severity,
 * lifecycle timestamps, evidence, and event history.
 */

import { Link, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { getIncident, listIncidentEvents } from '../api/client'
import { useFetch } from '../hooks/useFetch'
import {
  EmptyState,
  ErrorState,
  IncidentStatusBadge,
  LoadingState,
  Panel,
  SeverityBadge,
} from '../components/ui'
import { formatDateTime } from '../lib/format'

function LifecycleField({ label, value, by }: { label: string; value: string; by?: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-[#64748b] mb-1">{label}</div>
      <div className="text-sm text-[#e2e8f0]">{value}</div>
      {by ? <div className="text-xs text-[#64748b] mt-0.5">by {by}</div> : null}
    </div>
  )
}

export default function IncidentDetailPage() {
  const { incidentId = '' } = useParams<{ incidentId: string }>()

  const incident = useFetch(() => getIncident(incidentId), [incidentId])
  const events = useFetch(() => listIncidentEvents(incidentId), [incidentId])

  return (
    <div>
      <Link
        to="/incidents"
        className="inline-flex items-center gap-1.5 text-sm text-[#64748b] hover:text-[#e2e8f0] transition-colors mb-6"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to incidents
      </Link>

      {/* Incident summary */}
      <Panel className="mb-8">
        {incident.loading ? (
          <LoadingState label="Loading incident…" />
        ) : incident.error ? (
          <ErrorState message={incident.error} onRetry={incident.retry} />
        ) : !incident.data ? (
          <EmptyState title="Incident not found" />
        ) : (
          <div className="p-8">
            <div className="flex flex-wrap items-center gap-3 mb-4">
              <SeverityBadge severity={incident.data.severity} />
              <IncidentStatusBadge status={incident.data.status} />
              {incident.data.is_baseline_anomaly ? (
                <span className="px-2.5 py-0.5 rounded-full bg-[#2e1065] text-[#c4b5fd] text-xs font-medium uppercase tracking-wide">
                  Baseline anomaly
                </span>
              ) : null}
            </div>

            <h1 className="text-2xl font-semibold tracking-[-0.5px] mb-2">{incident.data.title}</h1>
            {incident.data.body ? (
              <p className="text-sm text-[#94a3b8] whitespace-pre-wrap mb-6">{incident.data.body}</p>
            ) : null}

            <div className="text-sm text-[#64748b] mb-8">
              <span className="mr-6">
                Check: <span className="text-[#94a3b8]">{incident.data.check_id}</span>
                {incident.data.check_type ? (
                  <span className="text-[#64748b]"> ({incident.data.check_type})</span>
                ) : null}
              </span>
              <span>
                Agent:{' '}
                <Link
                  to={`/servers/${encodeURIComponent(incident.data.agent_id)}`}
                  className="text-[#94a3b8] hover:text-[#7c6af7] transition-colors"
                >
                  {incident.data.agent_id}
                </Link>
              </span>
            </div>

            {/* Lifecycle timestamps */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 border-t border-[#1f2937] pt-6">
              <LifecycleField label="Opened" value={formatDateTime(incident.data.opened_at)} />
              <LifecycleField
                label="Acknowledged"
                value={formatDateTime(incident.data.acknowledged_at)}
                by={incident.data.acknowledged_by || undefined}
              />
              <LifecycleField
                label="Resolved"
                value={formatDateTime(incident.data.resolved_at)}
                by={incident.data.resolved_by || undefined}
              />
            </div>
          </div>
        )}
      </Panel>

      {/* Evidence */}
      {incident.data ? (
        <>
          <h2 className="text-xl font-semibold tracking-[-0.5px] mb-4">Evidence</h2>
          <Panel className="mb-8">
            {incident.data.evidence.length === 0 ? (
              <EmptyState title="No evidence attached" />
            ) : (
              <div className="p-6">
                <pre className="text-xs text-[#94a3b8] bg-[#0a0b0f] border border-[#1f2937] rounded-2xl p-5 overflow-x-auto whitespace-pre-wrap break-all">
                  {incident.data.evidence.join('\n')}
                </pre>
              </div>
            )}
          </Panel>
        </>
      ) : null}

      {/* Event history */}
      <h2 className="text-xl font-semibold tracking-[-0.5px] mb-4">Event history</h2>
      <Panel>
        {events.loading ? (
          <LoadingState label="Loading events…" />
        ) : events.error ? (
          <ErrorState message={events.error} onRetry={events.retry} />
        ) : !events.data || events.data.events.length === 0 ? (
          <EmptyState
            title="No events recorded"
            hint="Lifecycle events for this incident will appear here."
          />
        ) : (
          <div className="divide-y divide-[#1f2937]">
            {events.data.events.map((event) => (
              <div key={event.id} className="px-7 py-4">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                  <span className="font-medium text-sm text-[#e2e8f0]">{event.event_type}</span>
                  <span className="text-xs text-[#64748b]">{formatDateTime(event.created_at)}</span>
                </div>
                <div className="text-xs text-[#64748b]">
                  {event.actor}
                  {event.actor_id ? ` (${event.actor_id})` : ''}
                </div>
                {Object.keys(event.body).length > 0 ? (
                  <pre className="mt-2 text-xs text-[#94a3b8] bg-[#0a0b0f] border border-[#1f2937] rounded-xl p-3 overflow-x-auto whitespace-pre-wrap break-all">
                    {JSON.stringify(event.body, null, 2)}
                  </pre>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}
