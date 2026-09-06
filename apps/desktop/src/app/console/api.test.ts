import { beforeEach, describe, expect, it, vi } from 'vitest'

import { $agendaEvents } from '@/store/agenda'
import type { AgendaEvent } from '@/types/hermes'

const confirmAgendaEvent = vi.hoisted(() => vi.fn())
const dismissAgendaEvent = vi.hoisted(() => vi.fn())

vi.mock('@/hermes', () => ({
  confirmAgendaEvent: (...args: unknown[]) => confirmAgendaEvent(...args),
  dismissAgendaEvent: (...args: unknown[]) => dismissAgendaEvent(...args)
}))

import {
  confirmAgendaEventAction,
  createAgent,
  getAgentSubagentLog,
  getOutsourcedSessionTarget
} from './api'

function baseEvent(): AgendaEvent {
  const now = '2026-08-30T08:00:00Z'

  return {
    confirm_seq: 12,
    created_at: now,
    end_at: null,
    id: 'e1',
    kind: 'class',
    source: 'wechat',
    start_at: '2026-08-31T10:00:00',
    status: 'pending',
    title: '高数课改期',
    updated_at: now
  }
}

describe('confirmAgendaEventAction (U5-seg1 write-back)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    $agendaEvents.set([baseEvent()])
  })

  it('upserts the confirmed row into the shared agenda store', async () => {
    const confirmed = { ...baseEvent(), status: 'confirmed' as const }
    confirmAgendaEvent.mockResolvedValue(confirmed)

    await confirmAgendaEventAction('e1', 'confirm')

    expect(confirmAgendaEvent).toHaveBeenCalledWith('e1')
    expect($agendaEvents.get().find(e => e.id === 'e1')?.status).toBe('confirmed')
  })

  it('removes the row when the backend reports a deletion on dismiss', async () => {
    dismissAgendaEvent.mockResolvedValue({ deleted: true, id: 'e1', ok: true })

    await confirmAgendaEventAction('e1', 'dismiss')

    expect(dismissAgendaEvent).toHaveBeenCalledWith('e1')
    expect($agendaEvents.get().some(e => e.id === 'e1')).toBe(false)
  })

  it('upserts the returned row when dismiss answers with a row', async () => {
    const dismissed = { ...baseEvent(), status: 'cancelled' as const }
    dismissAgendaEvent.mockResolvedValue(dismissed)

    await confirmAgendaEventAction('e1', 'dismiss')

    expect($agendaEvents.get().find(e => e.id === 'e1')?.status).toBe('cancelled')
  })
})

// [WAIT-BACKEND] both are mocked: neither endpoint exists in the §5 contract
// yet. The tests pin the shape the UI depends on so swapping in the real
// request is a one-function change.
describe('createAgent (WP-L2-FE)', () => {
  it('POSTs /api/agents with the create request', async () => {
    const api = vi.fn().mockResolvedValue({
      data: { id: 'vaelis-code', name: 'vaelis-code', status: 'idle', todayCalls: 0 },
      ok: true
    })
    const previous = (window as { hermesDesktop?: unknown }).hermesDesktop

    Object.defineProperty(window, 'hermesDesktop', {
      configurable: true,
      value: { api }
    })

    try {
      const created = await createAgent({ id: 'vaelis-code', role: 'l2_project' })

      expect(api).toHaveBeenCalledWith({
        body: { id: 'vaelis-code', role: 'l2_project' },
        method: 'POST',
        path: '/api/agents'
      })
      expect(created.id).toBe('vaelis-code')
    } finally {
      if (previous) {
        Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: previous })
      } else {
        Reflect.deleteProperty(window, 'hermesDesktop')
      }
    }
  })
})

describe('S2 mock endpoints (U4)', () => {
  it('returns the mocked work log for a known sub-agent', async () => {
    const log = await getAgentSubagentLog('agenda-secretary', 'sub-extractor')

    expect(log.lines.length).toBeGreaterThan(0)
  })

  it('rejects an unknown sub-agent so the dialog can show its error state', async () => {
    await expect(getAgentSubagentLog('agenda-secretary', 'nope')).rejects.toThrow(/not found/)
  })

  it('returns a deep-link target for an outsourced conversation', async () => {
    const target = await getOutsourcedSessionTarget('cursor', 'cur 1')

    expect(target.url).toContain('cursor')
    expect(target.url).toContain('cur%201')
  })
})
