import { FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Shield } from 'lucide-react'
import { setCredential } from '../auth/credential'

export default function ConnectPage() {
  const [credential, setCredentialValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      setCredential(credential)
      navigate('/servers')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Credential is invalid')
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
          <p className="text-sm text-[#64748b]">Beta account credential</p>
        </div>
      </div>
      <form onSubmit={submit} className="bg-[#111318] border border-[#1f2937] rounded-3xl p-7">
        <label className="block text-sm text-[#94a3b8] mb-2" htmlFor="credential">
          Account credential
        </label>
        <input
          id="credential"
          type="password"
          autoComplete="off"
          value={credential}
          onChange={(event) => setCredentialValue(event.target.value)}
          className="w-full rounded-xl bg-[#0a0b0f] border border-[#2d3048] px-4 py-3 text-[#e2e8f0] outline-none focus:border-[#7c6af7]"
          placeholder="ap_account_…"
        />
        {error ? <p className="text-sm text-[#f87171] mt-3">{error}</p> : null}
        <p className="text-xs text-[#64748b] mt-4">
          This beta credential is kept only in this browser tab. General-availability session login is still a release blocker.
        </p>
        <button type="submit" className="mt-6 rounded-xl bg-[#7c6af7] px-5 py-2.5 text-sm font-medium text-white hover:bg-[#6d5ce7]">
          Connect
        </button>
      </form>
    </div>
  )
}
