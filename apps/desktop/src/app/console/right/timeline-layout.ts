/**
 * Day-axis layout for the L1 right-rail agenda timeline (R-009 / R-020).
 *
 * Pure math, no React and no i18n — `timeline.tsx` renders exactly what this
 * returns, and the vitest suite pins the arithmetic (hour span, block height,
 * open-ended events) without mounting anything.
 *
 * Rules that come straight from the ruling:
 * - The axis always shows at least 08:00 → 23:00 and stretches to fit anything
 *   outside that window, so an early or late entry is never clipped away.
 * - A block's height follows `start_at` → `end_at`. A missing `end_at` is NOT
 *   stretched into a fake hour: it gets the minimum height and is flagged
 *   `openEnded` so the UI can say「未写结束」.
 */

import type { AgendaEvent } from '@/types/hermes'

export const TIMELINE_START_HOUR = 8
export const TIMELINE_END_HOUR = 23

/** Pixels per hour on the day axis. */
export const HOUR_HEIGHT = 44
/** Minimum block height so a zero-length (or open-ended) entry stays readable. */
export const MIN_BLOCK_HEIGHT = 22
/** Horizontal nudge between overlapping blocks, in pixels. */
export const OVERLAP_OFFSET_PX = 10

export function dayKeyOf(iso: string): string {
  return (iso ?? '').slice(0, 10)
}

/** Clock part of a naive local ISO timestamp (`2026-09-11T09:30:00` → `09:30`). */
export function clockOf(iso: string): string {
  return iso && iso.length >= 16 ? iso.slice(11, 16) : iso
}

/** Minutes since midnight for a naive local ISO timestamp. */
export function minutesOf(iso: string): number {
  if (!iso || iso.length < 16) {
    return 0
  }

  const hours = Number(iso.slice(11, 13))
  const minutes = Number(iso.slice(14, 16))
  const safeHours = Number.isFinite(hours) ? hours : 0
  const safeMinutes = Number.isFinite(minutes) ? minutes : 0

  return safeHours * 60 + safeMinutes
}

export interface TimelineBlock {
  /** Overlap column index (0-based) — the renderer indents by it. */
  column: number
  /** `end_at` clock, or null when the entry is open-ended. */
  endClock: null | string
  event: AgendaEvent
  heightPx: number
  /** True when `end_at` is missing (never guessed). */
  openEnded: boolean
  pending: boolean
  startClock: string
  topPx: number
}

export interface TimelineDay {
  blocks: TimelineBlock[]
  /** Whole hours to draw as ticks, inclusive. */
  hours: number[]
  key: string
  /** Axis end (minutes since midnight) — the container height derives from it. */
  spanEndMinutes: number
  /** Axis start (minutes since midnight). */
  spanStartMinutes: number
  totalHeightPx: number
}

function pxOf(minutes: number, spanStartMinutes: number): number {
  return ((minutes - spanStartMinutes) / 60) * HOUR_HEIGHT
}

/**
 * Lay out one day. Returns null when no event starts on `dayKey`.
 *
 * Events are sorted by start; overlaps get a column so two blocks at the same
 * time stay both readable.
 */
export function layoutDay(events: AgendaEvent[], dayKey: string): TimelineDay | null {
  const rows = events
    .filter(event => dayKeyOf(event.start_at) === dayKey)
    .slice()
    .sort((left, right) => minutesOf(left.start_at) - minutesOf(right.start_at))

  if (rows.length === 0) {
    return null
  }

  const starts = rows.map(event => minutesOf(event.start_at))
  const ends = rows.map(event => (event.end_at ? minutesOf(event.end_at) : minutesOf(event.start_at)))

  const minMinutes = Math.min(...starts)
  const maxMinutes = Math.max(...ends, ...starts)

  // At least 08:00–23:00; widen to whatever the day actually contains.
  const spanStartMinutes = Math.min(TIMELINE_START_HOUR * 60, Math.floor(minMinutes / 60) * 60)
  const spanEndMinutes = Math.max((TIMELINE_END_HOUR + 1) * 60, Math.ceil(maxMinutes / 60) * 60)

  // Ticks are hour marks *inside* the span: 08:00–23:00 by default, so the
  // default axis never shows a "24:00" label.
  const hours: number[] = []
  for (let hour = spanStartMinutes / 60; hour * 60 < spanEndMinutes; hour += 1) {
    hours.push(hour)
  }

  // Greedy overlap columns: reuse a column once its last block has ended.
  const columnEnds: number[] = []
  const blocks: TimelineBlock[] = rows.map(event => {
    const startMinutes = minutesOf(event.start_at)
    const endMinutes = event.end_at ? minutesOf(event.end_at) : null
    const openEnded = endMinutes === null

    let column = columnEnds.findIndex(end => end <= startMinutes)

    if (column === -1) {
      column = columnEnds.length
    }

    columnEnds[column] = openEnded ? startMinutes + 30 : Math.max(endMinutes as number, startMinutes + 30)

    const naturalHeight = openEnded
      ? MIN_BLOCK_HEIGHT
      : ((endMinutes as number) - startMinutes) / 60 * HOUR_HEIGHT

    return {
      column,
      endClock: event.end_at ? clockOf(event.end_at) : null,
      event,
      heightPx: Math.max(MIN_BLOCK_HEIGHT, Math.round(naturalHeight)),
      openEnded,
      pending: event.status === 'pending',
      startClock: clockOf(event.start_at),
      topPx: Math.round(pxOf(startMinutes, spanStartMinutes))
    }
  })

  return {
    blocks,
    hours,
    key: dayKey,
    spanEndMinutes,
    spanStartMinutes,
    totalHeightPx: Math.round(pxOf(spanEndMinutes, spanStartMinutes))
  }
}

/** Day keys that carry events, chronological. */
export function dayKeysOf(events: AgendaEvent[]): string[] {
  return [...new Set(events.map(event => dayKeyOf(event.start_at)).filter(Boolean))].sort()
}
