/**
 * Live SSE subscription to /api/events.
 *
 * Exactly one EventSource per mounted hook: the effect creates it, the
 * cleanup closes it, so React 19 StrictMode's mount→cleanup→mount dance
 * never leaves two streams open. Reconnection is delegated to the browser's
 * native EventSource retry — we do NOT close() on error and we run no timer
 * loop of our own, so there is exactly one reconnect mechanism.
 */

import { useEffect, useRef, useState } from 'react'
import type {
  HistoryEntry,
  LiveMetricSample,
  SseMsg,
  StateSnapshot,
} from './types'

/** Live samples kept in memory for chart merging (~30min at 15s cadence). */
const MAX_LIVE_SAMPLES = 120

export interface Live {
  state: StateSnapshot | null
  history: HistoryEntry[]
  /** True while the SSE stream is open. */
  live: boolean
  /** Most recent instantaneous metric values (for stat readouts). */
  lastMetric: Record<string, number>
  /** Rolling buffer of live samples, oldest→newest (for chart merging). */
  liveSamples: LiveMetricSample[]
}

function parseMsg(raw: string): SseMsg | null {
  try {
    const msg = JSON.parse(raw) as SseMsg
    if (msg && typeof msg === 'object' && 'type' in msg) return msg
  } catch {
    // malformed frame — skip rather than kill the stream
  }
  return null
}

export function useLive(): Live {
  const [state, setState] = useState<StateSnapshot | null>(null)
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [live, setLive] = useState(false)
  const [lastMetric, setLastMetric] = useState<Record<string, number>>({})
  const [liveSamples, setLiveSamples] = useState<LiveMetricSample[]>([])
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    const es = new EventSource('/api/events')
    esRef.current = es

    es.onopen = () => setLive(true)

    es.onerror = () => {
      // Native EventSource retries on its own; just reflect the drop.
      setLive(false)
    }

    es.onmessage = (ev: MessageEvent<string>) => {
      const msg = parseMsg(ev.data)
      if (!msg) return
      switch (msg.type) {
        case 'state':
          setState(msg.data)
          break
        case 'history':
          if (Array.isArray(msg.data)) setHistory(msg.data)
          break
        case 'metrics':
          setLastMetric(msg.data.values)
          setLiveSamples((prev) => {
            const next = prev.length >= MAX_LIVE_SAMPLES ? prev.slice(1) : prev.slice()
            next.push(msg.data)
            return next
          })
          break
      }
    }

    return () => {
      es.close()
      if (esRef.current === es) esRef.current = null
    }
  }, [])

  return { state, history, live, lastMetric, liveSamples }
}
