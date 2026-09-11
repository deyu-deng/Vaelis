/**
 * Agenda timeline (U3, spec §3.3) — the L1 right rail's day view (R-009 / R-020).
 *
 * Rendered as a **vertical day axis**: hour ticks from 08:00 to 23:00 (widened
 * when the day holds anything outside that window) with each event drawn as a
 * block between its `start_at` and `end_at`. A missing `end_at` stays honest —
 * the block is a marker labelled「未写结束」, never a fabricated hour.
 *
 * Layout math lives in `./timeline-layout` (pure, unit-tested); this file only
 * renders. Pending entries keep the amber treatment.
 */

import { useMemo } from 'react'

import { PanelSectionLabel } from '@/app/overlays/panel'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'
import type { AgendaEvent } from '@/types/hermes'

import {
  dayKeysOf,
  HOUR_HEIGHT,
  layoutDay,
  OVERLAP_OFFSET_PX,
  type TimelineDay
} from './timeline-layout'

function localDateKey(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')

  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function padHour(hour: number): string {
  return `${String(hour).padStart(2, '0')}:00`
}

function DayAxis({
  day,
  label,
  noEndLabel,
  pendingLabel
}: {
  day: TimelineDay
  label: string
  noEndLabel: string
  pendingLabel: string
}) {
  return (
    <div className="flex flex-col gap-1" data-testid={`timeline-day-${day.key}`}>
      <PanelSectionLabel>{label}</PanelSectionLabel>
      <div className="relative" style={{ height: day.totalHeightPx }}>
        {day.hours.map(hour => (
          <div
            className="pointer-events-none absolute inset-x-0 flex items-center gap-1.5"
            key={hour}
            style={{ top: ((hour * 60 - day.spanStartMinutes) / 60) * HOUR_HEIGHT }}
          >
            <span className="w-9 shrink-0 tabular-nums text-[0.62rem] text-(--ui-text-tertiary)">
              {padHour(hour)}
            </span>
            <span className="h-px flex-1 bg-border/60" />
          </div>
        ))}

        {day.blocks.map(block => (
          <div
            className={cn(
              'absolute right-1 overflow-hidden rounded-md border px-1.5 py-0.5',
              block.pending
                ? 'border-amber-500/50 bg-amber-500/10'
                : block.event.status === 'cancelled'
                  ? 'border-border/60 bg-muted/40 opacity-70'
                  : 'border-emerald-600/40 bg-emerald-500/5'
            )}
            data-testid={`timeline-block-${block.event.id}`}
            key={block.event.id}
            style={{
              height: Math.max(block.heightPx, 20),
              left: `calc(2.5rem + ${block.column * OVERLAP_OFFSET_PX}px)`,
              top: block.topPx
            }}
          >
            <div className="flex min-w-0 items-center gap-1">
              <span className="shrink-0 tabular-nums text-[0.62rem] text-(--ui-text-tertiary)">
                {block.startClock}
                {block.endClock ? `–${block.endClock}` : ''}
              </span>
              {block.pending ? (
                <span className="shrink-0 text-[0.62rem] text-amber-600/90">{pendingLabel}</span>
              ) : null}
              <span className="min-w-0 truncate text-[0.72rem] text-foreground/90">{block.event.title}</span>
            </div>
            {block.openEnded ? (
              <span className="block truncate text-[0.6rem] text-(--ui-text-tertiary)">{noEndLabel}</span>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  )
}

export function Timeline({ events }: { events: AgendaEvent[] }) {
  const { t } = useI18n()
  const todayKey = localDateKey(new Date())
  const tomorrowDate = new Date()
  tomorrowDate.setDate(tomorrowDate.getDate() + 1)
  const tomorrowKey = localDateKey(tomorrowDate)

  const days = useMemo(
    () =>
      dayKeysOf(events)
        .map(dayKey => layoutDay(events, dayKey))
        .filter((day): day is TimelineDay => day !== null),
    [events]
  )

  if (days.length === 0) {
    return (
      <p className="px-2 py-6 text-center text-[0.72rem] text-(--ui-text-tertiary)">{t.console.timeline.emptyDesc}</p>
    )
  }

  return (
    <div className="flex flex-col gap-4 px-1">
      {days.map(day => (
        <DayAxis
          day={day}
          key={day.key}
          label={
            day.key === todayKey
              ? t.console.timeline.today
              : day.key === tomorrowKey
                ? t.console.timeline.tomorrow
                : day.key
          }
          noEndLabel={t.agenda.noEnd}
          pendingLabel={t.console.timeline.pending}
        />
      ))}
    </div>
  )
}
