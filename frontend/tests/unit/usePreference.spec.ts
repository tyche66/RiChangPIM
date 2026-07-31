import { beforeEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import { usePreference } from '@/composables/usePreference'

const PREFIX = 'pim:pref:'
const VIEW_MODES = ['grid', 'list'] as const
type ViewMode = (typeof VIEW_MODES)[number]

// Each case uses its own key on purpose: useStorage keeps window-level listeners
// alive for cross-instance sync, so a key shared with an earlier case can be
// written over by that case's still-live instance.
describe('usePreference', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('returns the fallback when nothing is stored yet', () => {
    const viewMode = usePreference<ViewMode>('spec.default.viewMode', 'grid', VIEW_MODES)
    expect(viewMode.value).toBe('grid')
  })

  it('persists a write and reads it back through a fresh instance', async () => {
    const key = 'spec.roundtrip.viewMode'
    const viewMode = usePreference<ViewMode>(key, 'grid', VIEW_MODES)

    viewMode.value = 'list'
    await nextTick()

    expect(localStorage.getItem(`${PREFIX}${key}`)).toBe('list')
    expect(usePreference<ViewMode>(key, 'grid', VIEW_MODES).value).toBe('list')
  })

  it('falls back to the default when the stored value is outside the whitelist', async () => {
    const key = 'spec.dirty.viewMode'
    localStorage.setItem(`${PREFIX}${key}`, 'definitely-not-a-view-mode')

    const viewMode = usePreference<ViewMode>(key, 'grid', VIEW_MODES)
    expect(viewMode.value).toBe('grid')

    // The dirty value is not just ignored in memory, it gets overwritten.
    await nextTick()
    expect(localStorage.getItem(`${PREFIX}${key}`)).toBe('grid')
  })

  it('prefixes every key with pim:pref:', () => {
    usePreference<ViewMode>('spec.prefix.viewMode', 'grid', VIEW_MODES)

    expect(localStorage.getItem('pim:pref:spec.prefix.viewMode')).toBe('grid')
    expect(localStorage.getItem('spec.prefix.viewMode')).toBeNull()

    const storedKeys = Array.from({ length: localStorage.length }, (_, i) => localStorage.key(i))
    expect(storedKeys.length).toBeGreaterThan(0)
    expect(storedKeys.every((k) => k?.startsWith(PREFIX))).toBe(true)
  })
})
