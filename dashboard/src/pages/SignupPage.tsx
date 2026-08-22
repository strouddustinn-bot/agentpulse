import { useState } from 'react'
import { useSearchParams } from 'react-router'

type CheckoutResponse = {
  checkout_url: string
  checkout_session_id: string
  livemode: boolean
  expires_at: number
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8787').replace(/\/+$/, '')

export function isCheckoutPlan(value: string | null): value is 'starter' {
  return value === 'starter'
}

export function isTrustedStripeCheckoutUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return (
      url.protocol === 'https:' &&
      url.hostname === 'checkout.stripe.com' &&
      url.username === '' &&
      url.password === '' &&
      url.port === ''
    )
  } catch {
    return false
  }
}

async function createStarterCheckout(): Promise<CheckoutResponse> {
  const response = await fetch(`${API_BASE_URL}/v1/billing/checkout`, {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan: 'starter' }),
  })

  if (!response.ok) {
    let message = `Checkout is unavailable (HTTP ${response.status})`
    try {
      const body = (await response.json()) as { error?: { message?: string } }
      if (body.error?.message) message = body.error.message
    } catch {
      // Keep the status-based failure message.
    }
    throw new Error(message)
  }

  const checkout = (await response.json()) as CheckoutResponse
  if (!checkout.checkout_session_id?.startsWith('cs_')) {
    throw new Error('Checkout returned an invalid session identifier')
  }
  if (!isTrustedStripeCheckoutUrl(checkout.checkout_url)) {
    throw new Error('Checkout returned an untrusted destination')
  }
  return checkout
}

export default function SignupPage() {
  const [params] = useSearchParams()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const canceled = params.get('canceled') === '1'

  async function startCheckout() {
    setLoading(true)
    setError(null)
    try {
      const checkout = await createStarterCheckout()
      window.location.assign(checkout.checkout_url)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Checkout is unavailable')
      setLoading(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto py-12">
      <div className="mb-10">
        <div className="text-xs uppercase tracking-[0.22em] text-[#7c6af7] mb-3">
          Bounded server recovery
        </div>
        <h1 className="text-4xl md:text-5xl font-semibold tracking-[-2px] mb-4">
          Start with one protected host.
        </h1>
        <p className="text-[#94a3b8] text-lg max-w-2xl">
          Detect supported repeat incidents, run only approved recovery actions,
          verify the result, and escalate when the evidence is not strong enough.
        </p>
      </div>

      {canceled ? (
        <div className="mb-6 rounded-xl border border-[#334155] bg-[#111318] px-5 py-4 text-sm text-[#cbd5e1]">
          Checkout was canceled. Nothing was charged.
        </div>
      ) : null}

      <div className="grid gap-4 max-w-md mb-6">
        <div className="rounded-2xl border border-[#7c6af7] bg-[#151424] p-5">
          <div className="text-sm text-[#94a3b8] mb-2">Starter</div>
          <div className="text-2xl font-semibold mb-1">C$29/month</div>
          <div className="text-sm text-[#64748b]">1 host</div>
        </div>
      </div>

      <p className="mb-8 max-w-2xl text-sm leading-6 text-[#94a3b8]">
        Pro (C$99/month, up to 5 hosts) and Business (C$299/month, up to 20 hosts)
        remain reservation-only during this bounded validation. Reserve Pro or Business
        interest at <span className="text-[#a99cf8]">agentpulse.ca/signup</span>.
      </p>

      <div className="rounded-2xl border border-[#293241] bg-[#111318] p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="text-sm text-[#94a3b8]">Selected plan</div>
            <div className="text-xl font-semibold">Starter</div>
          </div>
          <button
            type="button"
            onClick={startCheckout}
            disabled={loading}
            className="rounded-xl bg-[#7c6af7] px-6 py-3 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? 'Opening secure checkout…' : 'Continue to secure checkout'}
          </button>
        </div>

        {error ? <p className="mt-4 text-sm text-[#f87171]">{error}</p> : null}

        <p className="mt-5 text-xs leading-5 text-[#64748b]">
          Starter checkout is currently provided under the product name AgentPulse.
          Payment is handled by Stripe. Pro and Business remain reservation-only.
          AgentPulse does not expose arbitrary remote shell access; host actions
          remain bounded by local policy and supported action types.
        </p>
      </div>
    </div>
  )
}
