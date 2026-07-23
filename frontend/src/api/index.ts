import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import type {
  ApiEnvelope,
  Paginated,
  ProductListItem,
  Proposal,
  ProposalCreateRequest,
  ProposalUpdateRequest,
  Quotation,
  QuotationCreateRequest,
  QuotationUpdateRequest,
  ShareCreateRequest,
  ShareResult,
} from '@/types/sales'

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
    suppressErrorMessage?: boolean
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

    if (error.response?.status === 403 && !originalRequest.suppressErrorMessage) {
      const detail: any = (error.response as any).data
      ElMessage.error(detail?.detail?.msg || detail?.message || '无权限访问该资源')
    }

    // Surface backend error messages for non-401/403 cases.
    if (error.response?.status && error.response.status !== 401) {
      const raw = (error.response as any).data
      console.error('[API Error]', error.response.status, raw)
      // FastAPI custom HTTPException: { detail: { code, msg } }
      // FastAPI validation error: { detail: [{ loc, msg, type }] }
      let msg: string | undefined
      if (typeof raw === 'object' && raw !== null) {
        msg = raw?.detail?.msg || raw?.detail?.[0]?.msg || raw?.message || raw?.msg || raw?.error
      }
      if (originalRequest.suppressErrorMessage) {
        // The requesting view renders a status-specific error state.
      } else if (msg) {
        ElMessage.error(msg)
      } else {
        const status = error.response.status
        if (status === 404) {
          ElMessage.error('接口不存在或后端服务未正确配置路由')
        } else if (status === 422) {
          ElMessage.error('请求参数验证失败，请检查文件格式和大小')
        } else if (status === 413) {
          ElMessage.error('文件过大，上传失败')
        } else if (status === 415) {
          ElMessage.error('不支持的文件类型')
        } else if (status === 400) {
          ElMessage.error('请求参数错误')
        } else if (status >= 500) {
          ElMessage.error(`服务器错误 (${status})`)
        } else {
          ElMessage.error(`请求失败 (HTTP ${status})`)
        }
      }
    } else if (!error.response) {
      console.error('[API Network Error]', error.message)
      if (!originalRequest.suppressErrorMessage) {
        ElMessage.error('网络连接失败，请检查后端服务是否正常运行 (http://localhost:8000)')
      }
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

export interface ProductListParams {
  keyword?: string
  status?: string
  stock_status?: string
  page?: number
  size?: number
}

export const productApi = {
  list: (params?: ProductListParams) =>
    api.get('/products', { params }) as Promise<ApiEnvelope<Paginated<ProductListItem>>>,
  get: (id: string) => api.get(`/products/${id}`, { suppressErrorMessage: true }),
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
  bindProductImages: (id: string, data: { attachment_ids: string[] }) =>
    api.post(`/products/${id}/images`, data),
  unbindProductImage: (id: string, imageId: string) =>
    api.delete(`/products/${id}/images/${imageId}`),
  setCoverImage: (id: string, imageId: string) =>
    api.patch(`/products/${id}/images/${imageId}/cover`),
  reorderProductImages: (id: string, data: { items: Array<{ image_id: string; sort: number }> }) =>
    api.patch(`/products/${id}/images/reorder`, data),
  bindSceneImages: (id: string, data: { scene_image_ids: string[] }) =>
    api.post(`/products/${id}/scene-images`, data),
  unbindSceneImage: (id: string, sceneImageId: string) =>
    api.delete(`/products/${id}/scene-images/${sceneImageId}`),
  reorderSceneImages: (id: string, data: { items: Array<{ scene_image_id: string; sort: number }> }) =>
    api.patch(`/products/${id}/scene-images/reorder`, data),
}

export const versionApi = {
  get: () => api.get('/version'),
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

export interface ProposalListParams {
  keyword?: string
  status?: string
  page?: number
  size?: number
}

/**
 * Normalizes proposal API responses for forward/backward compatibility.
 *
 * The new backend wraps every proposal response in ``{ code, data }``.
 * The old running backend may return the bare ``Proposal`` object directly.
 * ``normalizeProposalEnvelope`` detects the shape and returns a typed
 * ``ApiEnvelope<Proposal>`` in all cases, without using ``any``.
 */
type ProposalEnvelopeOrBare =
  | { code: number; data: Proposal; msg?: string }
  | (Omit<Proposal, 'items'> & { items: unknown })

function _isProposalEnvelope(v: ProposalEnvelopeOrBare): v is { code: number; data: Proposal; msg?: string } {
  return 'code' in v && typeof v.code === 'number' && 'data' in v
}

function normalizeProposalEnvelope(p: Promise<ProposalEnvelopeOrBare>): Promise<ApiEnvelope<Proposal>> {
  return p.then((res) => {
    if (_isProposalEnvelope(res)) {
      return res
    }
    return { code: 200, data: res as Proposal }
  })
}

export interface QuotationListParams {
  proposal_id?: string
  status?: string
  page?: number
  size?: number
}

export const proposalApi = {
  list: (params?: ProposalListParams) =>
    api.get('/proposals', { params }) as Promise<ApiEnvelope<Paginated<Proposal>>>,
  get: (id: string) => normalizeProposalEnvelope(
    api.get(`/proposals/${id}`) as Promise<ApiEnvelope<Proposal>>,
  ),
  create: (data: ProposalCreateRequest) => normalizeProposalEnvelope(
    api.post('/proposals', data) as Promise<ApiEnvelope<Proposal>>,
  ),
  update: (id: string, data: ProposalUpdateRequest) => normalizeProposalEnvelope(
    api.put(`/proposals/${id}`, data) as Promise<ApiEnvelope<Proposal>>,
  ),
  delete: (id: string) => api.delete(`/proposals/${id}`),
  confirm: (id: string) => api.post(`/proposals/${id}/confirm`),
  revertConfirmation: (id: string) => normalizeProposalEnvelope(
    api.post(`/proposals/${id}/revert-confirmation`) as Promise<ApiEnvelope<Proposal>>,
  ),
}

export const quotationApi = {
  list: (params?: QuotationListParams) =>
    api.get('/quotations', { params }) as Promise<ApiEnvelope<Paginated<Quotation>>>,
  get: (id: string) => api.get(`/quotations/${id}`) as Promise<ApiEnvelope<Quotation>>,
  create: (data: QuotationCreateRequest) => api.post('/quotations', data) as Promise<ApiEnvelope<Quotation>>,
  update: (id: string, data: QuotationUpdateRequest) => api.put(`/quotations/${id}`, data) as Promise<ApiEnvelope<Quotation>>,
  exportPdf: (id: string) =>
    api.get(`/quotations/${id}/pdf`, { responseType: 'blob' }) as unknown as Promise<Blob>,
  confirm: (id: string) => api.post(`/quotations/${id}/confirm`),
}

export const shareApi = {
  create: (data: ShareCreateRequest) => api.post('/shares', data) as Promise<ApiEnvelope<ShareResult>>,
  list: () => api.get('/shares') as Promise<{ data: { list: { id: string; share_type: 'proposal' | 'quotation'; target_id: string; creator_id: string; status: 'active' | 'disabled' | 'expired'; create_time: string | null }[] } }>,
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

export interface SceneImage {
  id: string
  name: string
  attachment_id: string
  file_url: string
  preview_url?: string
  file_name: string
  file_type: string
  sort: number
  create_time: string
  update_time: string
  bound_products: Array<{ id: string; product_no: string; product_name: string }>
}

export const sceneImageApi = {
  list: (params?: { keyword?: string; page?: number; size?: number; status?: string; product_keyword?: string; sort?: string }) =>
    api.get('/scene-images', { params }),
  get: (id: string) => api.get(`/scene-images/${id}`),
  create: (data: { name: string; attachment_id: string; sort?: number; product_ids?: string[] }) =>
    api.post('/scene-images', data),
  update: (id: string, data: { name?: string; attachment_id?: string; sort?: number }) =>
    api.put(`/scene-images/${id}`, data),
  delete: (id: string) => api.delete(`/scene-images/${id}`),
  bind: (id: string, productIds: string[]) =>
    api.post(`/scene-images/${id}/bind`, { product_ids: productIds }),
  unbind: (id: string, productIds: string[]) =>
    api.post(`/scene-images/${id}/unbind`, { product_ids: productIds }),
  batchBind: (sceneImageIds: string[], productIds: string[]) =>
    api.post('/scene-images/batch-bind', { scene_image_ids: sceneImageIds, product_ids: productIds }),
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
