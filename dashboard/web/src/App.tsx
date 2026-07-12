import { ActivityTimeline } from './components/ActivityTimeline'
import { MetricsPanel } from './components/MetricsPanel'
import { PendingList } from './components/PendingList'
import { StatCards } from './components/StatCards'
import { TopBar } from './components/TopBar'
import { useLive } from './lib/useLive'

export default function App() {
  const { state, history, live, lastMetric, liveSamples } = useLive()
  return <div className="app-shell"><TopBar live={live} lastRun={state?.last_run ?? null}/><main><div className="page-intro"><div><span className="eyebrow">Single-host control plane</span><h1>Operational pulse</h1><p>Watch conditions, review every decision, and keep human authority at the action boundary.</p></div><div className="safety-note"><span>SAFETY POSTURE</span><strong>Verify or escalate</strong><small>No blind retries. No direct state mutation.</small></div></div><StatCards state={state} history={history}/>{state === null && <div className="connecting-banner">Connecting to the persistent service…</div>}<div className="work-grid"><PendingList pending={state?.pending ?? []}/><ActivityTimeline liveHistory={history}/></div><MetricsPanel liveSamples={liveSamples} lastMetric={lastMetric}/></main><footer>AgentPulse · alert-only by default · every fix verifies or escalates</footer></div>
}
