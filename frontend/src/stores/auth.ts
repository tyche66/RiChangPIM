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

  function extractTokenClaims(token: string): { role_code: string | null; perms: string[] } | null {
    const decoded = decodeJwt(token)
    if (!decoded?.payload) return null
    return {
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
    try {
      const userRes = await authApi.getCurrentUser()
      user.value = userRes.data || userRes.data
    } catch {
      // user info fetch failure is non-fatal after login
    }
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

    try {
      const userRes = await authApi.getCurrentUser()
      user.value = userRes.data
    } catch {
      clearAuth()
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
    login,
    logout,
    refresh,
    init,
    clearAuth,
  }
})
