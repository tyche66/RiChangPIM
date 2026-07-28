import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { login, refreshToken } from '@/api'

function decodeJwt(token: string): Record<string, unknown> | null {
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    return JSON.parse(atob(payload)) as Record<string, unknown>
  } catch {
    return null
  }
}

function isTokenExpiring(token: string, skewSeconds = 30): boolean {
  const expiresAt = decodeJwt(token)?.exp
  if (typeof expiresAt !== 'number') return false
  return expiresAt <= Math.floor(Date.now() / 1000) + skewSeconds
}

export const useAuthStore = defineStore('portal-auth', () => {
  const accessToken = ref<string | null>(localStorage.getItem('token'))
  const refreshTokenValue = ref<string | null>(localStorage.getItem('refresh_token'))
  const initialized = ref(false)
  const claims = ref<Record<string, unknown> | null>(
    accessToken.value ? decodeJwt(accessToken.value) : null,
  )

  const isAuthenticated = computed(() => !!accessToken.value)
  const permissions = computed(() => (claims.value?.perms as string[] | undefined) || [])
  const roleCode = computed(() => (claims.value?.role_code as string | undefined) || null)

  function persist(access: string, refresh: string) {
    accessToken.value = access
    refreshTokenValue.value = refresh
    claims.value = decodeJwt(access)
    localStorage.setItem('token', access)
    localStorage.setItem('refresh_token', refresh)
  }

  function clear() {
    accessToken.value = null
    refreshTokenValue.value = null
    claims.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('refresh_token')
  }

  async function init() {
    if (initialized.value) return
    initialized.value = true
    if (!accessToken.value) return
    if (isTokenExpiring(accessToken.value)) {
      if (!refreshTokenValue.value) {
        clear()
        return
      }
      try {
        const payload = await refreshToken(refreshTokenValue.value)
        persist(payload.data.access_token, payload.data.refresh_token)
      } catch {
        clear()
        return
      }
    }
    claims.value = decodeJwt(accessToken.value)
  }

  async function signIn(username: string, password: string) {
    const payload = await login(username, password)
    persist(payload.data.access_token, payload.data.refresh_token)
  }

  async function ensureToken(): Promise<string | null> {
    if (accessToken.value && !isTokenExpiring(accessToken.value)) return accessToken.value
    if (!refreshTokenValue.value) {
      clear()
      return null
    }
    try {
      const payload = await refreshToken(refreshTokenValue.value)
      persist(payload.data.access_token, payload.data.refresh_token)
      return accessToken.value
    } catch {
      clear()
      return null
    }
  }

  return {
    accessToken,
    refreshTokenValue,
    initialized,
    isAuthenticated,
    permissions,
    roleCode,
    init,
    signIn,
    ensureToken,
    clear,
  }
})
