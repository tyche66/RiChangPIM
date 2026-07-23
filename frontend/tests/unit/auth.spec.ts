import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { ElForm, ElFormItem, ElInput, ElButton, ElCard } from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('@/api', () => ({
  authApi: {
    login: vi.fn(),
    logout: vi.fn(),
    getCurrentUser: vi.fn(),
    refresh: vi.fn(),
  },
}))

import { authApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import Login from '@/views/Login.vue'
import { decodeJwt, isTokenExpired } from '@/utils/jwt'

// Helper to build a fake JWT with given payload.
function makeToken(payload: Record<string, unknown>): string {
  const b64 = (obj: unknown) =>
    btoa(JSON.stringify(obj)).replace(/=+$/, '')
  return `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64(payload)}.signature`
}

describe('JWT utility', () => {
  it('decodes a valid JWT payload', () => {
    const payload = { sub: 'u1', role_code: 'admin', perms: ['product:view', 'product:edit'] }
    const token = makeToken(payload)
    const decoded = decodeJwt(token)
    expect(decoded).not.toBeNull()
    expect(decoded!.payload.sub).toBe('u1')
    expect(decoded!.payload.role_code).toBe('admin')
    expect(decoded!.payload.perms).toEqual(['product:view', 'product:edit'])
  })

  it('returns null for malformed tokens', () => {
    expect(decodeJwt('not-a-jwt')).toBeNull()
    expect(decodeJwt('')).toBeNull()
    expect(decodeJwt('a.b')).toBeNull()
  })

  it('detects expired tokens', () => {
    const expired = makeToken({ exp: Math.floor(Date.now() / 1000) - 60 })
    const valid = makeToken({ exp: Math.floor(Date.now() / 1000) + 3600 })
    const noExp = makeToken({ sub: 'u1' })
    expect(isTokenExpired(expired)).toBe(true)
    expect(isTokenExpired(valid)).toBe(false)
    expect(isTokenExpired(noExp)).toBe(false)
  })
})

describe('Login.vue + auth flow', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  const mountLogin = async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/products', component: { template: '<div />' } },
      ],
    })
    router.push('/')
    await router.isReady()

    return mount(Login, {
      global: {
        plugins: [createPinia(), router],
        stubs: {
          ElForm,
          ElFormItem,
          ElInput,
          ElButton,
          ElCard,
        },
      },
    })
  }

  it('persists access_token and refresh_token on success', async () => {
    const token = makeToken({ sub: 'u1', role_code: 'admin', perms: ['product:view'] })
    ;(authApi.login as any).mockResolvedValue({
      data: { access_token: token, refresh_token: 'RT', token_type: 'bearer', expires_in: 7200 },
    })
    ;(authApi.getCurrentUser as any).mockResolvedValue({ data: { id: 'u1', username: 'admin' } })
    const wrapper = await mountLogin()
    await wrapper.findComponent(ElInput).setValue('admin')
    await wrapper.findAllComponents(ElInput)[1].setValue('admin')
    await wrapper.findComponent(ElButton).trigger('click')
    await new Promise((r) => setTimeout(r, 50))
    expect(localStorage.getItem('token')).toBe(token)
    expect(localStorage.getItem('refresh_token')).toBe('RT')
  })

  it('shows error when backend returns 401', async () => {
    const loginMock = authApi.login as any
    loginMock.mockRejectedValue({
      response: { data: { detail: { msg: '用户名或密码错误', code: 40101 } } },
    })
    const wrapper = await mountLogin()
    await wrapper.findComponent(ElInput).setValue('admin')
    await wrapper.findAllComponents(ElInput)[1].setValue('bad')
    await wrapper.findComponent(ElButton).trigger('click')
    await new Promise((r) => setTimeout(r, 50))
    expect(localStorage.getItem('token')).toBeNull()
  })

  it('extracts permissions and role_code from JWT on login', async () => {
    const perms = ['product:view', 'product:create', 'category:view']
    const token = makeToken({ sub: 'u1', role_code: 'purchaser', perms })
    ;(authApi.login as any).mockResolvedValue({
      data: { access_token: token, refresh_token: 'RT', token_type: 'bearer', expires_in: 7200 },
    })
    ;(authApi.getCurrentUser as any).mockResolvedValue({ data: { id: 'u1', username: 'buyer' } })
    const store = useAuthStore()
    await store.login('buyer', 'pass')
    expect(store.roleCode).toBe('purchaser')
    expect(store.permissions).toEqual(perms)
    expect(store.isAuthenticated).toBe(true)
  })
})

