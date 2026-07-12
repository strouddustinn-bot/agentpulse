/**
 * Server detail — read-only agent metadata plus its incidents.
 */

import { Link, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { getAgent, listIncidents } from '../api/client'
import { useFetch } from '../hooks/useFetch'
import {
  AgentStatusBadge,
  EmptyState,
  ErrorState,
  IncidentStatusBadge,
  LoadingState,
  OnlineBadge,
  Panel,
  SeverityBadge,
} from '../components/ui'
import { formatDateTime, formatRelative, isAgentOnline } from '../lib/format'

function MetaField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-[#64748b] mb-1">{label}</div>
      <div className="text-sm text-[#e2e8f0] break-all">{value || '—'}</div>
    </div>
  )
}

export default function ServerDetailPage() {
  const { agentId = '' } = useParams<{ agentId: string }>()

  const agent = useFetch(() => getAgent(agentId), [agentId])
  const incidents = useFetch(() => listIncidents({ agent_id: agentId }), [agentId])

  return (
    <div>
      <Link
        to="/servers"
        className="inline-flex items-center gap-1.5 text-sm text-[#64748b] hover:text-[#e2e8f0] transition-colors mb-6"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to servers
      </Link>

      {/* Agent metadata */}
      <Panel className="mb-8">
        {agent.loading ? (
          <LoadingState label="Loading server…" />
        ) : agent.error ? (
          <ErrorState message={agent.error} onRetry={agent.retry} />
        ) : !agent.data ? (
          <EmptyState title="Server not found" />
        ) : (
          <div className="p-8">
            <div className="flex flex-wrap items-center gap-4 mb-8">
              <h1 className="text-3xl font-semibold tracking-[-1px]">
                {agent.data.hostname || agent.data.id}
              </h1>
              <AgentStatusBadge status={agent.data.status} />
              <OnlineBadge online={isAgentOnline(agent.data.last_seen_at)} />
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-6">
              <MetaField label="Agent ID" value={agent.data.id} />
              <MetaField label="OS" value={agent.data.os} />
              <MetaField label="Architecture" value={agent.data.architecture} />
              <MetaField label="Agent version" value={agent.data.agent_version} />
              <MetaField label="Config version" value={agent.data.config_version} />
              <MetaField label="Machine ID" value={agent.data.machine_id} />
              <MetaField label="Enrolled" value={formatDateTime(agent.data.enrolled_at)} />
              <MetaField
                label="Last check-in"
                value={`${formatDateTime(agent.data.last_seen_at)} (${formatRelative(agent.data.last_seen_at)})`}
              />
            </div>

            {agent.data.tags.length > 0 ? (
              <div className="mt-6 flex flex-wrap gap-2">
                {agent.data.tags.map((tag) => (
                  <span
                    key={tag}
                    className="px-2.5 py-0.5 rounded-full bg-[#1a1d27] border border-[#2d3048] text-xs text-[#94a3b8]"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        )}
      </Panel>

      {/* Incidents for this agent */}
      <h2 className="text-xl font-semibold tracking-[-0.5px] mb-4">Incidents</h2>
      <Panel>
        {incidents.loading ? (
          <LoadingState label="Loading incidents…" />
        ) : incidents.error ? (
          <ErrorState message={incidents.error} onRetry={incidents.retry} />
        ) : !incidents.data || incidents.data.incidents.length === 0 ? (
          <EmptyState
            title="No incidents for this server"
            hint="Incidents opened by this agent's checks will appear here."
          />
        ) : (
          <div className="divide-y divide-[#1f2937]">
            {incidents.data.incidents.map((incident) => (
              <Link
                key={incident.id}
                to={`/incidents/${encodeURIComponent(incident.id)}`}
                className="flex flex-wrap items-center justify-between gap-3 px-7 py-4 hover:bg-[#161923] transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <SeverityBadge severity={incident.severity} />
                  <span className="font-medium text-[#e2e8f0] truncate">{incident.title}</span>
                </div>
                <div className="flex items-center gap-4">
                  <IncidentStatusBadge status={incident.status} />
                  <span className="text-xs text-[#64748b]" title={formatDateTime(incident.opened_at)}>
                    {formatRelative(incident.opened_at)}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}
