/**
 * Talker kind classifier (R-021 / 裁定 23).
 *
 * Lives in its own module (not `talker-collection.tsx`) so the component file
 * only exports components — mixing a helper export into a component module
 * breaks Vite's Fast Refresh (the dev server falls back to a full reload).
 *
 * chatlog's session payload carries no type field, so we classify from the
 * talker id convention: `…@chatroom` = group, `gh_…` = official account,
 * everything else (wxid_, filehelper, …) = direct chat.
 */

export type TalkerKind = 'direct' | 'group' | 'official'

export function talkerKind(id: string): TalkerKind {
  const value = (id ?? '').trim()

  if (value.endsWith('@chatroom')) {
    return 'group'
  }

  if (value.startsWith('gh_')) {
    return 'official'
  }

  return 'direct'
}

/** Render order of the three sections. */
export const KIND_ORDER: readonly TalkerKind[] = ['direct', 'group', 'official']
