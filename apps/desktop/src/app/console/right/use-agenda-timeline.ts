/**
 * Right-rail agenda timeline (U3, spec §3.3).
 *
 * The data is the SAME store the full-screen board (`app/agenda`) renders
 * (`@/store/agenda` → `getAgenda` in `@/hermes`) — there is exactly one
 * `events` source of truth, per spec §3.3 "完全同一份". This hook just makes
 * sure that store is populated and kept fresh (≤10s, ADR-0008) when the
 * console is the only mounted consumer. The board's own poll is independent
 * and writes the same atoms, so whichever view mounts first owns the poll.
 */

import { useEffect } from 'react'

import { $agendaEvents, setAgendaError, setAgendaEvents, setAgendaLoading } from '@/store/agenda'
import { $busy } from '@/store/session'

import { fetchAllAgendaEvents } from '../api'

// ADR-0008 SLA: changes visible ≤10s.  Poll at 8s to stay inside the SLA
// with margin for network latency.  Future: upgrade to push (SSE/WebSocket)
// when the backend supports it.
const POLL_INTERVAL_MS = 8000

let inFlight: Promise<void> | null = null
let queued = false

async function refresh(): Promise<void> {
  if (inFlight) {
    queued = true

    return inFlight
  }

  setAgendaLoading(true)

  inFlight = (async () => {
    try {
      const rows = await fetchAllAgendaEvents()

      setAgendaEvents(rows)
      setAgendaError(null)
    } catch (error) {
      setAgendaError(error instanceof Error ? error.message : String(error))
    } finally {
      setAgendaLoading(false)
      inFlight = null

      if (queued) {
        queued = false
        void refresh()
      }
    }
  })()

  return inFlight
}

/** Force an immediate refresh — wired to the rail's manual retry action. */
export async function refreshAgendaTimeline(): Promise<void> {
  await refresh()
}

/** L1 right rail should refetch as soon as a turn settles, not wait for the 8s poll. */
export function shouldRefreshAgendaOnBusyChange(previousBusy: boolean, nextBusy: boolean): boolean {
  return previousBusy && !nextBusy
}

/**
 * Poll/seed the agenda store only while the consumer is actually mounted as
 * the L1 right rail (WP-D). `enabled: false` (L2, legacy chat, full-pane
 * views) leaves the store untouched — no seed, no interval — so a non-secretary
 * route never keeps an 8s network loop alive.
 *
 * WP-G2: when `$busy` falls (a `submitText` turn finished), refresh immediately
 * so a secretary_ask pipeline's SQLite writes show up without waiting for poll.
 */
export function useAgendaTimeline(enabled: boolean): void {
  useEffect(() => {
    if (!enabled) {
      return
    }

    // `$agendaLoading` starts true (spinner). That is "not fetched yet", not
    // "someone else's request is in flight" — always seed an empty store.
    if ($agendaEvents.get().length === 0) {
      void refresh()
    }

    const intervalId = window.setInterval(() => {
      void refresh()
    }, POLL_INTERVAL_MS)

    let previousBusy = $busy.get()
    const unsubscribeBusy = $busy.listen(busy => {
      if (shouldRefreshAgendaOnBusyChange(previousBusy, busy)) {
        void refresh()
      }

      previousBusy = busy
    })

    return () => {
      window.clearInterval(intervalId)
      unsubscribeBusy()
    }
  }, [enabled])
}
