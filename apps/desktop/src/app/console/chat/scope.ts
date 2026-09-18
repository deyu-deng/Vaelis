/**
 * ChatSurface scope — the ONLY thing that differs between the two places the
 * console shell renders a conversation (spec §3.6: one Shell, one ChatSurface).
 *
 * - S1 center, the L1 secretary  → `{ kind: 'l1' }`
 * - S2 center, an L2 workbench   → `{ kind: 'agent', id }`
 *
 * One scope value plays two roles, so they can never drift apart:
 * - store key   via `chatScopeKey` (conversations never cross-contaminate)
 * - copy        via `scope.kind`   (i18n block, nothing else branches on it)
 *
 * A future `POST /api/chat` endpoint would add a third role as a wire-format
 * `target` field — reintroduce `ChatTarget` / `chatTarget` at that point.
 */

export interface AgentChatScope {
  kind: 'agent'
  id: string
}

export interface L1ChatScope {
  kind: 'l1'
}

export type ChatScope = AgentChatScope | L1ChatScope

export const L1_SCOPE: L1ChatScope = { kind: 'l1' }

/**
 * Build an agent scope. Callers memoize on the agent id so the object identity
 * is stable across renders (the surface keys its effects off the scope).
 */
export function agentScope(id: string): AgentChatScope {
  return { id, kind: 'agent' }
}

export function chatScopeKey(scope: ChatScope): string {
  return scope.kind === 'l1' ? 'l1' : `agent:${scope.id}`
}
