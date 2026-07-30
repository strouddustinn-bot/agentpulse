/**
 * Account — post-pay session status, enrollment token mint, billing portal.
 *
 * Access model: payment → claim → HttpOnly cookie session.
 * No browser bearer credentials. Enrollment token is shown once in memory only.
 */

import { useCallback, useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router'
import {
  ApiError,
  API_BASE_URL,
  buildEnrollmentGuidance,
  createBillingPortalSession,
  createBrowserEnrollmentToken,
  getAccount,
  type AccountResponse,
  type EnrollmentTokenResponse,
} from '../api/client'
import { isEntitlementUsable } from '../auth/session'
import { EmptyState, ErrorState, LoadingState, Panel } from '../components/ui'
import { formatDateTime } from '../lib/format'
import { navigateExternal } from '../lib/navigation'

function entitlementLabel(status: string): string {
  if (status === 'active') return 'Active'
  if (status === 'grace') return 'Grace (payment recovery window)'
  if (status === 'blocked') return 'Inactive'
  return status
}

function planLabel(plan: string): string {
  return plan.charAt(0).toUpperCase() + plan.slice(1)
}

export default function AccountPage() {
  const [account, setAccount] = useState<AccountResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [unauthorized, setUnauthorized] = useState(false)

  const [enrollBusy, setEnrollBusy] = useState(false)
  const [enrollError, setEnrollError] = useState<string | null>(null)
  const [issued, setIssued] = useState<EnrollmentTokenResponse | null>(null)
  const [copied, setCopied] = useState(false)

  const [portalBusy, setPortalBusy] = useState(false)
  const [portalError, setPortalError] = useState<string | null>(null)

  const guidance = buildEnrollmentGuidance(API_BASE_URL)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    setUnauthorized(false)
    getAccount()
      .then((value) => {
        setAccount(value)
        setLoading(false)
      })
      .catch((reason) => {
        if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) {
          setUnauthorized(true)
          setLoading(false)
          return
        }
        setError(reason instanceof Error ? reason.message : 'Could not load account')
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (unauthorized) return <Navigate to="/connect" replace />

  async function mintEnrollment() {
    setEnrollBusy(true)
    setEnrollError(null)
    setCopied(false)
    setIssued(null)
    try {
      const token = await createBrowserEnrollmentToken(600)
      setIssued(token)
    } catch (reason) {
      setEnrollError(reason instanceof Error ? reason.message : 'Enrollment token request failed')
    } finally {
      setEnrollBusy(false)
    }
  }

  async function openPortal() {
    setPortalBusy(true)
    setPortalError(null)
    try {
      const { portal_url } = await createBillingPortalSession()
      // Stripe portal is external; only open https billing hosts.
      const url = new URL(portal_url)
      if (url.protocol !== 'https:') throw new Error('Billing portal URL must be HTTPS')
      if (url.hostname !== 'billing.stripe.com' && !url.hostname.endsWith('.stripe.com')) {
        throw new Error('Billing portal URL host is not trusted')
      }
      navigateExternal(url.toString())
    } catch (reason) {
      setPortalError(reason instanceof Error ? reason.message : 'Billing portal unavailable')
      setPortalBusy(false)
    }
  }

  async function copyToken() {
    if (!issued) return
    try {
      await navigator.clipboard.writeText(issued.enrollment_token)
      setCopied(true)
    } catch {
      setEnrollError('Could not copy token. Select and copy it manually.')
    }
  }

  const usable = account ? isEntitlementUsable(account.entitlement_status) : false

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-[-1px]">Account</h1>
        <p className="text-sm text-[#64748b] mt-1">
          Subscription status, host enrollment, and billing. Access requires a completed checkout claim.
        </p>
      </div>

      {loading ? (
        <Panel>
          <LoadingState label="Loading account…" />
        </Panel>
      ) : error ? (
        <Panel>
          <ErrorState message={error} onRetry={load} />
        </Panel>
      ) : !account ? (
        <Panel>
          <EmptyState title="No account session" hint="Complete checkout claim to open the console." />
        </Panel>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <Panel className="p-7">
            <h2 className="text-lg font-semibold mb-4">Subscription</h2>
            <dl className="space-y-3 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-[#64748b]">Email</dt>
                <dd className="text-[#e2e8f0]">{account.email}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-[#64748b]">Plan</dt>
                <dd className="text-[#e2e8f0]">{planLabel(account.plan)}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-[#64748b]">Entitlement</dt>
                <dd className={usable ? 'text-[#22c55e]' : 'text-[#f87171]'}>
                  {entitlementLabel(account.entitlement_status)}
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-[#64748b]">Host limit</dt>
                <dd className="text-[#e2e8f0] tabular-nums">{account.agent_limit}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-[#64748b]">Period ends</dt>
                <dd className="text-[#94a3b8]">
                  {account.current_period_end
                    ? formatDateTime(account.current_period_end)
                    : '—'}
                </dd>
              </div>
              {account.grace_period_ends_at ? (
                <div className="flex justify-between gap-4">
                  <dt className="text-[#64748b]">Grace ends</dt>
                  <dd className="text-[#fbbf24]">{formatDateTime(account.grace_period_ends_at)}</dd>
                </div>
              ) : null}
            </dl>

            {!usable ? (
              <p className="mt-5 text-sm text-[#f87171]" role="status">
                Host enrollment is blocked until billing is active again.
              </p>
            ) : null}

            <div className="mt-6 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={openPortal}
                disabled={portalBusy}
                className="rounded-xl bg-[#7c6af7] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#6d5ce7] disabled:opacity-50"
              >
                {portalBusy ? 'Opening portal…' : 'Open billing portal'}
              </button>
              <Link
                to="/servers"
                className="rounded-xl border border-[#2d3048] px-4 py-2.5 text-sm text-[#e2e8f0] hover:border-[#7c6af7]"
              >
                View servers
              </Link>
            </div>
            {portalError ? <p className="mt-3 text-sm text-[#f87171]">{portalError}</p> : null}
          </Panel>

          <Panel className="p-7">
            <h2 className="text-lg font-semibold mb-2">Enroll a host</h2>
            <p className="text-sm text-[#64748b] mb-5">
              Mint a one-time token, then run the agent enroll command. The token is never placed on the
              process command line.
            </p>

            <ol className="list-decimal list-inside space-y-2 text-sm text-[#94a3b8] mb-5">
              <li>{guidance.configureHint}</li>
              <li>
                Run <code className="text-[#e2e8f0]">{guidance.enrollCommand}</code> and paste the token
                at the prompt, or pipe it into{' '}
                <code className="text-[#e2e8f0]">{guidance.stdinCommand}</code>
              </li>
            </ol>

            <button
              type="button"
              onClick={mintEnrollment}
              disabled={!usable || enrollBusy}
              className="rounded-xl bg-[#1a1d27] border border-[#2d3048] px-4 py-2.5 text-sm text-[#e2e8f0] hover:border-[#7c6af7] disabled:opacity-50"
            >
              {enrollBusy ? 'Creating token…' : 'Create enrollment token'}
            </button>

            {enrollError ? <p className="mt-3 text-sm text-[#f87171]">{enrollError}</p> : null}

            {issued ? (
              <div className="mt-5 rounded-2xl border border-[#2d3048] bg-[#0a0b0f] p-4">
                <div className="text-xs uppercase tracking-wider text-[#64748b] mb-2">
                  One-time token · expires {formatDateTime(issued.expires_at)}
                </div>
                <code
                  className="block break-all text-sm text-[#e2e8f0] select-all"
                  data-testid="enrollment-token"
                >
                  {issued.enrollment_token}
                </code>
                <div className="mt-3 flex gap-2">
                  <button
                    type="button"
                    onClick={copyToken}
                    className="rounded-lg border border-[#2d3048] px-3 py-1.5 text-xs text-[#e2e8f0] hover:border-[#7c6af7]"
                  >
                    {copied ? 'Copied' : 'Copy token'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setIssued(null)}
                    className="rounded-lg border border-transparent px-3 py-1.5 text-xs text-[#64748b] hover:text-[#e2e8f0]"
                  >
                    Hide
                  </button>
                </div>
                <p className="mt-3 text-xs text-[#64748b]">
                  This value is held in page memory only. Refreshing the page discards it; mint again if needed.
                </p>
              </div>
            ) : null}
          </Panel>
        </div>
      )}
    </div>
  )
}