describe('AuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('clears all auth state on logout', async () => {
    const token = makeToken({ sub: 'u1', role_code: 'admin', perms: ['product:view'] })
    localStorage.setItem('token', token)
    localStorage.setItem('refresh_token', 'RT')
    ;(authApi.logout as any).mockResolvedValue({ data: { code: 200, msg: 'success' } })
    const store = useAuthStore()
    await store.login('admin', 'pass')
    expect(store.isAuthenticated).toBe(true)
    await store.logout()
    expect(store.isAuthenticated).toBe(false)
    expect(store.permissions).toEqual([])
    expect(store.roleCode).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('refresh_token')).toBeNull()
  })

  it('refresh updates tokens and re-extracts claims', async () => {
    const oldToken = makeToken({ sub: 'u1', role_code: 'viewer', perms: ['product:view'] })
    const newToken = makeToken({ sub: 'u1', role_code: 'admin', perms: ['*'] })
    localStorage.setItem('token', oldToken)
    localStorage.setItem('refresh_token', 'RT')
    ;(authApi.refresh as any).mockResolvedValue({
      data: { access_token: newToken, refresh_token: 'newRT', token_type: 'bearer', expires_in: 7200 },
    })
    const store = useAuthStore()
    const ok = await store.refresh()
    expect(ok).toBe(true)
    expect(localStorage.getItem('token')).toBe(newToken)
    expect(store.roleCode).toBe('admin')
  })

  it('init does nothing when no token is stored', async () => {
    const store = useAuthStore()
    await store.init()
    expect(store.isAuthenticated).toBe(false)
  })

  it('init keeps permissions/role when /auth/me fails (token still valid)', async () => {
    const token = makeToken({
      sub: 'u1',
      role_code: 'purchaser',
      perms: ['product:view', 'proposal:create'],
      exp: Math.floor(Date.now() / 1000) + 3600,
    })
    localStorage.setItem('token', token)
    localStorage.setItem('refresh_token', 'RT')
    ;(authApi.getCurrentUser as any).mockRejectedValue({
      response: { status: 500, data: { detail: { msg: 'boom' } } },
    })
    const store = useAuthStore()
    await store.init()
    // Token + permissions are still authoritative even when /auth/me is down.
    expect(store.isAuthenticated).toBe(true)
    expect(store.roleCode).toBe('purchaser')
    expect(store.permissions).toEqual(['product:view', 'proposal:create'])
    // userId falls back to the JWT 'sub' so dependent actions still work.
    expect(store.userId).toBe('u1')
  })

  it('ensureUser() hydrates the profile and caches it', async () => {
    const token = makeToken({
      sub: 'u7',
      role_code: 'admin',
      perms: ['*'],
      exp: Math.floor(Date.now() / 1000) + 3600,
    })
    localStorage.setItem('token', token)
    localStorage.setItem('refresh_token', 'RT')
    ;(authApi.getCurrentUser as any).mockResolvedValue({
      data: { id: 'u7', username: 'alice' },
    })
    const store = useAuthStore()
    const profile = await store.ensureUser()
    expect(profile?.id).toBe('u7')
    expect(store.userId).toBe('u7')
    // second call is a cache hit, no extra API call
    await store.ensureUser()
    expect((authApi.getCurrentUser as any).mock.calls.length).toBe(1)
  })

  it('ensureUser() returns null but preserves userId from JWT when /auth/me fails', async () => {
    const token = makeToken({
      sub: 'u9',
      role_code: 'admin',
      perms: ['*'],
      exp: Math.floor(Date.now() / 1000) + 3600,
    })
    localStorage.setItem('token', token)
    localStorage.setItem('refresh_token', 'RT')
    ;(authApi.getCurrentUser as any).mockRejectedValue(new Error('network down'))
    const store = useAuthStore()
    const profile = await store.ensureUser()
    expect(profile).toBeNull()
    expect(store.userId).toBe('u9')
    expect(store.isAuthenticated).toBe(true)
  })
})
