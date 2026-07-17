import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

// Tracks an in-flight refresh request so concurrent 401s share one refresh call.
let refreshPromise: Promise<boolean> | null = null
// Queue of resolve/reject pairs for requests that arrived during a refresh.
type PendingRequest = {
  resolve: (token: string) => void
  reject: (err: unknown) => void
}
const pendingQueue: PendingRequest[] = []

function processQueue(error: unknown, token?: string) {
  while (pendingQueue.length) {
    const req = pendingQueue.shift()!
    if (error) req.reject(error)
    else req.resolve(token!)
  }
}

// Extend axios request config type to allow skipAuth flag.
declare module 'axios' {
  interface AxiosRequestConfig {
    skipAuth?: boolean
  }
}

api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // Public share endpoints must NOT carry auth headers.
    if (config.skipAuth) {
      delete config.headers.Authorization
      return config
    }
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

api.interceptors.response.use(
  (response) => response.data,
  async (error: AxiosError & { config?: InternalAxiosRequestConfig & { _retry?: boolean } }) => {
    const originalRequest = error.config
    if (!originalRequest) return Promise.reject(error)

    // If the request already retried once, don't loop.
    if (originalRequest._retry) {
      localStorage.removeItem('token')
      localStorage.removeItem('refresh_token')
      window.location.href = '/login'
      return Promise.reject(error)
    }

    if (error.response?.status === 401 && !originalRequest.skipAuth) {
      originalRequest._retry = true

      // Do not redirect to login for auth endpoints themselves (login, refresh).
      const url = originalRequest.url || ''
      if (url.includes('/auth/login') || url.includes('/auth/refresh')) {
        return Promise.reject(error)
      }

      const rt = localStorage.getItem('refresh_token')
      if (!rt) {
        localStorage.removeItem('token')
        window.location.href = '/login'
        return Promise.reject(error)
      }

      if (!refreshPromise) {
        refreshPromise = api.post('/auth/refresh', null, { skipAuth: true, params: { refresh_token: rt } })
          .then((res: any) => {
            const data = res.data
            localStorage.setItem('token', data.access_token)
            localStorage.setItem('refresh_token', data.refresh_token)
            processQueue(null, data.access_token)
            return true
          })
          .catch(() => {
            processQueue(error, undefined)
            localStorage.removeItem('token')
            localStorage.removeItem('refresh_token')
            window.location.href = '/login'
            return false
          })
          .finally(() => {
            refreshPromise = null
          })
      }

      try {
        const newToken = await new Promise<string>((resolve, reject) => {
          pendingQueue.push({ resolve, reject })
        })
        originalRequest.headers.Authorization = `Bearer ${newToken}`
        return api(originalRequest)
      } catch {
        return Promise.reject(error)
      }
    }

    if (error.response?.status === 403) {
      const detail: any = (error.response as any).data
      ElMessage.error(detail?.detail?.msg || '无权限访问该资源')
    }

    // Surface backend error messages for non-401/403 cases.
    if (error.response?.status && error.response.status !== 401) {
      const detail: any = (error.response as any).data
      const msg = detail?.detail?.msg || detail?.msg || '请求失败'
      if (msg) ElMessage.error(msg)
    }

    return Promise.reject(error)
  }
)

export default api

export const authApi = {
  login: (data: { username: string; password: string }) =>
    api.post('/auth/login', data),
  logout: () => api.post('/auth/logout'),
  getCurrentUser: () => api.get('/auth/me'),
  refresh: (refreshToken: string) =>
    api.post('/auth/refresh', null, { skipAuth: true, params: { refresh_token: refreshToken } }),
  changePassword: (oldPassword: string, newPassword: string) =>
    api.post('/auth/change-password', null, { params: { old_password: oldPassword, new_password: newPassword } }),
}

export const productApi = {
  list: (params?: Record<string, unknown>) => api.get('/products', { params }),
  get: (id: string) => api.get(`/products/${id}`),
  create: (data: unknown) => api.post('/products', data),
  update: (id: string, data: unknown) => api.put(`/products/${id}`, data),
  delete: (id: string) => api.delete(`/products/${id}`),
  updateStatus: (id: string, status: string) =>
    api.patch(`/products/${id}/status`, { status }),
  clone: (id: string) => api.post(`/products/${id}/clone`),
  export: (params?: Record<string, unknown>) =>
    api.get('/products/export', { params, responseType: 'blob' }),
  import: (data: unknown, params?: Record<string, unknown>) =>
    api.post('/products/import', data, { params }),
}

