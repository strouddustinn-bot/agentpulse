import { useEffect, useState } from 'react'
import { Radio, Save, ShieldCheck } from 'lucide-react'
import { getToken, setToken } from '../lib/api'
import { relTime } from '../lib/time'

interface Props { live: boolean; lastRun: number | null }

export function TopBar({ live, lastRun }: Props) {
  const [token, updateToken] = useState(getToken())
  const [saved, setSaved] = useState(false)
  const [, tick] = useState(0)
  useEffect(() => { const id = window.setInterval(() => tick((n) => n + 1), 5000); return () => clearInterval(id) }, [])
  const save = () => { setToken(token.trim()); setSaved(true); window.setTimeout(() => setSaved(false), 1500) }

  return <header className="topbar">
    <div className="brand"><span className="brand-mark"><ShieldCheck size={20}/></span><div><strong>AgentPulse</strong><span>Operations control</span></div></div>
    <div className="topbar-actions">
      <div className={`live-pill ${live ? 'is-live' : ''}`}><Radio size={14}/><span>{live ? 'LIVE' : 'RECONNECTING'}</span></div>
      <div className="last-run"><span>Last agent run</span><strong>{relTime(lastRun)}</strong></div>
      <label className="token-field"><span>Operator token</span><div><input aria-label="Operator token" type="password" value={token} placeholder="Required to act" onChange={(e) => updateToken(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') save() }}/><button aria-label="Save operator token" onClick={save}><Save size={15}/><span>{saved ? 'Saved' : 'Save'}</span></button></div></label>
    </div>
  </header>
}
