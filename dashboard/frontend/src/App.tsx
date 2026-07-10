import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Shield, AlertTriangle, Activity, Users } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'

interface AgentState {
  last_run: number | null
  pending: any[]
  history: any[]
  blocked_ips: any[]
  agents: Record<string, any>
}

export default function App() {
  const [state, setState] = useState<AgentState>({
    last_run: null,
    pending: [],
    history: [],
    blocked_ips: [],
    agents: {}
  })
  const [metricsHistory, setMetricsHistory] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  // Poll real state from the agent
  useEffect(() => {
    const fetchState = async () => {
      try {
        const res = await fetch('/api/state')
        const data = await res.json()
        
        if (data && !data.error) {
          setState(data)

          // Build simple metrics history from pending + last_run
          const now = new Date().toLocaleTimeString([], { 
            hour: '2-digit', minute: '2-digit', second: '2-digit' 
          })
          
          setMetricsHistory(prev => [
            ...prev.slice(-10),
            {
              time: now,
              pending: data.pending?.length || 0,
              blocked: data.blocked_ips?.length || 0
            }
          ])
        }
      } catch (e) {
        console.error('Failed to fetch state', e)
      } finally {
        setLoading(false)
      }
    }

    fetchState()
    const interval = setInterval(fetchState, 3000) // every 3 seconds

    return () => clearInterval(interval)
  }, [])

  const totalPending = state.pending.length
  const totalBlocked = state.blocked_ips.length
  const agentCount = Object.keys(state.agents).length || 1

  const pieData = [
    { name: 'Healthy', value: Math.max(0, agentCount - totalPending) },
    { name: 'Needs Attention', value: totalPending },
  ]

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0b0f] flex items-center justify-center text-[#64748b]">
        Loading real agent data...
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#0a0b0f] text-[#e2e8f0]">
      {/* Header */}
      <div className="border-b border-[#1f2937] bg-[#111318]/95 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-8 flex items-center justify-between h-20">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-[#7c6af7] flex items-center justify-center">
              <Shield className="w-6 h-6 text-white" />
            </div>
            <div>
              <div className="text-2xl font-semibold tracking-[-1.5px]">AgentPulse</div>
              <div className="text-[10px] text-[#64748b] -mt-1 tracking-[2px]">LIVE • REAL DATA</div>
            </div>
          </div>
          <div className="text-xs px-4 py-1.5 rounded-full bg-[#052e16] text-[#22c55e]">
            CONNECTED TO REAL AGENT
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-8 py-10">
        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-10">
          {[
            { icon: Users, label: "Monitored Hosts", value: agentCount },
            { icon: AlertTriangle, label: "Pending Actions", value: totalPending },
            { icon: Activity, label: "Blocked IPs", value: totalBlocked },
            { icon: Shield, label: "Last Run", value: state.last_run ? new Date(state.last_run * 1000).toLocaleTimeString() : '—' },
          ].map((stat, i) => (
            <div key={i} className="bg-[#111318] border border-[#1f2937] rounded-3xl p-7">
              <stat.icon className="w-5 h-5 mb-6 text-[#7c6af7]" />
              <div className="text-5xl font-semibold tracking-[-1.5px] tabular-nums mb-1">{stat.value}</div>
              <div className="text-[#64748b] text-sm">{stat.label}</div>
            </div>
          ))}
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 mb-10">
          <div className="lg:col-span-3 bg-[#111318] border border-[#1f2937] rounded-3xl p-8">
            <div className="font-semibold text-xl mb-6">Activity Over Time</div>
            <div className="h-80">
              <ResponsiveContainer>
                <AreaChart data={metricsHistory.length ? metricsHistory : [{ time: 'now', pending: totalPending, blocked: totalBlocked }]}>
                  <CartesianGrid stroke="#1f2937" />
                  <XAxis dataKey="time" stroke="#64748b" />
                  <YAxis stroke="#64748b" />
                  <Tooltip contentStyle={{ background: '#1a1d27', border: 'none' }} />
                  <Area type="natural" dataKey="pending" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.2} strokeWidth={3} />
                  <Area type="natural" dataKey="blocked" stroke="#ef4444" fill="#ef4444" fillOpacity={0.15} strokeWidth={3} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="lg:col-span-2 bg-[#111318] border border-[#1f2937] rounded-3xl p-8">
            <div className="font-semibold mb-4">Current Status</div>
            <ResponsiveContainer height={260}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={70} outerRadius={100} dataKey="value">
                  {pieData.map((entry, index) => <Cell key={index} fill={['#22c55e', '#f59e0b'][index]} />)}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Pending Actions */}
        <div className="bg-[#111318] border border-[#1f2937] rounded-3xl p-8">
          <div className="font-semibold text-2xl mb-6">Pending Actions</div>
          
          {state.pending.length === 0 ? (
            <div className="text-center py-12 text-[#64748b]">
              No pending actions. Your system is healthy.
            </div>
          ) : (
            <div className="space-y-3">
              {state.pending.map((action, index) => (
                <div key={index} className="flex items-center justify-between bg-[#1a1d27] border border-[#2d3048] rounded-2xl px-7 py-5">
                  <div>
                    <div className="font-medium">{action.action}</div>
                    <div className="text-sm text-[#64748b]">{action.target}</div>
                  </div>
                  <div className="text-[#f59e0b] text-sm">{action.reason || 'Action required'}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
