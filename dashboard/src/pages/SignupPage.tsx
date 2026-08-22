import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'

type Plan = 'starter' | 'pro' | 'business'

type CheckoutResponse = {
  checkout_url: string
  checkout_session_id: string
  livemode: boolean
  expires_at: number
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8787').replace(/\/+$/, '')

const plans: Array<{ id: Plan; name: string; price: string; scope: string }> = [
  { id: 'starter', name: 'Starter', price: 'C$29/month', scope: '1 host' },
  { id: 'pro', name: 'Pro', price: 'C$99/month', scope: 'Up to 5 hosts' },
  { id: 'business', name: 'Business', price: 'C$299/month', scope: 'Up to 20 hosts' },
]

function isPlan(value: string | null): value is Plan {
  return value === 'starter' || value === 'pro' || value === 'business'
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

async function createCheckout(plan: Plan): Promise<CheckoutResponse> {
  const response = await fetch(`${API_BASE_URL}/v1/billing/checkout`, {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan }),
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
  const [params, setParams] = useSearchParams()
  const initialPlan = useMemo<Plan>(() => {
    const requested = params.get('plan')
    return isPlan(requested) ? requested : 'starter'
  }, [params])
  const [selectedPlan, setSelectedPlan] = useState<Plan>(initialPlan)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const canceled = params.get('canceled') === '1'

  function selectPlan(plan: Plan) {
    setSelectedPlan(plan)
    const next = new URLSearchParams(params)
    next.set('plan', plan)
    next.delete('canceled')
    setParams(next, { replace: true })
  }

  async function startCheckout() {
    setLoading(true)
    setError(null)
    try {
      const checkout = await createCheckout(selectedPlan)
      window.location.assign(checkout.checkout_url)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Checkout is unavailable')
      setLoading(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto py-12">
      <div className="mb-10">
        <div className="text-xs uppercase tracking-[0.22em] text-[#7c6af7] mb-3">Bounded server recovery</div>
        <h1 className="text-4xl md:text-5xl font-semibold tracking-[-2px] mb-4">
          Choose the host scope you want protected.
        </h1>
        <p className="text-[#94a3b8] text-lg max-w-2xl">
          Detect supported repeat incidents, run only approved recovery actions, verify the result, and escalate when the evidence is not strong enough.
        </p>
      </div>

      {canceled ? (
        <div className="mb-6 rounded-xl border border-[#334155] bg-[#111318] px-5 py-4 text-sm text-[#cbd5e1]">
          Checkout was canceled. Nothing was charged.
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3 mb-8">
        {plans.map((plan) => {
          const selected = selectedPlan === plan.id
          return (
            <button
              type="button"
              key={plan.id}
              onClick={() => selectPlan(plan.id)}
              className={`text-left rounded-2xl border p-5 transition-colors ${
                selected
                  ? 'border-[#7c6af7] bg-[#151424]'
                  : 'border-[#293241] bg-[#111318] hover:border-[#475569]'
              }`}
              aria-pressed={selected}
            >
              <div className="text-sm text-[#94a3b8] mb-2">{plan.name}</div>
              <div className="text-2xl font-semibold mb-1">{plan.price}</div>
              <div className="text-sm text-[#64748b]">{plan.scope}</div>
            </button>
          )
        })}
      </div>

      <div className="rounded-2xl border border-[#293241] bg-[#111318] p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="text-sm text-[#94a3b8]">Selected plan</div>
            <div className="text-xl font-semibold">{plans.find((plan) => plan.id === selectedPlan)?.name}</div>
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
          Checkout is currently provided under the product name AgentPulse. Payment is handled by Stripe. AgentPulse does not expose arbitrary remote shell access; host actions remain bounded by local policy and supported action types.
        </p>
      </div>
    </div>
  )
}
