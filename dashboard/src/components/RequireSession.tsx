/**
 * RequireSession — gate fleet routes behind a live cookie session.
 * Anonymous users go to /connect. Inactive entitlement can still open /account.
 */

import { useEffect, useState } from 'react'
import { Navigate, useLocation } from 'react-router'
import { loadSession, type SessionState } from '../auth/session'
import { ErrorState, LoadingState, Panel } from '../components/ui'

export default function RequireSession({
  children,
  allowInactive = false,
}: {
  children: React.ReactNode
  allowInactive?: boolean
}) {
  const location = useLocation()
  const [state, setState] = useState<SessionState>({ status: 'loading' })
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading' })
    setError(null)
    loadSession()
      .then((next) => {
        if (!cancelled) setState(next)
      })
      .catch((reason) => {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : 'Session check failed')
          setState({ status: 'anonymous' })
        }
      })
    return () => {
      cancelled = true
    }
  }, [location.pathname])

  if (state.status === 'loading') {
    return (
      <Panel>
        <LoadingState label="Checking session…" />
      </Panel>
    )
  }

  if (error) {
    return (
      <Panel>
        <ErrorState message={error} onRetry={() => setState({ status: 'loading' })} />
      </Panel>
    )
  }

  if (state.status === 'anonymous') {
    return <Navigate to="/connect" replace state={{ from: location.pathname }} />
  }

  if (state.status === 'inactive' && !allowInactive) {
    return <Navigate to="/account" replace />
  }

  return <>{children}</>
}
