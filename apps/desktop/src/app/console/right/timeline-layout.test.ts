import { describe, expect, it } from 'vitest'

import type { AgendaEvent } from '@/types/hermes'

import {
  dayKeysOf,
  HOUR_HEIGHT,
  layoutDay,
  MIN_BLOCK_HEIGHT,
  minutesOf
} from './timeline-layout'

const DAY = '2026-09-11'

function event(id: string, startAt: string, endAt: null | string = null, status: AgendaEvent['status'] = 'confirmed'): AgendaEvent {
  const now = '2026-09-10T00:00:00Z'

  return {
    confirm_seq: null,
    created_at: now,
    end_at: endAt,
    id,
    kind: 'task',
    source: 'manual',
    start_at: startAt,
    status,
    title: `event-${id}`,
    updated_at: now
  }
}

describe('layoutDay', () => {
  it('returns null for a day with no events', () => {
    expect(layoutDay([event('a', `${DAY}T09:00:00`)], '2026-09-12')).toBeNull()
  })

  it('always exposes at least the 08:00–23:00 tick marks', () => {
    const day = layoutDay([event('a', `${DAY}T09:00:00`, `${DAY}T11:00:00`)], DAY)

    expect(day).not.toBeNull()
    expect(day?.hours[0]).toBe(8)
    expect(day?.hours.at(-1)).toBe(23)
    expect(day?.spanStartMinutes).toBe(8 * 60)
    expect(day?.spanEndMinutes).toBe(24 * 60)
  })

  it('sizes a block from start_at to end_at', () => {
    const day = layoutDay([event('a', `${DAY}T09:00:00`, `${DAY}T11:00:00`)], DAY)
    const block = day?.blocks[0]

    expect(block?.startClock).toBe('09:00')
    expect(block?.endClock).toBe('11:00')
    expect(block?.openEnded).toBe(false)
    // Two hours → two hour-heights; 09:00 is one hour past the 08:00 axis start.
    expect(block?.heightPx).toBe(2 * HOUR_HEIGHT)
    expect(block?.topPx).toBe(HOUR_HEIGHT)
  })

  it('never invents an end: a missing end_at becomes a minimum-height marker', () => {
    const day = layoutDay([event('a', `${DAY}T09:00:00`)], DAY)
    const block = day?.blocks[0]

    expect(block?.openEnded).toBe(true)
    expect(block?.endClock).toBeNull()
    expect(block?.heightPx).toBe(MIN_BLOCK_HEIGHT)
  })

  it('widens the axis for entries outside 08:00–23:00', () => {
    const early = layoutDay([event('a', `${DAY}T06:30:00`, `${DAY}T07:00:00`)], DAY)
    const late = layoutDay([event('b', `${DAY}T23:40:00`, `${DAY}T23:59:00`)], DAY)

    expect(early?.spanStartMinutes).toBe(6 * 60)
    expect(late?.spanEndMinutes).toBeGreaterThan(24 * 60 - 1)
    // Even widened, the tick marks stay on whole hours inside the span.
    expect(late?.hours.at(-1)).toBe(23)
  })

  it('sorts blocks by start and gives overlaps their own column', () => {
    const day = layoutDay(
      [
        event('late', `${DAY}T15:00:00`, `${DAY}T16:00:00`),
        event('early', `${DAY}T09:00:00`, `${DAY}T10:00:00`),
        event('clash', `${DAY}T09:30:00`, `${DAY}T10:30:00`)
      ],
      DAY
    )

    expect(day?.blocks.map(block => block.event.id)).toEqual(['early', 'clash', 'late'])
    expect(day?.blocks.map(block => block.column)).toEqual([0, 1, 0])
  })

  it('flags pending blocks so the rail can keep them amber', () => {
    const day = layoutDay([event('p', `${DAY}T10:00:00`, null, 'pending')], DAY)

    expect(day?.blocks[0].pending).toBe(true)
  })
})

describe('dayKeysOf / minutesOf', () => {
  it('lists event days chronologically without duplicates', () => {
    expect(dayKeysOf([event('a', `${DAY}T09:00:00`), event('b', `${DAY}T18:00:00`), event('c', '2026-09-12T08:00:00')])).toEqual([
      DAY,
      '2026-09-12'
    ])
  })

  it('parses the clock part defensively', () => {
    expect(minutesOf(`${DAY}T09:30:00`)).toBe(9 * 60 + 30)
    expect(minutesOf('')).toBe(0)
    expect(minutesOf('nonsense')).toBe(0)
  })
})
