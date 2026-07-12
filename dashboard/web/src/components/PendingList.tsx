import { useState } from 'react'
import { Check, LoaderCircle, ShieldAlert, X } from 'lucide-react'
import { approvePending, denyPending } from '../lib/api'
import { relTime } from '../lib/time'
import type { Pending } from '../lib/types'

export function PendingList({ pending }: { pending: Pending[] }) {
  const [busy, setBusy] = useState<string | null>(null)
  const [notice, setNotice] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const act = async (id: string, verb: 'approve' | 'deny') => {
    setBusy(`${id}:${verb}`); setNotice(null)
    const result = verb === 'approve' ? await approvePending(id) : await denyPending(id)
    setBusy(null)
    if (result.ok) setNotice({ kind: 'ok', text: verb === 'approve' ? 'Approval sent through the safety loop.' : 'Action denied and recorded.' })
    else setNotice({ kind: 'err', text: result.status === 401 ? 'Set the operator token in the top bar.' : (result.error ?? 'Request failed.') })
  }
  return <section className="panel pending-panel"><div className="panel-heading"><div><span className="eyebrow">Operator queue</span><h2>Pending approvals</h2></div><span className="count-badge">{pending.length}</span></div>
    {notice && <div role="status" className={`notice ${notice.kind}`}>{notice.kind === 'err' ? <ShieldAlert size={16}/> : <Check size={16}/>} {notice.text}</div>}
    <div className="pending-list">{pending.length === 0 ? <div className="empty-state"><Check size={22}/><strong>Nothing waiting</strong><span>The agent is holding steady.</span></div> : pending.map((item) => <article className="pending-row" key={item.id}><div className="pending-copy"><div><span className="action-chip">{item.action.replaceAll('_', ' ')}</span><code>{item.target}</code></div><p>{item.reason || 'Operator decision required.'}</p><small>Queued {relTime(item.queued_at)} · <code>{item.id}</code></small></div><div className="row-actions"><button className="btn approve" disabled={busy !== null} onClick={() => act(item.id, 'approve')}>{busy === `${item.id}:approve` ? <LoaderCircle className="spin" size={16}/> : <Check size={16}/>}Approve</button><button className="btn deny" disabled={busy !== null} onClick={() => act(item.id, 'deny')}>{busy === `${item.id}:deny` ? <LoaderCircle className="spin" size={16}/> : <X size={16}/>}Deny</button></div></article>)}</div>
  </section>
}
