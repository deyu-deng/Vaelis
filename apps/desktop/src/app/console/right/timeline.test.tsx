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

describe('Timeline', () => {
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

  it('highlights pending rows with the pending tag and a leading dot', () => {
    render(<Timeline events={[event('p', dateAt(0, 10), { status: 'pending' })]} />)

    expect(screen.getByText('pending')).toBeTruthy()
    // The pending meta is wrapped in an amber span — the tag text is present.
    expect(screen.getByText('event-p')).toBeTruthy()
  })

  it('renders the clock time as the row lead', () => {
    const at = dateAt(0, 8)

    render(<Timeline events={[event('c', at)]} />)

    expect(screen.getByText('08:00')).toBeTruthy()
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
