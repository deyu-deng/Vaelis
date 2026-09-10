import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { $talkerError, $talkerLoading, $talkerState } from './store'
import { TalkerCollection } from './talker-collection'
import { talkerKind } from './talker-kind'

const getTalkerCollection = vi.hoisted(() => vi.fn())
const setTalkerMode = vi.hoisted(() => vi.fn())
const bulkSetTalkerMode = vi.hoisted(() => vi.fn())
const completeReview = vi.hoisted(() => vi.fn())

vi.mock('./api', () => ({
  bulkSetTalkerMode: (...args: unknown[]) => bulkSetTalkerMode(...args),
  completeReview: (...args: unknown[]) => completeReview(...args),
  getTalkerCollection: (...args: unknown[]) => getTalkerCollection(...args),
  setTalkerMode: (...args: unknown[]) => setTalkerMode(...args)
}))

function talker(id: string, status: 'known' | 'excluded' | 'pending') {
  return { id, name: `Talker ${id}`, status }
}

describe('TalkerCollection (A7)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    $talkerState.set(null)
    $talkerLoading.set(false)
    $talkerError.set(null)
    setTalkerMode.mockResolvedValue(undefined)
    bulkSetTalkerMode.mockResolvedValue(undefined)
    completeReview.mockResolvedValue(undefined)
  })

  afterEach(() => {
    cleanup()
  })

  it('shows the loading state before data lands', () => {
    getTalkerCollection.mockReturnValue(new Promise<never>(() => {}))

    render(<TalkerCollection onClose={() => {}} />)

    expect(screen.getByRole('status', { name: 'Session collection' })).toBeTruthy()
  })

  it('shows the error state with a retry action', async () => {
    getTalkerCollection.mockRejectedValue(new Error('down'))

    render(<TalkerCollection onClose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('Could not load collection status.')).toBeTruthy()
    })
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy()
  })

  it('shows the pre-review backlog with a “not collecting yet” banner', async () => {
    getTalkerCollection.mockResolvedValue({
      reviewComplete: false,
      talkers: [talker('a', 'pending'), talker('b', 'pending')]
    })

    render(<TalkerCollection onClose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('Not collecting yet')).toBeTruthy()
    })
    expect(screen.getByText('Recent conversations')).toBeTruthy()
    expect(screen.getByText('Talker a')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Finish review & start collecting' })).toBeTruthy()
  })

  it('shows the pending list once review is complete', async () => {
    getTalkerCollection.mockResolvedValue({
      reviewComplete: true,
      talkers: [talker('a', 'pending')]
    })

    render(<TalkerCollection onClose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('New conversations awaiting a choice')).toBeTruthy()
    })
    expect(screen.getByText('Talker a')).toBeTruthy()
  })

  it('shows the empty state when review is done and nothing is pending', async () => {
    getTalkerCollection.mockResolvedValue({
      reviewComplete: true,
      talkers: [talker('a', 'known')]
    })

    render(<TalkerCollection onClose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('No new conversations')).toBeTruthy()
    })
  })

  it('collects a talker through the api layer', async () => {
    getTalkerCollection.mockResolvedValue({
      reviewComplete: true,
      talkers: [talker('a', 'pending')]
    })

    render(<TalkerCollection onClose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('Talker a')).toBeTruthy()
    })

    screen.getByRole('button', { name: 'Collect' }).click()

    await waitFor(() => {
      expect(setTalkerMode).toHaveBeenCalledWith('a', 'collect')
    })
  })

  it('excludes a talker through the api layer', async () => {
    getTalkerCollection.mockResolvedValue({
      reviewComplete: true,
      talkers: [talker('a', 'pending')]
    })

    render(<TalkerCollection onClose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('Talker a')).toBeTruthy()
    })

    screen.getByRole('button', { name: 'Exclude' }).click()

    await waitFor(() => {
      expect(setTalkerMode).toHaveBeenCalledWith('a', 'exclude')
    })
  })

  it('finishes the review through the api layer', async () => {
    getTalkerCollection.mockResolvedValue({
      reviewComplete: false,
      talkers: [talker('a', 'pending')]
    })

    render(<TalkerCollection onClose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Finish review & start collecting' })).toBeTruthy()
    })

    screen.getByRole('button', { name: 'Finish review & start collecting' }).click()

    await waitFor(() => {
      expect(completeReview).toHaveBeenCalled()
    })
  })
})

