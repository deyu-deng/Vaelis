import { Codecs, persistentAtom } from '@/lib/persisted'
import { storageKey } from '@/lib/storage'

// Per-view sort direction for the Capabilities lists — persisted so each tab
// remembers most/least-used across navigations and restarts.
export const $skillsSortDesc = persistentAtom(storageKey('desktop.capabilities.skillsSortDesc'), true, Codecs.bool)
export const $toolsetsSortDesc = persistentAtom(storageKey('desktop.capabilities.toolsetsSortDesc'), true, Codecs.bool)
