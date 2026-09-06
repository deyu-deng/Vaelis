import { atom, computed } from 'nanostores'

import { fetchAgents } from '../api'
import type { Agent } from '../types'

/**
 * Console data atoms (U1: agent rail).
 *
 * Mirrors the agenda store's contract: the backend owns the truth, these atoms
 * are a render cache, and anything that mutates writes the server's answer back
 * rather than patching optimistically.
 */

export const $consoleAgents = atom<Agent[]>([])
export const $consoleAgentsLoading = atom(true)
export const $consoleAgentsError = atom<null | string>(null)

/** Agents the user has to unblock — drives the rail's attention hint. */
export const $consoleBlockedAgents = computed($consoleAgents, agents =>
  agents.filter(agent => agent.status === 'awaiting_approval' || agent.status === 'error')
)

export const $consoleBlockedCount = computed($consoleBlockedAgents, blocked => blocked.length)

function messageOf(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause)
}

export function setConsoleAgents(agents: Agent[]): void {
  $consoleAgents.set(agents)
}

export function setConsoleAgentsError(message: null | string): void {
  $consoleAgentsError.set(message)
}

export function setConsoleAgentsLoading(loading: boolean): void {
  $consoleAgentsLoading.set(loading)
}

export async function refreshConsoleAgents(): Promise<void> {
  setConsoleAgentsLoading(true)

  try {
    setConsoleAgents(await fetchAgents())
    setConsoleAgentsError(null)
  } catch (cause) {
    setConsoleAgentsError(messageOf(cause))
  } finally {
    setConsoleAgentsLoading(false)
  }
}
