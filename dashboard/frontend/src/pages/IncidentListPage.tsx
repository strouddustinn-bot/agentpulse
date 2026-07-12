/**
 * Incident list — read-only table of all incidents.
 */

import { Link } from 'react-router-dom'
import { listIncidents } from '../api/client'
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

export default function IncidentListPage() {
  const { data, loading, error, retry } = useFetch(() => listIncidents(), [])

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-[-1px]">Incidents</h1>
        <p className="text-sm text-[#64748b] mt-1">
          Issues detected by agent checks, most recent first.
        </p>
      </div>

      <Panel>
        {loading ? (
          <LoadingState label="Loading incidents…" />
        ) : error ? (
          <ErrorState message={error} onRetry={retry} />
        ) : !data || data.incidents.length === 0 ? (
          <EmptyState
            title="No incidents"
            hint="When an agent check fails, the resulting incident will appear here."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-[#64748b] border-b border-[#1f2937]">
                  <th className="px-7 py-4 font-medium">Severity</th>
                  <th className="px-4 py-4 font-medium">Title</th>
                  <th className="px-4 py-4 font-medium">Status</th>
                  <th className="px-4 py-4 font-medium">Agent</th>
                  <th className="px-4 py-4 font-medium">Opened</th>
                  <th className="px-7 py-4 font-medium">Resolved</th>
                </tr>
              </thead>
              <tbody>
                {data.incidents.map((incident) => (
                  <tr
                    key={incident.id}
                    className="border-b border-[#1f2937] last:border-b-0 hover:bg-[#161923] transition-colors"
                  >
                    <td className="px-7 py-4">
                      <SeverityBadge severity={incident.severity} />
                    </td>
                    <td className="px-4 py-4">
                      <Link
                        to={`/incidents/${encodeURIComponent(incident.id)}`}
                        className="font-medium text-[#e2e8f0] hover:text-[#7c6af7] transition-colors"
                      >
                        {incident.title}
                      </Link>
                      <div className="text-xs text-[#64748b] mt-0.5">{incident.check_type}</div>
                    </td>
                    <td className="px-4 py-4">
                      <IncidentStatusBadge status={incident.status} />
                    </td>
                    <td className="px-4 py-4">
                      <Link
                        to={`/servers/${encodeURIComponent(incident.agent_id)}`}
                        className="text-[#94a3b8] hover:text-[#7c6af7] transition-colors"
                      >
                        {incident.agent_id}
                      </Link>
                    </td>
                    <td className="px-4 py-4 text-[#94a3b8]">{formatDateTime(incident.opened_at)}</td>
                    <td className="px-7 py-4 text-[#94a3b8]">{formatDateTime(incident.resolved_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}
