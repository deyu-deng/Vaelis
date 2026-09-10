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
