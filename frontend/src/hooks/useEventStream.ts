/** GET /api/events is the authoritative feed: voice answers only reach us through it.
 *
 * EventSource reconnects itself while it can. When it gives up (readyState CLOSED) we
 * rebuild it with a capped backoff. On every (re)connect we replay /api/turns/latest so
 * a turn produced while we were disconnected is never lost; the caller dedupes by
 * turn_id. */
import { useEffect, useRef, useState } from 'react'
import { getLatestTurn } from '../api/client'
import type { DatasetInfo, Turn } from '../api/types'

const MAX_BACKOFF_MS = 15_000

export interface EventStreamHandlers {
  onTurn: (turn: Turn) => void
  onDataset: (info: DatasetInfo) => void
}

export function useEventStream(handlers: EventStreamHandlers): boolean {
  const [connected, setConnected] = useState(false)
  const latest = useRef(handlers)

  useEffect(() => {
    latest.current = handlers
  })

  useEffect(() => {
    // jsdom has no EventSource; the rest of the app stays usable without the feed.
    if (typeof EventSource === 'undefined') return

    let source: EventSource | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    let attempt = 0
    let stopped = false

    const catchUp = async () => {
      try {
        const turn = await getLatestTurn()
        if (turn && !stopped) latest.current.onTurn(turn)
      } catch {
        // A failed catch-up is not worth surfacing; the live feed is already open.
      }
    }

    const parse = <T,>(event: Event): T | null => {
      try {
        return JSON.parse((event as MessageEvent<string>).data) as T
      } catch {
        return null
      }
    }

    const connect = () => {
      source = new EventSource('/api/events')

      source.addEventListener('open', () => {
        attempt = 0
        setConnected(true)
        void catchUp()
      })

      source.addEventListener('turn', (event) => {
        const turn = parse<Turn>(event)
        if (turn) latest.current.onTurn(turn)
      })

      source.addEventListener('dataset', (event) => {
        const info = parse<DatasetInfo>(event)
        if (info) latest.current.onDataset(info)
      })

      source.addEventListener('error', () => {
        setConnected(false)
        if (stopped || source?.readyState !== EventSource.CLOSED) return
        source.close()
        attempt += 1
        timer = setTimeout(connect, Math.min(1000 * 2 ** attempt, MAX_BACKOFF_MS))
      })
    }

    connect()

    return () => {
      stopped = true
      if (timer) clearTimeout(timer)
      source?.close()
    }
  }, [])

  return connected
}
