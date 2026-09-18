/**
 * Talker collection store (A7).
 *
 * Render cache for the board's "session collection" entry. The backend owns
 * the truth; every mutation goes through `./api` and then the server's answer
 * (or the optimistic status flip) is written back here — never optimistic-only.
 * Mirrors `apps/desktop/src/store/agenda.ts`.
 */

import { atom } from 'nanostores'

import { bulkSetTalkerMode, completeReview, getTalkerCollection, setTalkerMode } from './api'
import type { TalkerCollection } from './api'

export const $talkerState = atom<null | TalkerCollection>(null)
export const $talkerLoading = atom(false)
export const $talkerError = atom<null | string>(null)

export async function refreshTalkerCollection(): Promise<void> {
  $talkerLoading.set(true)

  try {
    const state = await getTalkerCollection()

    $talkerState.set(state)
    $talkerError.set(null)
  } catch (cause) {
    $talkerError.set(cause instanceof Error ? cause.message : String(cause))
  } finally {
    $talkerLoading.set(false)
  }
}

async function withRefresh(action: () => Promise<void>): Promise<void> {
  await action()
  await refreshTalkerCollection()
}

export function collectTalker(id: string): Promise<void> {
  return withRefresh(() => setTalkerMode(id, 'collect'))
}

export function excludeTalker(id: string): Promise<void> {
  return withRefresh(() => setTalkerMode(id, 'exclude'))
}

/** One bulk call for many excludes — same endpoint, single refresh. */
export function excludeTalkers(ids: string[]): Promise<void> {
  if (ids.length === 0) {
    return Promise.resolve()
  }

  return withRefresh(() => bulkSetTalkerMode(ids, 'excluded'))
}

export function finishReview(): Promise<void> {
  return withRefresh(() => completeReview())
}
