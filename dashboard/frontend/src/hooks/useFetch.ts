/**
 * useFetch — minimal on-load fetch hook with loading / error / retry.
 *
 * Read-only by design: fires exactly once per dependency change (no
 * polling loops), and exposes `retry` for error-state affordances.
 */

import { useCallback, useEffect, useState } from 'react'

export interface FetchState<T> {
  data: T | null
  loading: boolean
  error: string | null
  retry: () => void
}

export function useFetch<T>(fetcher: () => Promise<T>, deps: readonly unknown[]): FetchState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  const retry = useCallback(() => setAttempt((n) => n + 1), [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    fetcher()
      .then((result) => {
        if (!cancelled) {
          setData(result)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Unexpected error')
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, attempt])

  return { data, loading, error, retry }
}
