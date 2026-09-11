import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { $agendaEvents, $agendaLoading, $agendaError, $agendaSelectedId } from '@/store/agenda'

const getAgenda = vi.hoisted(() => vi.fn())
const confirmAgendaEvent = vi.hoisted(() => vi.fn())
const createAgendaEvent = vi.hoisted(() => vi.fn())
const deleteAgendaEvent = vi.hoisted(() => vi.fn())
const dismissAgendaEvent = vi.hoisted(() => vi.fn())
const updateAgendaEvent = vi.hoisted(() => vi.fn())

vi.mock('@/hermes', () => ({
  confirmAgendaEvent: (...args: unknown[]) => confirmAgendaEvent(...args),
  createAgendaEvent: (...args: unknown[]) => createAgendaEvent(...args),
  deleteAgendaEvent: (...args: unknown[]) => deleteAgendaEvent(...args),
  dismissAgendaEvent: (...args: unknown[]) => dismissAgendaEvent(...args),
  getAgenda: (...args: unknown[]) => getAgenda(...args),
  updateAgendaEvent: (...args: unknown[]) => updateAgendaEvent(...args)
}))

const getTalkerCollection = vi.hoisted(() => vi.fn())
const setTalkerMode = vi.hoisted(() => vi.fn())
const completeReview = vi.hoisted(() => vi.fn())

vi.mock('./talker/api', () => ({
  completeReview: (...args: unknown[]) => completeReview(...args),
  getTalkerCollection: (...args: unknown[]) => getTalkerCollection(...args),
  setTalkerMode: (...args: unknown[]) => setTalkerMode(...args)
}))

import { AgendaView } from './index'

describe('AgendaView empty board (WP-A7-EMPTY)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    $agendaEvents.set([])
    $agendaLoading.set(false)
    $agendaError.set(null)
    $agendaSelectedId.set(null)
    getAgenda.mockResolvedValue([])
    getTalkerCollection.mockResolvedValue({ reviewComplete: false, talkers: [] })
  })

  afterEach(() => {
    cleanup()
  })

  it('shows the start–end span in the list and the sender in the detail', async () => {
    const withEnd = {
      created_at: '2026-09-10T00:00:00Z',
      end_at: '2026-09-11T11:00:00',
      id: 'e-end',
      kind: 'meeting' as const,
      source: 'wechat' as const,
      start_at: '2026-09-11T09:00:00',
      status: 'confirmed' as const,
      title: '组会',
      updated_at: '2026-09-10T00:00:00Z'
    }
    const openEnded = {
      ...withEnd,
      end_at: null,
      evidence: { sender: '张老师', snippet: '明天上午九点组会', talker_name: '车辆2502' },
      id: 'e-open',
      title: '开题讨论'
    }

    getAgenda.mockResolvedValue([withEnd, openEnded])
    $agendaEvents.set([withEnd, openEnded])
    $agendaSelectedId.set('e-open')

    render(<AgendaView onClose={() => {}} />)

    // R-009: the list prints the span, and says so when the end is unwritten.
    expect(await screen.findByText('09:00–11:00')).toBeTruthy()
    expect(screen.getByText('09:00 · no end time')).toBeTruthy()

    // The detail names who said it (evidence.sender + conversation name).
    await waitFor(() => {
      expect(screen.getByText('张老师 · 车辆2502')).toBeTruthy()
    })
    // …and the open-ended entry shows the honest end value.
    expect(screen.getAllByText('no end time').length).toBeGreaterThanOrEqual(1)
  })

  it('falls back to unknown when the extractor could not name a sender', async () => {
    const anonymous = {
      created_at: '2026-09-10T00:00:00Z',
      end_at: null,
      evidence: { snippet: '改到三点' },
      id: 'e-anon',
      kind: 'task' as const,
      source: 'wechat' as const,
      start_at: '2026-09-11T15:00:00',
      status: 'pending' as const,
      title: '时间变更',
      updated_at: '2026-09-10T00:00:00Z'
    }

    getAgenda.mockResolvedValue([anonymous])
    $agendaEvents.set([anonymous])
    $agendaSelectedId.set('e-anon')

    render(<AgendaView onClose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('Unknown')).toBeTruthy()
    })
  })

  it('keeps the Session collection entry visible when no events exist', async () => {
    render(<AgendaView onClose={() => {}} />)

    // The collect entry row must survive the empty board (it was previously
    // swallowed by a dedicated PanelEmpty branch — the chicken-and-egg bug).
    // The label + the row title both render, so assert at least one of each.
    expect(screen.getAllByText('Session collection').length).toBeGreaterThanOrEqual(2)

    // The meta reflects the prefetched collection state, not a guess.
    await waitFor(() => {
      expect(screen.getByText('not started')).toBeTruthy()
    })

    // The rest of the empty board is still there: 暂无日程 + New entry.
    expect(screen.getByText('Nothing scheduled')).toBeTruthy()
    expect(screen.getByText('New entry')).toBeTruthy()
  })

  it('prefetches the talker collection state on mount', async () => {
    render(<AgendaView onClose={() => {}} />)

    await waitFor(() => {
      expect(getTalkerCollection).toHaveBeenCalled()
    })
  })
})
