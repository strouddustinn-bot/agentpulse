import { FormEvent, useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { Shield } from 'lucide-react'
import { ApiError, claimAccount, getAccount } from '../api/client'

export default function ConnectPage() {
  const location = useLocation()
  const [claimNonce, setClaimNonce] = useState('')
  const [checkingSession, setCheckingSession] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const nonce = params.get('claim_nonce') ?? ''
    if (nonce) {
      window.history.replaceState(null, '', location.pathname)
      setError(null)
      claimAccount(nonce)
        .then(() => navigate('/servers', { replace: true }))
        .catch(async (reason) => {
          try {
            await getAccount()
            navigate('/servers', { replace: true })
          } catch {
            setError(reason instanceof Error ? reason.message : 'Claim token is invalid')
          }
        })
        .finally(() => setCheckingSession(false))
      return
    }

    getAccount()
      .then(() => navigate('/servers', { replace: true }))
      .catch((reason) => {
        if (reason instanceof ApiError && reason.status !== 401) setError(reason.message)
      })
      .finally(() => setCheckingSession(false))
  }, [location.pathname, location.search, navigate])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    try {
      await claimAccount(claimNonce)
      navigate('/servers')
    } catch (reason) {
      try {
        await getAccount()
        navigate('/servers')
      } catch {
        setError(reason instanceof Error ? reason.message : 'Claim token is invalid')
      }
    }
  }

  return (
    <div className="max-w-lg mx-auto py-16">
      <div className="flex items-center gap-3 mb-8">
        <div className="w-10 h-10 rounded-2xl bg-[#7c6af7] flex items-center justify-center">
          <Shield className="w-6 h-6 text-white" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">Connect AgentPulse</h1>
          <p className="text-sm text-[#64748b]">Secure account claim</p>
        </div>
      </div>
      <form onSubmit={submit} className="bg-[#111318] border border-[#1f2937] rounded-3xl p-7">
        <label className="block text-sm text-[#94a3b8] mb-2" htmlFor="claimNonce">
          Checkout claim nonce
        </label>
        <input
          id="claimNonce"
          type="text"
          autoComplete="off"
          value={claimNonce}
          onChange={(event) => setClaimNonce(event.target.value)}
          className="w-full rounded-xl bg-[#0a0b0f] border border-[#2d3048] px-4 py-3 text-[#e2e8f0] outline-none focus:border-[#7c6af7]"
          placeholder="ap_claim_…"
          disabled={checkingSession}
        />
        {checkingSession ? <p className="text-sm text-[#64748b] mt-3">Checking session…</p> : null}
        {error ? <p className="text-sm text-[#f87171] mt-3">{error}</p> : null}
        <p className="text-xs text-[#64748b] mt-4">
          The claim nonce is exchanged once for an HttpOnly session cookie; it is never stored in browser storage.
        </p>
        <button type="submit" className="mt-6 rounded-xl bg-[#7c6af7] px-5 py-2.5 text-sm font-medium text-white hover:bg-[#6d5ce7]" disabled={checkingSession}>
          Connect
        </button>
      </form>
    </div>
  )
}
