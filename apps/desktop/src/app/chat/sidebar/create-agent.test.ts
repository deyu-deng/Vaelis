import { describe, expect, it } from 'vitest'

import {
  AGENT_CATEGORY_VALUES,
  DEFAULT_AGENT_CATEGORY,
  agentIdFromName,
  buildCreateAgentBody,
  isCreateAgentCategoryBlocked,
  type AgentCategory
} from './create-agent'

describe('agentIdFromName', () => {
  it('lowerCases and hyphenates', () => {
    expect(agentIdFromName('My Project')).toBe('my-project')
    expect(agentIdFromName('VaElis Code')).toBe('vaelis-code')
  })

  it('falls back to an l2- timestamped slug for empty/CJK-only input', () => {
    expect(agentIdFromName('').startsWith('l2-')).toBe(true)
    expect(agentIdFromName('   ').startsWith('l2-')).toBe(true)
  })
})

describe('buildCreateAgentBody', () => {
  it('forwards category into the POST body with the l2_project role', () => {
    const body = buildCreateAgentBody('My Project', 'research')

    expect(body).toEqual({
      id: 'my-project',
      role: 'l2_project',
      category: 'research'
    })
  })

  it('keeps the default category when none is overridden', () => {
    const body = buildCreateAgentBody('Butler Bot', DEFAULT_AGENT_CATEGORY)

    expect(body.category).toBe(DEFAULT_AGENT_CATEGORY)
    expect(body.role).toBe('l2_project')
  })
})

describe('isCreateAgentCategoryBlocked', () => {
  it('blocks only the events category', () => {
    expect(isCreateAgentCategoryBlocked('events')).toBe(true)

    for (const cat of AGENT_CATEGORY_VALUES.filter(c => c !== 'events')) {
      expect(isCreateAgentCategoryBlocked(cat as AgentCategory)).toBe(false)
    }
  })
})
