import { readdir, readFile } from 'node:fs/promises'
import { join } from 'node:path'

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/components/assistant-ui/thread', () => ({ Thread: () => <div data-testid="thread" /> }))

import { ChatSurface } from './chat-surface'
import { agentScope, L1_SCOPE } from './scope'
import { setGatewayState } from '@/store/session'

// The full ChatBar's ComposerStatusStack calls useNavigate(), so the surface
// must render inside a Router.
const renderSurface = (node: ReactNode) => render(<MemoryRouter>{node}</MemoryRouter>)

async function collectTsx(dir: string): Promise<string[]> {
  const entries = await readdir(dir, { withFileTypes: true })

  const files = await Promise.all(
    entries.map(async entry => {
      const full = join(dir, entry.name)

      if (entry.isDirectory()) {
        return collectTsx(full)
      }

      // Implementation sources only — test files are excluded so the guard
      // cannot count itself.
      return entry.name.endsWith('.tsx') && !entry.name.endsWith('.test.tsx') ? [full] : []
    })
  )

  return files.flat()
}

describe('ChatSurface (spec §3.6: one conversation component)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setGatewayState('open')
  })

  afterEach(() => {
    cleanup()
    setGatewayState('idle')
  })

  it('renders one transcript + composer for the L1 scope', () => {
    renderSurface(<ChatSurface scope={L1_SCOPE} />)

    expect(screen.getByTestId('thread')).toBeTruthy()
    expect(screen.getByRole('textbox', { name: 'Message' })).toBeTruthy()
  })

  it('renders the SAME surface for an L2 scope, only the copy differs', () => {
    renderSurface(<ChatSurface scope={agentScope('x')} />)

    expect(screen.getByTestId('thread')).toBeTruthy()
    expect(screen.getByRole('textbox', { name: 'Message' })).toBeTruthy()
  })

  it('forwards a real submit through the injected submit prop (L1)', async () => {
    const submit = vi.fn().mockResolvedValue(true)

    renderSurface(<ChatSurface scope={L1_SCOPE} submit={submit} />)

    const editor = screen.getByRole('textbox', { name: 'Message' })
    editor.textContent = 'hi'
    fireEvent.keyDown(editor, { key: 'Enter' })

    await waitFor(() => expect(submit).toHaveBeenCalled())
    expect(submit.mock.calls[0][0]).toBe('hi')
  })

  it('does not remount the transcript when scope or model menu changes', () => {
    const { rerender } = render(
      <MemoryRouter>
        <ChatSurface modelMenuContent={<span>m1</span>} scope={L1_SCOPE} />
      </MemoryRouter>
    )
    const thread = screen.getByTestId('thread')

    rerender(
      <MemoryRouter>
        <ChatSurface modelMenuContent={<span>m2</span>} scope={agentScope('agenda')} />
      </MemoryRouter>
    )

    expect(screen.getByTestId('thread')).toBe(thread)
    expect(screen.getByTestId('thread').closest('[data-chat-scope]')?.getAttribute('data-chat-scope')).toBe(
      'agent:agenda'
    )
  })

  it('exposes an accessible Send control once the L2 composer has text', async () => {
    renderSurface(<ChatSurface scope={agentScope('simulation')} />)

    const editor = screen.getByRole('textbox', { name: 'Message' })
    editor.textContent = 'hello'
    fireEvent.input(editor)

    await waitFor(() => expect(screen.getByRole('button', { name: 'Send' })).toBeTruthy())
  })

  it('forwards a real submit through the injected submit prop (L2 workbench)', async () => {
    const submit = vi.fn().mockResolvedValue(true)

    renderSurface(<ChatSurface scope={agentScope('x')} submit={submit} />)

    const editor = screen.getByRole('textbox', { name: 'Message' })
    editor.textContent = 'hi'
    fireEvent.keyDown(editor, { key: 'Enter' })

    await waitFor(() => expect(submit).toHaveBeenCalled())
    expect(submit.mock.calls[0][0]).toBe('hi')
  })
})

// Acceptance item added by spec §3.6: grep the console domain and assert there
// is exactly ONE chat rendering implementation. Both centers must be
// instantiations of `ChatSurface`; no other console file may own a runtime,
// transcript, or composer.
describe('spec §3.6 single-implementation guard', () => {
  // vitest jsdom reports `import.meta.url` as http, so anchor on cwd
  // (the desktop app root) instead of the module URL.
  const consoleDir = join(process.cwd(), 'src', 'app', 'console')

  it('has exactly one console module owning the chat runtime', async () => {
    const files = await collectTsx(consoleDir)
    const owners = []

    for (const file of files) {
      const source = await readFile(file, 'utf8')

      if (source.split('\n').some(line => line.includes('useIncrementalExternalStoreRuntime') && line.includes('import'))) {
        owners.push(file)
      }
    }

    expect(owners).toHaveLength(1)
    expect(owners[0]?.endsWith('chat-surface.tsx')).toBe(true)
  })
})
