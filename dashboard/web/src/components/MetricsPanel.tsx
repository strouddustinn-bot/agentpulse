import { useEffect, useMemo, useState } from 'react'
import { Activity, LoaderCircle } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fetchMetrics } from '../lib/api'
import { axisTime } from '../lib/time'
import type { LiveMetricSample, MetricPoint, MetricsResponse } from '../lib/types'

const WINDOWS = [{ label: '1h', hours: 1 }, { label: '24h', hours: 24 }, { label: '7d', hours: 168 }]
const labelFor = (m: string) => m === 'mem' ? 'Memory usage' : m === 'load1' ? 'System load · 1m' : m.startsWith('disk:') ? `Disk usage · ${m.slice(5)}` : m

export function MetricsPanel({ liveSamples, lastMetric }: { liveSamples: LiveMetricSample[]; lastMetric: Record<string, number> }) {
  const [hours, setHours] = useState(24)
  const [data, setData] = useState<MetricsResponse>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => { let active = true; setLoading(true); setError(''); fetchMetrics(hours).then((r) => active && setData(r)).catch((e) => active && setError(e instanceof Error ? e.message : 'Metrics unavailable')).finally(() => active && setLoading(false)); return () => { active = false } }, [hours])
  const merged = useMemo(() => {
    const out: MetricsResponse = {}
    const names = new Set([...Object.keys(data), ...liveSamples.flatMap((s) => Object.keys(s.values))])
    names.forEach((name) => { const map = new Map<number, MetricPoint>(); (data[name] ?? []).forEach((p) => map.set(p.ts, p)); liveSamples.forEach((s) => { if (name in s.values) map.set(s.ts, { ts: s.ts, value: s.values[name] }) }); out[name] = [...map.values()].sort((a, b) => a.ts - b.ts) })
    return out
  }, [data, liveSamples])
  const metrics = Object.entries(merged).sort(([a], [b]) => a.localeCompare(b))
  return <section className="panel metrics-panel"><div className="panel-heading metrics-heading"><div><span className="eyebrow">Host telemetry</span><h2>System metrics</h2></div><div className="window-tabs" role="group" aria-label="Chart time window">{WINDOWS.map((w) => <button aria-pressed={hours === w.hours} className={hours === w.hours ? 'active' : ''} onClick={() => setHours(w.hours)} key={w.hours}>{w.label}</button>)}</div></div>
    {loading ? <div className="metrics-loading"><LoaderCircle className="spin"/><span>Loading telemetry…</span></div> : error ? <div className="metrics-loading error"><Activity/><span>{error}</span></div> : metrics.length === 0 ? <div className="empty-state"><Activity size={22}/><strong>No samples yet</strong><span>The service records memory, load and disk every 15 seconds.</span></div> : <div className="charts-grid">{metrics.map(([name, points]) => <article className="chart-card" key={name}><header><div><span>{labelFor(name)}</span><strong>{(lastMetric[name] ?? points.at(-1)?.value ?? 0).toFixed(name === 'load1' ? 2 : 1)}{name === 'mem' || name.startsWith('disk:') ? '%' : ''}</strong></div><small>{points.length} samples</small></header><div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><AreaChart data={points} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}><defs><linearGradient id={`fill-${name.replaceAll(/[^a-z0-9]/gi, '')}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#7c6af7" stopOpacity={0.28}/><stop offset="100%" stopColor="#7c6af7" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#252936" vertical={false}/><XAxis dataKey="ts" tickFormatter={(v) => axisTime(Number(v), hours)} stroke="#64748b" tickLine={false} axisLine={false} minTickGap={36} fontSize={11}/><YAxis domain={name === 'mem' || name.startsWith('disk:') ? [0, 100] : ['auto', 'auto']} stroke="#64748b" tickLine={false} axisLine={false} fontSize={11}/><Tooltip labelFormatter={(v) => new Date(Number(v) * 1000).toLocaleString()} contentStyle={{ background: '#1a1d27', border: '1px solid #2d3048', borderRadius: 8 }} formatter={(v) => [Number(v).toFixed(2), labelFor(name)]}/><Area type="monotone" dataKey="value" stroke="#8b7df8" strokeWidth={2} fill={`url(#fill-${name.replaceAll(/[^a-z0-9]/gi, '')})`} isAnimationActive={false}/></AreaChart></ResponsiveContainer></div></article>)}</div>}
  </section>
}
