import type { Agent } from '@/app/console/types'

/**
 * R-012 sidebar agent taxonomy. The backend registry owns the `category`
 * field; the client only normalizes and renders it. Unknown / missing values
 * fold into `butler` (日程秘书就是管家 — legacy agents are butler-shaped).
 */
export type AgentCategory = 'butler' | 'events' | 'projects' | 'research'

/** Fixed display order: PROJECTS / BUTLER / EVENTS / RESEARCH. */
export const AGENT_CATEGORY_ORDER: readonly AgentCategory[] = ['projects', 'butler', 'events', 'research']

const AGENT_CATEGORY_SET: ReadonlySet<string> = new Set(AGENT_CATEGORY_ORDER)

export function normalizeAgentCategory(raw?: null | string): AgentCategory {
  const key = (raw ?? '').trim().toLowerCase()

  return AGENT_CATEGORY_SET.has(key) ? (key as AgentCategory) : 'butler'
}

export interface AgentCategoryGroup<T> {
  agents: T[]
  category: AgentCategory
}

/**
 * Bucket agents by category. Groups come back in {@link AGENT_CATEGORY_ORDER}
 * (only non-empty ones), each agent list sorted by display name.
 */
export function groupAgentsByCategory<T extends Pick<Agent, 'category' | 'name'>>(
  agents: readonly T[]
): Array<AgentCategoryGroup<T>> {
  const buckets = new Map<AgentCategory, T[]>()

  for (const agent of agents) {
    const category = normalizeAgentCategory(agent.category)
    const bucket = buckets.get(category)

    if (bucket) {
      bucket.push(agent)
    } else {
      buckets.set(category, [agent])
    }
  }

  return AGENT_CATEGORY_ORDER.filter(category => buckets.has(category)).map(category => ({
    agents: (buckets.get(category) ?? []).slice().sort((a, b) => a.name.localeCompare(b.name, 'zh')),
    category
  }))
}

/** Profiles an agent chats under (used to nest agent-owned sessions). */
export function agentProfileIdSet(agents: readonly Agent[]): Set<string> {
  const out = new Set<string>()

  for (const agent of agents) {
    const profile = (agent.profile ?? '').trim()

    if (profile) {
      out.add(profile)
    }
  }

  return out
}

/** L1 identity profiles — never treated as agent-owned (they are the user's own main thread). */
export const L1_SESSION_PROFILES: ReadonlySet<string> = new Set(['default', 'master'])

export function isL1SessionProfile(profile?: null | string): boolean {
  return L1_SESSION_PROFILES.has((profile ?? 'default').trim().toLowerCase() || 'default')
}
