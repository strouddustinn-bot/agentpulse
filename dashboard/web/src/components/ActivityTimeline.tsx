import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, LoaderCircle } from 'lucide-react'
import { fetchHistory } from '../lib/api'
import { absTime, relTime } from '../lib/time'
import { historyKey, type HistoryEntry } from '../lib/types'

export function ActivityTimeline({ liveHistory }: { liveHistory: HistoryEntry[] }) {
  const [older, setOlder] = useState<HistoryEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const merged = useMemo(() => {
    const map = new Map<string, HistoryEntry>()
    ;[...liveHistory, ...older].forEach((e) => map.set(historyKey(e), e))
    return [...map.values()].sort((a, b) => b.ts - a.ts)
  }, [liveHistory, older])
  useEffect(() => { if (liveHistory.length) setOlder((o) => o.filter((x) => !liveHistory.some((h) => historyKey(h) === historyKey(x)))) }, [liveHistory])
  const load = async () => { setLoading(true); setError(''); try { const rows = await fetchHistory({ limit: 50, beforeTs: merged.at(-1)?.ts }); setOlder((o) => [...o, ...rows]) } catch (e) { setError(e instanceof Error ? e.message : 'Could not load history') } finally { setLoading(false) } }
  const tone = (o: string) => o === 'succeeded' || o === 'simulated_only' ? 'ok' : o === 'escalated' || o === 'blocked' ? 'warn' : o === 'denied' ? 'muted' : 'err'
  return <section className="panel timeline-panel"><div className="panel-heading"><div><span className="eyebrow">Audit trail</span><h2>Recent activity</h2></div><span className="count-badge">{merged.length}</span></div><div className="timeline">{merged.length === 0 ? <div className="empty-state"><strong>No recorded actions</strong><span>Verified remediation events will appear here.</span></div> : merged.map((entry) => <details className="timeline-entry" key={historyKey(entry)}><summary><span className={`event-dot ${tone(entry.outcome)}`}/><div><strong>{entry.action.replaceAll('_', ' ')}</strong><code>{entry.target}</code><small>{entry.outcome.replaceAll('_', ' ')} · {relTime(entry.ts)}</small></div><ChevronDown className="chevron" size={16}/></summary><div className="event-detail"><span>{absTime(entry.ts)}</span>{entry.reason && <p>{entry.reason}</p>}<pre>{JSON.stringify(entry, null, 2)}</pre></div></details>)}</div>{error && <p className="inline-error">{error}</p>}<button className="load-more" disabled={loading || merged.length === 0} onClick={load}>{loading && <LoaderCircle className="spin" size={15}/>}Load older</button></section>
}
