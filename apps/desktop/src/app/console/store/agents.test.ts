import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchAgents } from '../api'
import type { Agent } from '../types'
import { MOCK_L2_MODEL } from '../types'

import {
  $consoleAgents,
  $consoleAgentsError,
  $consoleAgentsLoading,
  $consoleBlockedAgents,
  $consoleBlockedCount,
  refreshConsoleAgents,
  setConsoleAgents
} from './agents'

vi.mock('../api', () => ({
  fetchAgendaEvents: vi.fn(),
  fetchAgents: vi.fn()
}))

const fetchAgentsMock = vi.mocked(fetchAgents)

function agent(id: string, status: Agent['status']): Agent {
  return { id, model: MOCK_L2_MODEL, name: id, status, todayCalls: 1 }
}

describe('console agents store', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    $consoleAgents.set([])
    $consoleAgentsError.set(null)
    $consoleAgentsLoading.set(true)
  })

  it('counts only the states a human must unblock', () => {
    setConsoleAgents([
      agent('idle', 'idle'),
      agent('working', 'working'),
      agent('waiting', 'awaiting_approval'),
      agent('broken', 'error')
    ])

    expect($consoleBlockedAgents.get().map(a => a.id)).toEqual(['waiting', 'broken'])
    expect($consoleBlockedCount.get()).toBe(2)
  })

  it('is not blocked when every agent is healthy', () => {
    setConsoleAgents([agent('idle', 'idle'), agent('working', 'working')])

    expect($consoleBlockedCount.get()).toBe(0)
  })

  it('publishes agents and clears the error on success', async () => {
    fetchAgentsMock.mockResolvedValue([agent('agenda-secretary', 'working')])

    await refreshConsoleAgents()

    expect($consoleAgents.get()).toHaveLength(1)
    expect($consoleAgentsError.get()).toBeNull()
    expect($consoleAgentsLoading.get()).toBe(false)
  })

  it('records the failure and stops loading when the backend is unreachable', async () => {
    fetchAgentsMock.mockRejectedValue(new Error('offline'))

    await refreshConsoleAgents()

    expect($consoleAgentsError.get()).toBe('offline')
    expect($consoleAgentsLoading.get()).toBe(false)
    // A failed refresh must not blank a rail that already had rows.
    expect($consoleAgents.get()).toEqual([])
  })

  it('keeps surviving rows when a later refresh fails', async () => {
    setConsoleAgents([agent('agenda-secretary', 'working')])
    fetchAgentsMock.mockRejectedValue(new Error('offline'))

    await refreshConsoleAgents()

    expect($consoleAgents.get()).toHaveLength(1)
    expect($consoleAgentsError.get()).toBe('offline')
  })
})
