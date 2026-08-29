import { useStore } from '@nanostores/react'
import type * as React from 'react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { PageLoader } from '@/components/page-loader'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  confirmAgendaEvent,
  createAgendaEvent,
  deleteAgendaEvent,
  dismissAgendaEvent,
  getAgenda,
  updateAgendaEvent
} from '@/hermes'
import { type Translations, useI18n } from '@/i18n'
import {
  $agendaError,
  $agendaEvents,
  $agendaLoading,
  $agendaPendingCount,
  $agendaSelected,
  removeAgendaEvent,
  setAgendaError,
  setAgendaEvents,
  setAgendaLoading,
  setAgendaSelectedId,
  upsertAgendaEvent
} from '@/store/agenda'
import { notify, notifyError } from '@/store/notifications'
import type { AgendaEvent, AgendaKind } from '@/types/hermes'

import {
  Panel,
  PanelAction,
  PanelAddButton,
  PanelBlock,
  PanelBody,
  PanelDetail,
  PanelEmpty,
  PanelHeader,
  PanelList,
  PanelListRow,
  PanelMeta,
  type PanelPillTone,
  PanelPill,
  PanelRowMenu,
  PanelSectionLabel
} from '../overlays/panel'

// Board refresh cadence. The spec allows up to 10s staleness (ADR-0008), and
// polling keeps us off SSE/WebSocket plumbing for a single-user desktop.
const POLL_INTERVAL_MS = 8000

const KINDS: readonly AgendaKind[] = ['meeting', 'ddl', 'class', 'task']

const STATUS_TONE: Record<string, PanelPillTone> = {
  cancelled: 'muted',
  confirmed: 'good',
  pending: 'warn'
}

const STATUS_DOT: Record<string, string> = {
  cancelled: 'bg-muted-foreground/40',
  confirmed: 'bg-emerald-500',
  pending: 'bg-amber-500'
}

interface EditorState {
  event?: AgendaEvent
  mode: 'closed' | 'create' | 'edit'
}

function startOfToday(): Date {
  const now = new Date()

  return new Date(now.getFullYear(), now.getMonth(), now.getDate())
}

