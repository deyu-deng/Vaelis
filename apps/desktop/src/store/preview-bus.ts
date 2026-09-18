/**
 * North Star preview bus (desktop).
 *
 * Priority: artifact (产出) > progress (进度) > resource (资源).
 * Auto-push opens the preview rail; users can also open manually anytime.
 */

import { atom } from 'nanostores'

import {
  setCurrentSessionPreviewTarget,
  setPreviewTarget,
  type PreviewTarget,
  type PreviewRecordSource
} from './preview'
import { setPaneOpen } from './panes'
import { PREVIEW_PANE_ID, RIGHT_RAIL_PREVIEW_TAB_ID, selectRightRailTab } from './layout'

export type PreviewBusPriority = 'artifact' | 'progress' | 'resource'

export interface PreviewBusItem {
  autoOpen?: boolean
  id?: string
  kind?: 'file' | 'url' | 'text'
  meta?: Record<string, unknown>
  path?: string
  priority?: PreviewBusPriority | number
  text?: string
  title: string
  url?: string
}

const PRIORITY_RANK: Record<PreviewBusPriority, number> = {
  artifact: 0,
  progress: 1,
  resource: 2
}

/** Last bus items received this session (newest last). */
export const $previewBusItems = atom<PreviewBusItem[]>([])

function rank(priority: PreviewBusItem['priority']): number {
  if (typeof priority === 'number') {
    return priority
  }

  return PRIORITY_RANK[priority ?? 'artifact'] ?? 0
}

function toPreviewTarget(item: PreviewBusItem): PreviewTarget | null {
  if (item.url || item.kind === 'url') {
    return {
      kind: 'url',
      label: item.title,
      source: item.url || item.title,
      url: item.url || 'about:blank'
    }
  }

  if (item.path || item.kind === 'file') {
    const path = item.path || ''
    const url = path ? `file://${path}` : item.url || ''
    if (!url && !path) {
      return null
    }

    return {
      kind: 'file',
      label: item.title,
      path,
      source: path || url,
      url: url || `file://${path}`
    }
  }

  // text-only: surface as url data placeholder label; live pane still opens
  return {
    kind: 'url',
    label: item.title,
    source: item.text || item.title,
    url: 'about:blank'
  }
}

/**
 * Push a bus item. Higher-priority (lower rank) auto-open items win when
 * several arrive close together — callers should push artifacts first.
 */
export function pushPreviewBusItem(item: PreviewBusItem, source: PreviewRecordSource = 'tool-result'): PreviewBusItem {
  const next = [...$previewBusItems.get(), item].slice(-100)
  next.sort((a, b) => rank(a.priority) - rank(b.priority))
  $previewBusItems.set(next)

  const auto = item.autoOpen !== false
  if (auto) {
    const target = toPreviewTarget(item)
    if (target) {
      setCurrentSessionPreviewTarget(target, source)
      setPreviewTarget(target)
    } else {
      openPreviewPanelManual()
    }
  }

  return item
}

/** Manual open — user can open the preview rail anytime (North Star UX). */
export function openPreviewPanelManual(): void {
  setPaneOpen(PREVIEW_PANE_ID, true)
  selectRightRailTab(RIGHT_RAIL_PREVIEW_TAB_ID)
}

/** Apply the highest-priority pending auto item (e.g. after polling host bus). */
export function applyHighestPriorityPreview(): PreviewBusItem | null {
  const items = [...$previewBusItems.get()].sort((a, b) => rank(a.priority) - rank(b.priority))
  const hit = items.find(i => i.autoOpen !== false)
  if (!hit) {
    return null
  }
  pushPreviewBusItem(hit)
  return hit
}
