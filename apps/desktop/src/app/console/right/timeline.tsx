/**
 * Agenda timeline (U3, spec §3.3) — presentational only.
 *
 * Reuse: each row is a `PanelListRow` (same primitive the left rail and the
 * overlays use). Pending rows surface a leading amber dot + a `pending` meta
 * tag; that is the "高亮" the spec asks for.
 */

import { PanelListRow, PanelSectionLabel } from '@/app/overlays/panel'
import { useI18n } from '@/i18n'
import type { AgendaEvent } from '@/types/hermes'

function localDateKey(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')

  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function clockOf(iso: string): string {
  return iso.length >= 16 ? iso.slice(11, 16) : iso
}

interface DaySectionProps {
  events: AgendaEvent[]
  label: string
}

function DaySection({ events, label }: DaySectionProps) {
  const { t } = useI18n()

  if (events.length === 0) {
    return null
  }

  return (
    <div className="flex flex-col gap-0.5">
      <PanelSectionLabel>{label}</PanelSectionLabel>
      {events.map(event => {
        const pending = event.status === 'pending'

        return (
          <PanelListRow
            active={false}
            dotClassName={pending ? 'bg-amber-500' : undefined}
            key={event.id}
            lead={<span className="shrink-0 tabular-nums text-[0.7rem] text-(--ui-text-tertiary)">{clockOf(event.start_at)}</span>}
            meta={pending ? <span className="text-amber-600/80">{t.console.timeline.pending}</span> : undefined}
            onSelect={() => {}}
            title={event.title}
          />
        )
      })}
    </div>
  )
}

export function Timeline({ events }: { events: AgendaEvent[] }) {
  const { t } = useI18n()
  const todayKey = localDateKey(new Date())
  const tomorrow = new Date()
  tomorrow.setDate(tomorrow.getDate() + 1)
  const tomorrowKey = localDateKey(tomorrow)

  const today = events.filter(event => event.start_at.slice(0, 10) === todayKey)
  const next = events.filter(event => event.start_at.slice(0, 10) === tomorrowKey)

  const other = events.filter(
    event => event.start_at.slice(0, 10) !== todayKey && event.start_at.slice(0, 10) !== tomorrowKey
  )

  if (events.length === 0) {
    return (
      <p className="px-2 py-6 text-center text-[0.72rem] text-(--ui-text-tertiary)">{t.console.timeline.emptyDesc}</p>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <DaySection events={today} label={t.console.timeline.today} />
      <DaySection events={next} label={t.console.timeline.tomorrow} />
      {other.length > 0 ? <DaySection events={other} label="…" /> : null}
    </div>
  )
}
