import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import type { AgendaEvent } from '@/types/hermes'

import { Timeline } from './timeline'
import { shouldRefreshAgendaOnBusyChange } from './use-agenda-timeline'

function event(id: string, startAt: string, overrides: Partial<AgendaEvent> = {}): AgendaEvent {
  const now = '2026-08-30T00:00:00Z'

  return {
    confirm_seq: null,
    created_at: now,
    end_at: null,
    id,
    kind: 'task',
    source: 'manual',
    start_at: startAt,
    status: 'confirmed',
    title: `event-${id}`,
    updated_at: now,
    ...overrides
  }
}

function dateAt(offsetDays: number, hour: number): string {
  const date = new Date()
  date.setDate(date.getDate() + offsetDays)
  date.setHours(hour, 0, 0, 0)

  const pad = (value: number) => String(value).padStart(2, '0')

  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(hour)}:00:00`
}

describe('Timeline (day axis)', () => {
  afterEach(() => {
    cleanup()
  })

  it('shows the empty hint when there are no events', () => {
    render(<Timeline events={[]} />)

    expect(screen.getByText('The secretary has nothing scheduled yet.')).toBeTruthy()
  })

  it('groups today and tomorrow under their section labels', () => {
    render(<Timeline events={[event('a', dateAt(0, 9)), event('b', dateAt(1, 14))]} />)

    expect(screen.getByText('Today')).toBeTruthy()
    expect(screen.getByText('Tomorrow')).toBeTruthy()
    expect(screen.getByText('event-a')).toBeTruthy()
    expect(screen.getByText('event-b')).toBeTruthy()
  })

  it('draws the 08:00–23:00 hour axis', () => {
    render(<Timeline events={[event('a', dateAt(0, 9), { end_at: dateAt(0, 11) })]} />)

    // Tick labels bracket the default window (the 08:00 block also prints its
    // own start, hence the *All* queries).
    expect(screen.getAllByText('08:00').length).toBeGreaterThan(0)
    expect(screen.getByText('23:00')).toBeTruthy()
  })

  it('prints the start–end span on the block', () => {
    render(<Timeline events={[event('s', dateAt(0, 9), { end_at: dateAt(0, 11) })]} />)

    expect(screen.getByText('09:00–11:00')).toBeTruthy()
  })

  it('says the end is unwritten instead of inventing an hour', () => {
    render(<Timeline events={[event('o', dateAt(0, 9))]} />)

    expect(screen.getByText('no end time')).toBeTruthy()
  })

  it('keeps the pending tag on pending entries', () => {
    render(<Timeline events={[event('p', dateAt(0, 10), { status: 'pending' })]} />)

    expect(screen.getByText('pending')).toBeTruthy()
    expect(screen.getByText('event-p')).toBeTruthy()
  })
})

describe('shouldRefreshAgendaOnBusyChange (WP-G2)', () => {
  it('fires only on the busy → idle falling edge', () => {
    expect(shouldRefreshAgendaOnBusyChange(true, false)).toBe(true)
    expect(shouldRefreshAgendaOnBusyChange(false, false)).toBe(false)
    expect(shouldRefreshAgendaOnBusyChange(false, true)).toBe(false)
    expect(shouldRefreshAgendaOnBusyChange(true, true)).toBe(false)
  })
})
