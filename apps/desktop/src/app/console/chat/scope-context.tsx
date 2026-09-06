/**
 * ScopeChatContext — the console back-end for {@link ChatContext}.
 *
 * Wires the SAME ChatBar the original chat uses, but its data is the base
 * session layer (per ARCH-RULINGS 2026-09-02 裁定 1): the center reuses the
 * `$messages` / `$busy` / `$activeSessionAwaitingInput` / `$composerAttachments`
 * atoms the full-screen chat uses, and `onSubmit` / `onCancel` are injected by
 * the shell (the real `submitText` / `cancelRun` from the desktop controller),
 * so the console never owns a second session or a mock transport.
 *
 * - `messages` is the global `$messages` atom (passed BY REFERENCE; the base
 *   ChatBar subscribes to it directly, exactly like `SessionChatContext`).
 * - `submit` / `cancel` are supplied by the owner (`ChatSurface` ← controller),
 *   keeping this module free of any send-side mock.
 * - `modelMenuContent` is the live model.options dropdown the status-bar /
 *   composer pill used to host; without it the pill falls back to the full
 *   picker dialog (the L1/L2 regression the QA caught).
 */

import { useStore } from '@nanostores/react'
import { type ReactNode, useMemo } from 'react'

import { $composerAttachments } from '@/store/composer'
import { $activeSessionAwaitingInput } from '@/store/prompts'
import { $busy, $currentModel, $currentProvider, $gatewayState, $messages } from '@/store/session'

import type { ChatBarState } from '../../chat/composer/types'
import { ChatContext, type ChatContextValue } from '../../chat/context'

export type SubmitFn = ChatContextValue['onSubmit']
export type CancelFn = ChatContextValue['onCancel']

export function ScopeChatContext({
  children,
  submit,
  cancel,
  modelMenuContent
}: {
  children: ReactNode
  submit?: SubmitFn
  cancel?: CancelFn
  modelMenuContent?: ReactNode
}) {
  const awaitingInput = useStore($activeSessionAwaitingInput)
  const busy = useStore($busy)
  const currentModel = useStore($currentModel)
  const currentProvider = useStore($currentProvider)
  const gatewayState = useStore($gatewayState)

  const gatewayOpen = gatewayState === 'open'

  const state: ChatBarState = useMemo(
    () => ({
      model: {
        model: currentModel,
        provider: currentProvider,
        canSwitch: gatewayOpen,
        loading: !gatewayOpen || (!currentModel && !currentProvider),
        modelMenuContent
      },
      tools: { enabled: true, label: 'Add context' },
      voice: { enabled: true, active: false }
    }),
    [currentModel, currentProvider, gatewayOpen, modelMenuContent]
  )

  const value: ChatContextValue = useMemo(
    () => ({
      messages: $messages,
      awaitingInput,
      attachments: $composerAttachments,
      busy,
      disabled: !gatewayOpen,
      state,
      onSubmit: async (text, options) => {
        if (!submit) {
          return false
        }

        return await submit(text, options)
      },
      onCancel: () => {
        void cancel?.()
      },
      onRemoveAttachment: (id: string) => {
        $composerAttachments.set($composerAttachments.get().filter(attachment => attachment.id !== id))
      }
    }),
    [awaitingInput, busy, gatewayOpen, state, submit, cancel]
  )

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}
