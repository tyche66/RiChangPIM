import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { ElButton } from 'element-plus'
import { setActivePinia, createPinia } from 'pinia'

import AISelect from '@/views/AISelect.vue'
import { useAuthStore } from '@/stores/auth'

const PORTAL_ORIGIN = 'http://portal.test'

let wrapper: VueWrapper | null = null

const factory = () => {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.accessToken = 'access-token-1'
  auth.refreshToken = 'refresh-token-1'

  wrapper = mount(AISelect, {
    attachTo: document.body,
    global: {
      plugins: [pinia],
      stubs: { ElButton },
    },
  })
  return wrapper
}

describe('AISelect.vue（嵌入 AI 前台 /chat）', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_PORTAL_ORIGIN', PORTAL_ORIGIN)
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.unstubAllEnvs()
    document.body.innerHTML = ''
  })

  it('renders an iframe pointing at the portal /chat in embed mode', () => {
    const iframe = factory().find('iframe')
    expect(iframe.exists()).toBe(true)
    expect(iframe.attributes('src')).toBe(`${PORTAL_ORIGIN}/chat?embed=1`)
  })

  it('hands the session to the iframe when it announces it is ready', async () => {
    const view = factory()
    const frame = view.find('iframe').element as HTMLIFrameElement
    const post = vi.fn()
    Object.defineProperty(frame, 'contentWindow', { value: { postMessage: post }, configurable: true })

    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'pim-embed-ready' },
        origin: PORTAL_ORIGIN,
        source: frame.contentWindow,
      }),
    )

    expect(post).toHaveBeenCalledTimes(1)
    expect(post).toHaveBeenCalledWith(
      { type: 'pim-embed-session', token: 'access-token-1', refreshToken: 'refresh-token-1' },
      PORTAL_ORIGIN,
    )
  })

  it('never posts the session to a wildcard target origin', async () => {
    const view = factory()
    const frame = view.find('iframe').element as HTMLIFrameElement
    const post = vi.fn()
    Object.defineProperty(frame, 'contentWindow', { value: { postMessage: post }, configurable: true })

    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'pim-embed-ready' },
        origin: PORTAL_ORIGIN,
        source: frame.contentWindow,
      }),
    )

    expect(post.mock.calls[0][1]).not.toBe('*')
  })

  it('ignores ready messages from a foreign origin', () => {
    const view = factory()
    const frame = view.find('iframe').element as HTMLIFrameElement
    const post = vi.fn()
    Object.defineProperty(frame, 'contentWindow', { value: { postMessage: post }, configurable: true })

    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'pim-embed-ready' },
        origin: 'http://evil.example',
        source: frame.contentWindow,
      }),
    )

    expect(post).not.toHaveBeenCalled()
  })

  it('ignores messages that do not come from the embedded frame', () => {
    const view = factory()
    const frame = view.find('iframe').element as HTMLIFrameElement
    const post = vi.fn()
    Object.defineProperty(frame, 'contentWindow', { value: { postMessage: post }, configurable: true })

    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'pim-embed-ready' },
        origin: PORTAL_ORIGIN,
        source: window,
      }),
    )

    expect(post).not.toHaveBeenCalled()
  })

  it('busts the iframe cache when the user reloads the workspace', async () => {
    const view = factory()
    const before = view.find('iframe').attributes('src')
    await view.findAllComponents(ElButton)[0].trigger('click')
    const after = view.find('iframe').attributes('src')
    expect(after).not.toBe(before)
    expect(after).toContain('embed=1')
  })
})