export const categoryApi = {
  list: () => api.get('/categories'),
  create: (data: unknown) => api.post('/categories', data),
  update: (id: string, data: unknown) => api.put(`/categories/${id}`, data),
  delete: (id: string) => api.delete(`/categories/${id}`),
}

export const brandApi = {
  list: () => api.get('/brands'),
  create: (data: unknown) => api.post('/brands', data),
  update: (id: string, data: unknown) => api.put(`/brands/${id}`, data),
  delete: (id: string) => api.delete(`/brands/${id}`),
}

export const supplierApi = {
  list: () => api.get('/suppliers'),
  create: (data: unknown) => api.post('/suppliers', data),
  update: (id: string, data: unknown) => api.put(`/suppliers/${id}`, data),
  delete: (id: string) => api.delete(`/suppliers/${id}`),
}

export const tagApi = {
  list: () => api.get('/tags'),
  create: (data: unknown) => api.post('/tags', data),
  update: (id: string, data: unknown) => api.put(`/tags/${id}`, data),
  delete: (id: string) => api.delete(`/tags/${id}`),
}

export const proposalApi = {
  list: (params?: Record<string, unknown>) => api.get('/proposals', { params }),
  get: (id: string) => api.get(`/proposals/${id}`),
  create: (data: unknown) => api.post('/proposals', data),
  update: (id: string, data: unknown) => api.put(`/proposals/${id}`, data),
  delete: (id: string) => api.delete(`/proposals/${id}`),
}

export const quotationApi = {
  list: (params?: Record<string, unknown>) => api.get('/quotations', { params }),
  get: (id: string) => api.get(`/quotations/${id}`),
  create: (data: unknown) => api.post('/quotations', data),
  update: (id: string, data: unknown) => api.put(`/quotations/${id}`, data),
  exportPdf: (id: string) =>
    api.get(`/quotations/${id}/pdf`, { responseType: 'blob' }) as unknown as Promise<Blob>,
}

export const shareApi = {
  create: (data: unknown) => api.post('/shares', data),
  list: () => api.get('/shares'),
  get: (token: string, password?: string) =>
    api.get(`/share/${token}`, { skipAuth: true, params: password ? { password } : {} }),
  revoke: (id: string) => api.delete(`/shares/${id}`),
}

export const userApi = {
  list: (params?: Record<string, unknown>) => api.get('/users', { params }),
  get: (id: string) => api.get(`/users/${id}`),
  create: (data: unknown) => api.post('/users', data),
  update: (id: string, data: unknown) => api.put(`/users/${id}`, data),
  delete: (id: string) => api.delete(`/users/${id}`),
}

export const roleApi = {
  list: () => api.get('/roles'),
  create: (data: unknown) => api.post('/roles', data),
  update: (id: string, data: unknown) => api.put(`/roles/${id}`, data),
  delete: (id: string) => api.delete(`/roles/${id}`),
}

export const fileApi = {
  upload: (data: FormData) =>
    api.post('/files/upload', data, { headers: { 'Content-Type': 'multipart/form-data' } }),
  delete: (id: string) => api.delete(`/files/${id}`),
  download: (id: string) => api.get(`/files/${id}/download`),
  preview: (id: string) => api.get(`/files/${id}/preview`),
}

export const manualApi = {
  create: (data: unknown) => api.post('/manuals', data),
  list: (params?: Record<string, unknown>) => api.get('/manuals', { params }),
  get: (id: string) => api.get(`/manuals/${id}`),
  delete: (id: string) => api.delete(`/manuals/${id}`),
  parse: (id: string) => api.post(`/manuals/${id}/parse`),
  ocr: (id: string) => api.post(`/manuals/${id}/ocr`),
  index: (id: string) => api.post(`/manuals/${id}/index`),
  answer: (data: unknown) => api.post('/manuals/answer', data),
}

export const statsApi = {
  shares: (params?: Record<string, unknown>) => api.get('/stats/shares', { params }),
  hotProducts: (params?: Record<string, unknown>) => api.get('/stats/products/hot', { params }),
}

export const auditApi = {
  operationLogs: (params?: Record<string, unknown>) => api.get('/audit/operation-logs', { params }),
}

export const aiApi = {
  chat: (data: unknown) => api.post('/ai/chat', data),
  ragSearch: (data: unknown) => api.post('/ai/rag/search', data),
  polishProposal: (proposalId: string) => api.post(`/ai/proposal/${proposalId}/polish`),
  recommend: (data: unknown) => api.post('/ai/recommend', data),
}
