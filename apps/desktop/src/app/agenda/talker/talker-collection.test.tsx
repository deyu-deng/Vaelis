import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { $talkerError, $talkerLoading, $talkerState } from './store'
import { TalkerCollection } from './talker-collection'

const getTalkerCollection = vi.hoisted(() => vi.fn())
const setTalkerMode = vi.hoisted(() => vi.fn())
const completeReview = vi.hoisted(() => vi.fn())

vi.mock('./api', () => ({
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
