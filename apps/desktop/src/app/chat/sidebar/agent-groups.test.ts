import { describe, expect, it } from 'vitest'

import type { Agent } from '@/app/console/types'

import {
  AGENT_CATEGORY_ORDER,
  agentProfileIdSet,
  groupAgentsByCategory,
  isL1SessionProfile,
  normalizeAgentCategory
} from './agent-groups'

function agent(overrides: Partial<Agent> & { id: string; name: string }): Agent {
  return { status: 'idle', todayCalls: 0, ...overrides }
}

describe('normalizeAgentCategory', () => {
  it('passes through the four known categories (case-insensitive)', () => {
    expect(normalizeAgentCategory('projects')).toBe('projects')
    expect(normalizeAgentCategory('BUTLER')).toBe('butler')
    expect(normalizeAgentCategory(' events ')).toBe('events')
    expect(normalizeAgentCategory('Research')).toBe('research')
  })

  it('folds missing / unknown categories into butler (legacy agents)', () => {
    expect(normalizeAgentCategory(undefined)).toBe('butler')
    expect(normalizeAgentCategory(null)).toBe('butler')
    expect(normalizeAgentCategory('')).toBe('butler')
    expect(normalizeAgentCategory('ops')).toBe('butler')
  })
})

describe('groupAgentsByCategory', () => {
  it('buckets into the fixed PROJECTS/BUTLER/EVENTS/RESEARCH order', () => {
    const groups = groupAgentsByCategory([
      agent({ id: 'r1', name: '论文调研', category: 'research' }),
      agent({ id: 'p1', name: '量化交易', category: 'projects' }),
      agent({ id: 'b1', name: '日程秘书' }),
      agent({ id: 'e1', name: '日程提醒', category: 'events' })
    ])

    expect(groups.map(group => group.category)).toEqual(['projects', 'butler', 'events', 'research'])
    expect(groups[1]?.agents.map(row => row.id)).toEqual(['b1'])
    expect(AGENT_CATEGORY_ORDER).toEqual(['projects', 'butler', 'events', 'research'])
  })

  it('omits empty groups and sorts agents by name within a group', () => {
    const groups = groupAgentsByCategory([
      agent({ id: 'b2', name: '管家乙' }),
      agent({ id: 'b1', name: '管家甲' }),
      agent({ id: 'legacy', name: '旧代理', category: 'unknown-cat' })
    ])

    expect(groups).toHaveLength(1)
    expect(groups[0]?.category).toBe('butler')
    expect(groups[0]?.agents.map(row => row.id)).toEqual(['b1', 'b2', 'legacy'])
  })

  it('returns an empty list for no agents', () => {
    expect(groupAgentsByCategory([])).toEqual([])
  })
})

describe('agentProfileIdSet / isL1SessionProfile', () => {
  it('collects non-blank agent profiles', () => {
    expect(
      agentProfileIdSet([
        agent({ id: 'a', name: 'A', profile: 'simulation' }),
        agent({ id: 'b', name: 'B' }),
        agent({ id: 'c', name: 'C', profile: '  ' })
      ])
    ).toEqual(new Set(['simulation']))
  })

  it('treats default/master as L1 identity profiles, others as agent-owned', () => {
    expect(isL1SessionProfile('default')).toBe(true)
    expect(isL1SessionProfile('master')).toBe(true)
    expect(isL1SessionProfile(undefined)).toBe(true)
    expect(isL1SessionProfile('simulation')).toBe(false)
  })
})
