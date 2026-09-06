import type { SessionInfo } from '@/hermes'
import { persistString, storedString } from '@/lib/storage'
import { normalizeProfileKey } from '@/store/profile'

// Cheap signature compare so a poll only swaps the atom (and re-renders the
// sidebar) when the visible rows actually changed.
export function sameCronSignature(a: SessionInfo[], b: SessionInfo[]): boolean {
  if (a.length !== b.length) {
    return false
  }

  return a.every((session, i) => {
    const other = b[i]

    return (
      other != null &&
      session.id === other.id &&
      session._lineage_root_id === other._lineage_root_id &&
      session.title === other.title &&
      session.source === other.source &&
      session.profile === other.profile &&
      session.preview === other.preview &&
      session.message_count === other.message_count &&
      session.last_active === other.last_active &&
      session.ended_at === other.ended_at
    )
  })
}

/** True only when a Hermes profile named `master` is actually installed. */
export function profileListHasMaster(profiles: Array<{ name: string }>): boolean {
  return profiles.some(profile => normalizeProfileKey(profile.name) === 'master')
}

/**
 * L1 may point the live gateway at `master` only when that profile exists
 * (ARCH-RULINGS 2026-09-04 裁定 6). Missing `master` must leave the current
 * profile and socket alone — never `ensureGatewayProfile('master')`.
 */
export async function bindL1GatewayIfMasterExists(options: {
  ensureGatewayProfile: (profile: string) => Promise<void>
  profiles: Array<{ name: string }>
}): Promise<'bound-master' | 'stayed'> {
  if (!profileListHasMaster(options.profiles)) {
    return 'stayed'
  }

  await options.ensureGatewayProfile('master')

  return 'bound-master'
}

/** Match an L2 overview session id against the desktop's known session list (N3). */
export function findKnownOverviewSession<T extends { id: string; _lineage_root_id?: null | string }>(
  sessions: T[],
  sessionId: string
): T | undefined {
  const id = sessionId.trim()

  if (!id) {
    return undefined
  }

  return sessions.find(session => session.id === id || session._lineage_root_id === id)
}

/**
 * Latest non-lineage session for a Hermes profile (L1 bind after 裁定 6).
 * Prefers tip sessions (`!_lineage_root_id`); falls back to any row on that profile.
 */
export function findLatestSessionForProfile<
  T extends { id: string; profile?: null | string; _lineage_root_id?: null | string; started_at?: null | number }
>(sessions: T[], profile: string): T | undefined {
  const key = normalizeProfileKey(profile)
  const onProfile = sessions.filter(session => normalizeProfileKey(session.profile ?? 'default') === key)

  if (onProfile.length === 0) {
    return undefined
  }

  const tips = onProfile.filter(session => !session._lineage_root_id)
  const pool = tips.length > 0 ? tips : onProfile

  return [...pool].sort((a, b) => (b.started_at || 0) - (a.started_at || 0))[0]
}

export function l1MainSessionKey(profile: string): string {
  return `vaelis.desktop.l1MainSession.${normalizeProfileKey(profile)}`
}

export function readL1MainSessionId(profile: string): null | string {
  return storedString(l1MainSessionKey(profile))
}

export function writeL1MainSessionId(profile: string, id: null | string): void {
  persistString(l1MainSessionKey(profile), id)
}

/** Known L2 short labels (裁定 13). Never use description / model as identity. */
const L2_SHORT_NAMES: Record<string, string> = {
  agenda: '日程秘书',
  'agenda-secretary': '日程秘书',
  'secretary-agenda': '日程秘书'
}

export function secretaryShortName(agentId: string, fallbackName?: string): string {
  const key = agentId.trim().toLowerCase()

  if (key && L2_SHORT_NAMES[key]) {
    return L2_SHORT_NAMES[key]
  }

  const named = (fallbackName || '').trim()

  if (named) {
    return named
  }

  return agentId.trim()
}

/**
 * Shell identity copy (裁定 16): L1 = 总秘书, L2 = short name.
 * Derived only from ShellLevel (+ optional agent list). Model / profile / session
 * title must not change this string.
 */
export function secretaryShellLabel(
  level: 'l1' | { l2: string } | null | undefined,
  chiefSecretary: string,
  agents?: ReadonlyArray<{ id: string; name?: string }>
): string {
  if (level && typeof level === 'object') {
    const agent = agents?.find(row => row.id === level.l2)

    return secretaryShortName(level.l2, agent?.name) || chiefSecretary
  }

  return chiefSecretary
}

/** Prefer the remembered L1 mainline; otherwise the latest tip on that profile. */
export function pickL1MainSession<
  T extends { id: string; profile?: null | string; _lineage_root_id?: null | string; started_at?: null | number }
>(sessions: T[], profile: string, rememberedId?: null | string): T | undefined {
  const key = normalizeProfileKey(profile)
  const remembered = (rememberedId || '').trim()

  if (remembered) {
    const hit = sessions.find(
      session => session.id === remembered && normalizeProfileKey(session.profile ?? 'default') === key
    )

    if (hit) {
      return hit
    }
  }

  return findLatestSessionForProfile(sessions, profile)
}
