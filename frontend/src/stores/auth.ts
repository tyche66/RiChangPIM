import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api'
import { decodeJwt, isTokenExpired } from '@/utils/jwt'
import type { UserResponse } from '@/types/auth'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(localStorage.getItem('token'))
  const refreshToken = ref<string | null>(localStorage.getItem('refresh_token'))
  const user = ref<UserResponse | null>(null)
  const permissions = ref<string[]>([])
  const roleCode = ref<string | null>(null)

  const isAuthenticated = computed(() => !!accessToken.value)
  const currentUser = computed(() => user.value)
  const userPermissions = computed(() => permissions.value)
  const userRoleCode = computed(() => roleCode.value)
  // userId falls back to the JWT 'sub' claim so views that need a creator/owner
  // id never see undefined when the access token is still valid, even if the
  // /auth/me profile fetch has not (yet) completed.
  const userId = computed<string | null>(() => {
    if (user.value?.id) return user.value.id
    const token = accessToken.value
    if (!token) return null
    const claims = extractTokenClaims(token)
    return (claims?.sub as string | undefined) ?? null
  })

  function extractTokenClaims(token: string): { sub?: string; role_code: string | null; perms: string[] } | null {
    const decoded = decodeJwt(token)
    if (!decoded?.payload) return null
    return {
      sub: (decoded.payload.sub as string) || undefined,
      role_code: (decoded.payload.role_code as string) || null,
      perms: (decoded.payload.perms as string[]) || [],
    }
  }

  function persistTokens(access: string, refresh: string) {
    accessToken.value = access
    refreshToken.value = refresh
    localStorage.setItem('token', access)
    localStorage.setItem('refresh_token', refresh)
    const claims = extractTokenClaims(access)
    if (claims) {
      roleCode.value = claims.role_code
      permissions.value = claims.perms
    }
  }

  function clearAuth() {
    accessToken.value = null
    refreshToken.value = null
    user.value = null
    permissions.value = []
    roleCode.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('refresh_token')
  }

  async function login(username: string, password: string) {
    const res = await authApi.login({ username, password })
    const data = res.data
    persistTokens(data.access_token, data.refresh_token)
    await ensureUser()
  }

  async function logout() {
    try {
      await authApi.logout()
    } catch {
      // ignore logout errors
    }
    clearAuth()
  }

  async function refresh(): Promise<boolean> {
    const rt = refreshToken.value
    if (!rt) return false
    try {
      const res = await authApi.refresh(rt)
      const data = res.data
      persistTokens(data.access_token, data.refresh_token)
      return true
    } catch {
      clearAuth()
      return false
    }
  }

  async function ensureUser(): Promise<UserResponse | null> {
    if (user.value?.id) return user.value
    const token = accessToken.value
    if (!token) return null
    // Avoid the round-trip if the token is already known to be expired; in
    // that case the caller should refresh first, but we still return what we
    // have so the UI can react gracefully.
    if (isTokenExpired(token)) {
      const rt = refreshToken.value
      if (rt) {
        const ok = await refresh()
        if (!ok) return null
      } else {
        return null
      }
    }
    try {
      const userRes = await authApi.getCurrentUser()
      const profile = (userRes as any)?.data
      if (profile && profile.id) {
        user.value = profile
      }
      return user.value
    } catch {
      // Profile fetch failure is non-fatal: the token is still valid, so we
      // keep permissions/role from the JWT and let the caller fall back to
      // the 'sub' claim via the userId computed.
      return null
    }
  }

  async function init() {
    const token = localStorage.getItem('token')
    const rt = localStorage.getItem('refresh_token')
    if (!token) return

    if (isTokenExpired(token)) {
      if (rt) {
        const ok = await refresh()
        if (!ok) return
      } else {
        clearAuth()
        return
      }
    }

    const claims = extractTokenClaims(token)
    if (claims) {
      roleCode.value = claims.role_code
      permissions.value = claims.perms
    }

    // Best-effort profile hydration. Failures must NOT clear auth state: the
    // token is valid and the role/permissions above are still authoritative.
    // Without this guard, any transient /auth/me 5xx would force a re-login
    // and surface as "用户信息尚未加载" on the very next user action.
    try {
      const userRes = await authApi.getCurrentUser()
      const profile = (userRes as any)?.data
      if (profile && profile.id) {
        user.value = profile
      }
    } catch {
      // ignore — user will be lazy-loaded via ensureUser() on demand
    }
  }

  // Restore permissions from token on page load (testability fix for E2E).
  const initialClaims = extractTokenClaims(accessToken.value || '')
  if (initialClaims) {
    roleCode.value = initialClaims.role_code
    permissions.value = initialClaims.perms
  }

  return {
    accessToken,
    refreshToken,
    user,
    permissions,
    roleCode,
    isAuthenticated,
    currentUser,
    userPermissions,
    userRoleCode,
    userId,
    login,
    logout,
    refresh,
    init,
    ensureUser,
    clearAuth,
  }
})
