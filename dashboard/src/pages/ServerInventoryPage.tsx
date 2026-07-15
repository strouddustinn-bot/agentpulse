/**
 * Server inventory — read-only table of enrolled agents.
 */

import { Link } from 'react-router-dom'
import { listAgents } from '../api/client'
import { useFetch } from '../hooks/useFetch'
import {
  AgentStatusBadge,
  EmptyState,
  ErrorState,
  LoadingState,
  OnlineBadge,
  Panel,
} from '../components/ui'
import { formatRelative, formatDateTime, isAgentOnline } from '../lib/format'

export default function ServerInventoryPage() {
  const { data, loading, error, retry } = useFetch(() => listAgents(), [])

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-[-1px]">Servers</h1>
        <p className="text-sm text-[#64748b] mt-1">
          All enrolled agents and their current check-in status.
        </p>
      </div>

      <Panel>
        {loading ? (
          <LoadingState label="Loading servers…" />
        ) : error ? (
          <ErrorState message={error} onRetry={retry} />
        ) : !data || data.agents.length === 0 ? (
          <EmptyState
            title="No servers enrolled"
            hint="Once an agent enrolls with the backend it will appear here."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-[#64748b] border-b border-[#1f2937]">
                  <th className="px-7 py-4 font-medium">Hostname</th>
                  <th className="px-4 py-4 font-medium">Status</th>
                  <th className="px-4 py-4 font-medium">Connectivity</th>
                  <th className="px-4 py-4 font-medium">Last check-in</th>
                  <th className="px-4 py-4 font-medium">OS / Arch</th>
                  <th className="px-7 py-4 font-medium">Version</th>
                </tr>
              </thead>
              <tbody>
                {data.agents.map((agent) => (
                  <tr
                    key={agent.id}
                    className="border-b border-[#1f2937] last:border-b-0 hover:bg-[#161923] transition-colors"
                  >
                    <td className="px-7 py-4">
                      <Link
                        to={`/servers/${encodeURIComponent(agent.id)}`}
                        className="font-medium text-[#e2e8f0] hover:text-[#7c6af7] transition-colors"
                      >
                        {agent.hostname || agent.id}
                      </Link>
                      <div className="text-xs text-[#64748b] mt-0.5">{agent.id}</div>
                    </td>
                    <td className="px-4 py-4">
                      <AgentStatusBadge status={agent.status} />
                    </td>
                    <td className="px-4 py-4">
                      <OnlineBadge online={isAgentOnline(agent.last_seen_at)} />
                    </td>
                    <td className="px-4 py-4 text-[#94a3b8]" title={formatDateTime(agent.last_seen_at)}>
                      {formatRelative(agent.last_seen_at)}
                    </td>
                    <td className="px-4 py-4 text-[#94a3b8]">
                      {agent.os}
                      {agent.architecture ? ` / ${agent.architecture}` : ''}
                    </td>
                    <td className="px-7 py-4 text-[#94a3b8] tabular-nums">{agent.agent_version || '—'}</td>
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
