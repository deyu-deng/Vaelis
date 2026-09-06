/**
 * Talker collection UI (A7) — mounted inside a `Dialog` from the board.
 *
 * Four states (loading / error / data) plus two data sub-views:
 * - pre-review (`reviewComplete === false`): a "未开始采集" banner + the
 *   backlog of recent talkers for one-click collect/exclude, closed by
 *   "完成审查并开始采集".
 * - post-review: the `pending` talkers (fail-closed new sessions) for
 *   one-click collect/exclude, or an empty state when none remain.
 *
 * Reuse: `PageLoader` / `PanelEmpty` / `PanelAction` / `PanelPill` /
 * `PanelSectionLabel` from `@/app/overlays/panel`, `Button` + `Codicon`. No
 * new visual language — same row chrome as the board/agent rails.
 */

import { useStore } from '@nanostores/react'
import { useEffect, useState } from 'react'

import { PanelAction, PanelEmpty, PanelPill, type PanelPillTone, PanelSectionLabel } from '@/app/overlays/panel'
import { PageLoader } from '@/components/page-loader'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'

import type { TalkerStatus } from './api'
import {
  $talkerError,
  $talkerLoading,
  $talkerState,
  collectTalker,
  excludeTalker,
  finishReview,
  refreshTalkerCollection
} from './store'

const MODE_TONE: Record<TalkerStatus, PanelPillTone> = {
  excluded: 'bad',
  known: 'good',
  pending: 'muted'
}

function TalkerRow({
  busy,
  name,
  onCollect,
  onExclude,
  status
}: {
  busy: boolean
  name: string
  onCollect: () => void
  onExclude: () => void
  status: TalkerStatus
}) {
  const { t } = useI18n()
  const c = t.agenda.collect

  return (
    <div className="group/row row-hover relative flex h-7 w-full items-center gap-2 rounded-md pl-2 pr-1 text-[0.78rem] hover:text-foreground">
      <span className="min-w-0 flex-1 truncate font-medium text-foreground/85">{name}</span>
      {status !== 'pending' ? (
        <PanelPill tone={MODE_TONE[status]}>{status === 'known' ? c.modeKnown : c.modeExcluded}</PanelPill>
      ) : null}
      <PanelAction disabled={busy} icon="check" onClick={onCollect}>
        {c.collect}
      </PanelAction>
      <PanelAction disabled={busy} icon="discard" onClick={onExclude}>
        {c.exclude}
      </PanelAction>
    </div>
  )
}

export function TalkerCollection({ onClose }: { onClose: () => void }) {
  const { t } = useI18n()
  const c = t.agenda.collect
  const state = useStore($talkerState)
  const loading = useStore($talkerLoading)
  const error = useStore($talkerError)
  const [busyId, setBusyId] = useState<null | string>(null)

  useEffect(() => {
    void refreshTalkerCollection()
  }, [])

  if (loading && !state) {
    return <PageLoader label={c.title} />
  }

  if (error && !state) {
    return (
      <PanelEmpty
        action={
          <Button onClick={() => void refreshTalkerCollection()} size="xs" variant="ghost">
            {c.retry}
          </Button>
        }
        description={error}
        icon="warning"
        title={c.loadFailed}
      />
    )
  }

  if (!state) {
    return null
  }

  const pending = state.talkers.filter(talker => talker.status === 'pending')

  if (!state.reviewComplete) {
    return (
      <div className="space-y-3">
        <PanelEmpty
          description={c.notStartedDesc}
          icon="shield"
          title={c.notStartedTitle}
        />

        <PanelSectionLabel className="px-1">{c.backlogTitle}</PanelSectionLabel>
        <div className="space-y-0.5">
          {state.talkers.map(talker => (
            <TalkerRow
              busy={busyId === talker.id}
              key={talker.id}
              name={talker.name}
              onCollect={() => void act(talker.id, 'collect')}
              onExclude={() => void act(talker.id, 'exclude')}
              status={talker.status}
            />
          ))}
        </div>

        <div className="flex justify-end pt-1">
          <Button disabled={busyId !== null} onClick={() => void actFinish()} size="sm">
            {c.finishReview}
          </Button>
        </div>
      </div>
    )
  }

  if (pending.length === 0) {
    return (
      <PanelEmpty
        action={
          <Button onClick={onClose} size="xs" variant="ghost">
            {t.common.close}
          </Button>
        }
        description={c.pendingEmptyDesc}
        icon="checklist"
        title={c.pendingEmptyTitle}
      />
    )
  }

  return (
    <div className="space-y-3">
      <PanelSectionLabel className="px-1">{c.pendingTitle}</PanelSectionLabel>
      <div className="space-y-0.5">
        {pending.map(talker => (
          <TalkerRow
            busy={busyId === talker.id}
            key={talker.id}
            name={talker.name}
            onCollect={() => void act(talker.id, 'collect')}
            onExclude={() => void act(talker.id, 'exclude')}
            status={talker.status}
          />
        ))}
      </div>
    </div>
  )

  async function act(id: string, mode: 'collect' | 'exclude') {
    setBusyId(id)

    try {
      if (mode === 'collect') {
        await collectTalker(id)
      } else {
        await excludeTalker(id)
      }
    } finally {
      setBusyId(null)
    }
  }

  async function actFinish() {
    setBusyId('__review__')

    try {
      await finishReview()
    } finally {
      setBusyId(null)
    }
  }
}