describe('talkerKind (R-021 / 裁定 23)', () => {
  it('classifies chatroom ids as groups', () => {
    expect(talkerKind('54302638261@chatroom')).toBe('group')
  })

  it('classifies gh_ ids as official accounts', () => {
    expect(talkerKind('gh_72e00b5828af')).toBe('official')
  })

  it('classifies wxid_/filehelper and everything else as direct chats', () => {
    expect(talkerKind('wxid_c1g832e6jk5322')).toBe('direct')
    expect(talkerKind('filehelper')).toBe('direct')
    expect(talkerKind('')).toBe('direct')
  })
})

describe('TalkerCollection sections + official bulk exclude (R-021)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    $talkerError.set(null)
    $talkerLoading.set(false)
    bulkSetTalkerMode.mockResolvedValue(undefined)
  })

  afterEach(() => {
    cleanup()
  })

  it('shows the three sections, each holding its own kind', async () => {
    $talkerState.set({
      reviewComplete: true,
      talkers: [
        { id: 'wxid_me', name: '嘎嘎', status: 'pending' },
        { id: '54302638261@chatroom', name: '拓扑群', status: 'pending' },
        { id: 'gh_72e00b5828af', name: 'Marvis马维斯', status: 'pending' }
      ]
    })

    getTalkerCollection.mockResolvedValue($talkerState.get())

    render(<TalkerCollection onClose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText('Direct chats')).toBeTruthy()
    })
    expect(screen.getByText('Groups')).toBeTruthy()
    expect(screen.getByText('Official accounts')).toBeTruthy()
    expect(screen.getByText('嘎嘎')).toBeTruthy()
    expect(screen.getByText('拓扑群')).toBeTruthy()
    expect(screen.getByText('Marvis马维斯')).toBeTruthy()
  })

  it('folds a section away on header click without touching the others', async () => {
    $talkerState.set({
      reviewComplete: true,
      talkers: [
        { id: 'wxid_me', name: '嘎嘎', status: 'pending' },
        { id: '54302638261@chatroom', name: '拓扑群', status: 'pending' }
      ]
    })

    getTalkerCollection.mockResolvedValue($talkerState.get())

    render(<TalkerCollection onClose={() => {}} />)

    const header = await screen.findByRole('button', { name: /Direct chats/i })

    expect(header.getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByText('嘎嘎')).toBeTruthy()

    header.click()

    await waitFor(() => {
      expect(screen.queryByText('嘎嘎')).toBeNull()
    })
    // Collapsing direct chats leaves the groups section alone.
    expect(screen.getByText('拓扑群')).toBeTruthy()
  })

  it('excludes only the pending official accounts, never decided ones', async () => {
    $talkerState.set({
      reviewComplete: false,
      talkers: [
        { id: 'gh_pending_a', name: '待定号A', status: 'pending' },
        { id: 'gh_pending_b', name: '待定号B', status: 'pending' },
        { id: 'gh_kept', name: '已采集号', status: 'known' },
        { id: 'gh_dropped', name: '已排除号', status: 'excluded' },
        { id: '54302638261@chatroom', name: '拓扑群', status: 'pending' },
        { id: 'wxid_me', name: '嘎嘎', status: 'pending' }
      ]
    })

    getTalkerCollection.mockResolvedValue($talkerState.get())

    render(<TalkerCollection onClose={() => {}} />)

    const button = await screen.findByRole('button', { name: 'Exclude all pending official accounts' })
    button.click()

    await waitFor(() => {
      expect(bulkSetTalkerMode).toHaveBeenCalledWith(['gh_pending_a', 'gh_pending_b'], 'excluded')
    })
    // Decided accounts and non-official talkers are never touched.
    expect(bulkSetTalkerMode).toHaveBeenCalledTimes(1)
  })
})
