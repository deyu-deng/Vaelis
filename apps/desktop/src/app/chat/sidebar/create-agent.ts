import type { AgentCreateRequest } from '../../console/types'
import { slug } from '@/lib/sanitize'

/**
 * R-012 sidebar taxonomy groups. The order is the order the new-agent
 * dialog renders the category <select> options in.
 */
export const AGENT_CATEGORY_VALUES = ['projects', 'butler', 'events', 'research'] as const

export type AgentCategory = (typeof AGENT_CATEGORY_VALUES)[number]

/** Default category for a human-created agent in the new-agent dialog. */
export const DEFAULT_AGENT_CATEGORY: AgentCategory = 'projects'

/**
 * Registry id / default profile slug from the typed name: lowercase +
 * hyphens. Empty (e.g. CJK-only) gets a dirty timestamped fallback so the
 * POST still has a non-empty id. Preserved from the previous inline
 * `agentIdFromName` in the sidebar.
 */
export function agentIdFromName(name: string): string {
  return slug(name).replace(/-+$/g, '') || `l2-${Date.now()}`
}

/**
 * Build the POST /api/agents body for a human-created L2 agent (裁定 18).
 * `category` is forwarded so the registry can group it under R-012.
 */
export function buildCreateAgentBody(name: string, category: AgentCategory): AgentCreateRequest {
  return {
    id: agentIdFromName(name),
    role: 'l2_project',
    category
  }
}

/**
 * The `events` category cannot be created from this dialog yet — it needs a
 * `source_event_id` from the schedule. The dialog disables submit and shows a
 * hint instead of letting the backend return 400. Centralised so the UI and
 * tests agree on the rule.
 */
export function isCreateAgentCategoryBlocked(category: AgentCategory): boolean {
  return category === 'events'
}