/** Backend speaks naive local ISO strings; keep the desktop on the same shape. */
function toLocalIso(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')

  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:00`
}

function toInputValue(iso: string): string {
  return iso.length >= 16 ? iso.slice(0, 16) : iso
}

function fromInputValue(value: string): string {
  return value.length === 16 ? `${value}:00` : value
}

function clockOf(iso: string): string {
  return iso.length >= 16 ? iso.slice(11, 16) : iso
}

function dayKeyOf(iso: string): string {
  return iso.slice(0, 10)
}

function dayLabel(dayKey: string, a: Translations['agenda']): string {
  const today = toLocalIso(startOfToday()).slice(0, 10)
  const tomorrowDate = startOfToday()

  tomorrowDate.setDate(tomorrowDate.getDate() + 1)

  const tomorrow = toLocalIso(tomorrowDate).slice(0, 10)

  if (dayKey === today) {
    return a.today
  }

  if (dayKey === tomorrow) {
    return a.tomorrow
  }

  return dayKey
}

function isDeleted(value: unknown): value is { deleted: true; id: string } {
  return typeof value === 'object' && value !== null && 'deleted' in value
}

interface AgendaViewProps extends React.ComponentProps<'section'> {
  onClose: () => void
}

export function AgendaView({ onClose }: AgendaViewProps) {
  const { t } = useI18n()
  const a = t.agenda
  const events = useStore($agendaEvents)
  const loading = useStore($agendaLoading)
  const error = useStore($agendaError)
  const selected = useStore($agendaSelected)
  const pendingCount = useStore($agendaPendingCount)

  const [editor, setEditor] = useState<EditorState>({ mode: 'closed' })
  const [busyId, setBusyId] = useState<null | string>(null)

  const refresh = useCallback(async () => {
    try {
      const rows = await getAgenda()

      setAgendaEvents(rows)
      setAgendaError(null)
    } catch (cause) {
      setAgendaError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setAgendaLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()

    const intervalId = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        void refresh()
      }
    }, POLL_INTERVAL_MS)

    return () => window.clearInterval(intervalId)
  }, [refresh])

  const grouped = useMemo(() => {
    const buckets = new Map<string, AgendaEvent[]>()

    for (const event of events) {
      const key = dayKeyOf(event.start_at)
      const bucket = buckets.get(key)

      if (bucket) {
        bucket.push(event)
      } else {
        buckets.set(key, [event])
      }
    }

    return [...buckets.entries()].sort(([left], [right]) => left.localeCompare(right))
  }, [events])

  async function handleConfirm(event: AgendaEvent) {
    setBusyId(event.id)

    try {
      upsertAgendaEvent(await confirmAgendaEvent(event.id))
      notify({ message: a.confirmed })
    } catch (cause) {
      notifyError(cause, a.actionFailed)
    } finally {
      setBusyId(null)
    }
  }

  async function handleDismiss(event: AgendaEvent) {
    setBusyId(event.id)

    try {
      const result = await dismissAgendaEvent(event.id)

      if (isDeleted(result)) {
        removeAgendaEvent(event.id)
      } else {
        upsertAgendaEvent(result)
      }

      notify({ message: a.dismissed })
    } catch (cause) {
      notifyError(cause, a.actionFailed)
    } finally {
      setBusyId(null)
    }
  }

  async function handleDelete(event: AgendaEvent) {
    setBusyId(event.id)

    try {
      await deleteAgendaEvent(event.id)
      removeAgendaEvent(event.id)
      notify({ message: a.deleted })
    } catch (cause) {
      notifyError(cause, a.actionFailed)
    } finally {
      setBusyId(null)
    }
  }

  async function handleEditorSave(values: { kind: AgendaKind; startAt: string; title: string }) {
    if (editor.mode === 'edit' && editor.event) {
      upsertAgendaEvent(
        await updateAgendaEvent(editor.event.id, {
          kind: values.kind,
          start_at: values.startAt,
          title: values.title
        })
      )
    } else {
      const created = await createAgendaEvent({
        kind: values.kind,
        start_at: values.startAt,
        title: values.title
      })

      upsertAgendaEvent(created)
      setAgendaSelectedId(created.id)
    }

    setEditor({ mode: 'closed' })
  }

  return (
    <Panel closeLabel={a.close} onClose={onClose}>
      {loading && events.length === 0 ? (
        <PageLoader label={a.loading} />
      ) : error && events.length === 0 ? (
        <PanelEmpty description={error} icon="warning" title={a.loadFailed} />
      ) : events.length === 0 ? (
        <PanelEmpty
          action={
            <Button onClick={() => setEditor({ mode: 'create' })} size="sm">
              {a.newEvent}
            </Button>
          }
          description={a.emptyDesc}
          icon="calendar"
          title={a.emptyTitle}
        />
      ) : (
        <>
          <PanelHeader
            subtitle={pendingCount > 0 ? a.pendingCount(pendingCount) : a.count(events.length)}
            title={a.title}
          />
          <PanelBody>
            <PanelList>
              {grouped.map(([dayKey, dayEvents]) => (
                <div key={dayKey}>
                  <PanelSectionLabel className="px-2 pb-1 pt-2">{dayLabel(dayKey, a)}</PanelSectionLabel>
                  {dayEvents.map(event => (
                    <PanelListRow
                      active={selected?.id === event.id}
                      dotClassName={STATUS_DOT[event.status] ?? 'bg-muted-foreground'}
                      key={event.id}
                      menu={
                        <PanelRowMenu
                          items={[
                            { icon: 'edit', label: a.edit, onSelect: () => setEditor({ event, mode: 'edit' }) },
                            {
                              icon: 'trash',
                              label: t.common.delete,
                              onSelect: () => void handleDelete(event),
                              tone: 'danger'
                            }
                          ]}
                        />
                      }
                      meta={clockOf(event.start_at)}
                      onSelect={() => setAgendaSelectedId(event.id)}
                      rowKey={event.id}
                      title={event.title}
                    />
                  ))}
                </div>
              ))}
              <PanelAddButton label={a.newEvent} onClick={() => setEditor({ mode: 'create' })} />
            </PanelList>

            {selected ? (
              <AgendaDetail
                a={a}
                busy={busyId === selected.id}
                event={selected}
                onConfirm={() => void handleConfirm(selected)}
                onDismiss={() => void handleDismiss(selected)}
                onEdit={() => setEditor({ event: selected, mode: 'edit' })}
              />
            ) : (
              <PanelEmpty description={a.emptyDesc} icon="calendar" />
            )}
          </PanelBody>
        </>
      )}

      <AgendaEditorDialog
        a={a}
        editor={editor}
        onClose={() => setEditor({ mode: 'closed' })}
        onSave={handleEditorSave}
      />
    </Panel>
  )
}

function AgendaDetail({
  a,
  busy,
  event,
  onConfirm,
  onDismiss,
  onEdit
}: {
  a: Translations['agenda']
  busy: boolean
  event: AgendaEvent
  onConfirm: () => void
  onDismiss: () => void
  onEdit: () => void
}) {
  const isPending = event.status === 'pending'
  const previous = event.prev_value

  return (
    <PanelDetail>
      <header className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h3 className="text-[0.95rem] font-semibold tracking-tight text-foreground">{event.title}</h3>
            <PanelPill tone={STATUS_TONE[event.status] ?? 'muted'}>{a.statuses[event.status]}</PanelPill>
          </div>
          <div className="flex shrink-0 items-center gap-0.5">
            {isPending ? (
              <>
                <PanelAction disabled={busy} icon="check" onClick={onConfirm}>
                  {a.confirm}
                </PanelAction>
                <PanelAction disabled={busy} icon="discard" onClick={onDismiss}>
                  {a.dismiss}
                </PanelAction>
              </>
            ) : (
              <PanelAction disabled={busy} icon="edit" onClick={onEdit}>
                {a.edit}
              </PanelAction>
            )}
          </div>
        </div>

        <PanelMeta
          rows={[
            { label: a.startLabel, value: event.start_at.replace('T', ' ') },
            { label: a.kindLabel, value: a.kinds[event.kind] },
            { label: a.sourceLabel, value: a.sources[event.source] }
          ]}
        />
      </header>

      {isPending && previous ? (
        <section className="space-y-1.5">
          <PanelSectionLabel>{a.changeLabel}</PanelSectionLabel>
          <PanelMeta
            rows={[
              ...(previous.title && previous.title !== event.title
                ? [{ label: a.titleField, value: `${previous.title} → ${event.title}` }]
                : []),
              ...(previous.start_at && previous.start_at !== event.start_at
                ? [{ label: a.startLabel, value: `${previous.start_at.replace('T', ' ')} → ${event.start_at.replace('T', ' ')}` }]
                : [])
            ]}
          />
        </section>
      ) : null}

      {event.evidence?.snippet ? (
        <section className="space-y-1.5">
          <PanelSectionLabel>{a.evidenceLabel}</PanelSectionLabel>
          <PanelBlock>{event.evidence.snippet}</PanelBlock>
        </section>
      ) : null}
    </PanelDetail>
  )
}

function AgendaEditorDialog({
  a,
  editor,
  onClose,
  onSave
}: {
  a: Translations['agenda']
  editor: EditorState
  onClose: () => void
  onSave: (values: { kind: AgendaKind; startAt: string; title: string }) => Promise<void>
}) {
  const { t } = useI18n()
  const open = editor.mode !== 'closed'
  const initial = editor.mode === 'edit' ? editor.event : undefined

  const [title, setTitle] = useState('')
  const [startAt, setStartAt] = useState('')
  const [kind, setKind] = useState<AgendaKind>('task')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<null | string>(null)

  useEffect(() => {
    if (!open) {
      return
    }

    const fallback = new Date()

    fallback.setMinutes(0, 0, 0)
    fallback.setHours(fallback.getHours() + 1)

    setTitle(initial?.title ?? '')
    setStartAt(toInputValue(initial?.start_at ?? toLocalIso(fallback)))
    setKind(initial?.kind ?? 'task')
    setError(null)
    setSaving(false)
  }, [initial, open])

  async function handleSubmit(submitEvent: React.FormEvent) {
    submitEvent.preventDefault()

    if (!title.trim() || !startAt) {
      setError(a.titleTimeRequired)

      return
    }

    setSaving(true)
    setError(null)

    try {
      await onSave({ kind, startAt: fromInputValue(startAt), title: title.trim() })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
      setSaving(false)
    }
  }

  return (
    <Dialog onOpenChange={value => !value && !saving && onClose()} open={open}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{editor.mode === 'edit' ? a.editTitle : a.createTitle}</DialogTitle>
        </DialogHeader>

        <form className="space-y-3" onSubmit={handleSubmit}>
          <Input
            aria-label={a.titleField}
            onChange={changeEvent => setTitle(changeEvent.target.value)}
            placeholder={a.titlePlaceholder}
            value={title}
          />
          <Input
            aria-label={a.startLabel}
            onChange={changeEvent => setStartAt(changeEvent.target.value)}
            type="datetime-local"
            value={startAt}
          />
          <Select onValueChange={value => setKind(value as AgendaKind)} value={kind}>
            <SelectTrigger aria-label={a.kindLabel}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {KINDS.map(value => (
                <SelectItem key={value} value={value}>
                  {a.kinds[value]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {error ? <p className="text-xs text-destructive">{error}</p> : null}

          <DialogFooter>
            <Button disabled={saving} onClick={onClose} type="button" variant="outline">
              {t.common.cancel}
            </Button>
            <Button disabled={saving} type="submit">
              {t.common.save}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
