import { describe, expect, it } from 'vitest'

import {
  hidesAgentSessions,
  shouldRenderProfileRail,
  showsSessionSurface,
  sidebarNavForLevel
} from './nav-level'

const NAV = [
  { id: 'new-session', label: 'new' },
  { id: 'skills', label: 'skills' },
  { id: 'messaging', label: 'messaging' },
  { id: 'artifacts', label: 'artifacts' }
]

describe('sidebarNavForLevel (WP-AGENT-MOUTH, 裁定 38/39)', () => {
  it('L1: Skills / Messaging / Artifacts, no New Session', () => {
    const items = sidebarNavForLevel(NAV, { l1: true, l2Id: null })

    expect(items.map(item => item.id)).toEqual(['skills', 'messaging', 'artifacts'])
  })

  it('L2: Messaging / Artifacts, no Skills and no New Session', () => {
    const items = sidebarNavForLevel(NAV, { l1: false, l2Id: 'agenda' })

    expect(items.map(item => item.id)).toEqual(['messaging', 'artifacts'])
  })

  it('mainline: unchanged, New Session stays (the session shell is not being torn down)', () => {
    const items = sidebarNavForLevel(NAV, { l1: false, l2Id: null })

    expect(items.map(item => item.id)).toEqual(['new-session', 'skills', 'messaging', 'artifacts'])
  })

  it('does not mutate the input array', () => {
    const before = NAV.map(item => item.id)

    sidebarNavForLevel(NAV, { l1: true, l2Id: null })

    expect(NAV.map(item => item.id)).toEqual(before)
  })
})

describe('showsSessionSurface (WP-AGENT-MOUTH, 裁定 38/39)', () => {
  it('no session search / pins / recents / blank state in the secretary shell', () => {
    expect(showsSessionSurface('l1')).toBe(false)
    expect(showsSessionSurface({ l2: 'agenda' })).toBe(false)
  })

  it('keeps them on the mainline', () => {
    expect(showsSessionSurface(null)).toBe(true)
    expect(showsSessionSurface(undefined)).toBe(true)
  })
})

describe('hidesAgentSessions (WP-AGENT-MOUTH, 裁定 38/39)', () => {
  it('an Agent row never expands into a session drawer — L1 and L2 alike', () => {
    expect(hidesAgentSessions('l1')).toBe(true)
    expect(hidesAgentSessions({ l2: 'agenda' })).toBe(true)
  })

  it('false on the mainline (it is not an agent rail)', () => {
    expect(hidesAgentSessions(null)).toBe(false)
    expect(hidesAgentSessions(undefined)).toBe(false)
  })
})

describe('shouldRenderProfileRail (WP-STUDIO, 裁定 36.0)', () => {
  it('hides the profile rail on L1 (secretary shell has no profile switcher)', () => {
    expect(shouldRenderProfileRail('l1')).toBe(false)
  })

  it('hides it on L2 as well', () => {
    expect(shouldRenderProfileRail({ l2: 'agenda' })).toBe(false)
  })

  it('keeps it on the mainline', () => {
    expect(shouldRenderProfileRail(null)).toBe(true)
    expect(shouldRenderProfileRail(undefined)).toBe(true)
  })
})
