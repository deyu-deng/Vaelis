import { useStore } from '@nanostores/react'
import type { ReactNode } from 'react'

import { $composerAttachments } from '@/store/composer'
import { $activeSessionAwaitingInput } from '@/store/prompts'
import { $messages } from '@/store/session'

import type { ChatBarProps } from './composer/types'
import { ChatContext, type ChatContextValue } from './context'

/**
 * SessionChatContext — the original-chat back-end for {@link ChatContext}.
 *
 * Wires the composer to the full session store. The atoms (`$messages`,
 * `$composerAttachments`) are passed BY REFERENCE so the per-token streaming
 * flush keeps its existing render isolation, exactly as it did when the
 * composer imported them directly. Behavior is byte-for-byte unchanged.
 */
export function SessionChatContext({ children, ...props }: ChatBarProps & { children: ReactNode }) {
  const awaitingInput = useStore($activeSessionAwaitingInput)

  const value: ChatContextValue = {
    awaitingInput,
    attachments: $composerAttachments,
    messages: $messages,
    ...props
  }

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}
