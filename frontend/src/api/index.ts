import axios, {
  type AxiosError,
  type AxiosProgressEvent,
  type InternalAxiosRequestConfig,
} from 'axios'
import { ElMessage } from 'element-plus'
import type {
  ApiEnvelope,
  Paginated,
  ProductListItem,
  ProjectSpace,
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

// 后台是以 base '/admin/' 构建的（scripts/build_frontends.sh 里 VITE_BASE_PATH=/admin/），
// 硬编码 '/login' 的整页跳转会落到 nginx 的 location /（门户 SPA），门户没有 /login
// 路由 → 用户看到白屏。这里统一拼上 import.meta.env.BASE_URL（dev 下就是 '/'）。
function loginUrl(): string {
  const base = (import.meta.env.BASE_URL || '/').replace(/\/+$/, '')
  return `${base}/login`
}

// 会话失效时的整页跳转。已经在登录页时不再重复赋值，避免刷新循环。
function redirectToLogin() {
  const target = loginUrl()
  if (window.location.pathname === target) return
  window.location.href = target
}

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
      redirectToLogin()
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
        redirectToLogin()
        return Promise.reject(error)
      }

      if (!refreshPromise) {
        refreshPromise = api.post('/auth/refresh', { refresh_token: rt }, { skipAuth: true })
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
            redirectToLogin()
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
      console.error('[API Error]', 403, detail)
      if (!originalRequest.suppressErrorMessage) {
        ElMessage.error(detail?.detail?.msg || detail?.message || '无权限访问该资源')
      }
    }

    /*
     * Surface backend error messages for non-401/403 cases.
     * 403 必须排除掉：后端的 403 都带 detail.msg，上面那段已经弹过一次，再走一遍
     * 通用分支就是同一个原因弹两条一模一样的 toast（分享页的密码门最明显）。
     */
    if (error.response?.status && error.response.status !== 401 && error.response.status !== 403) {
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
        // 超时和真正连不上要分开说：内容生成/导入这类慢接口超时时后端往往还在干活，
        // 报「后端服务未运行」会把用户引到错误的排查方向。
        if (error.code === 'ECONNABORTED' || /timeout/i.test(error.message || '')) {
          ElMessage.error('请求超时：服务端仍在处理或耗时过长，请稍后到列表确认结果')
        } else {
          ElMessage.error('网络连接失败，请检查后端服务是否正常运行')
        }
      }
    }

    return Promise.reject(error)
  }
)

export default api

export const authApi = {
  login: (data: { username: string; password: string }) =>
    api.post('/auth/login', data),
  logout: (refreshToken?: string | null) => {
    // 调用方可显式传入（登出前 store 还持有它）；否则回落到 localStorage。
    // 后端只有收到 refresh_token 才会撤销它，否则退出后仍可换取新会话。
    const token = refreshToken ?? localStorage.getItem('refresh_token')
    return api.post('/auth/logout', token ? { refresh_token: token } : {})
  },
  getCurrentUser: () => api.get('/auth/me'),
  refresh: (refreshToken: string) =>
    api.post('/auth/refresh', { refresh_token: refreshToken }, { skipAuth: true }),
  changePassword: (oldPassword: string, newPassword: string) =>
    api.post('/auth/change-password', {
      old_password: oldPassword,
      new_password: newPassword,
    }),
}

export interface ProductListParams {
  keyword?: string
  status?: string
  stock_status?: string
  page?: number
  size?: number
}

/** 三级筛选导航的维度：与后端 /products/filter-options 的 dimension 一一对应。 */
export type ProductFilterDimension =
  | 'series'
  | 'brand'
  | 'supplier'
  | 'status'
  | 'stock'
  | 'category'

export interface ProductFilterOption {
  value: string
  label: string
  count: number
}

export interface ProductFilterOptionsData {
  dimension: ProductFilterDimension
  items: ProductFilterOption[]
}

/** 重传产品包时可选的重复处理方式。 */
export type ImportMode = 'overwrite' | 'append' | 'skip'

/** 产品编号别名冲突（103800022 ↔ P-103800022）的处理方式。 */
export type ImportAliasAction = 'overwrite_alias' | 'create_new'

export interface ImportConflictRow {
  row: number
  product_no: string
  product_name: string
  existing_name: string
  existing_image_count: number
}

export interface ImportAliasConflictRow {
  row: number
  product_no: string
  product_name: string
  alias_product_id: string | null
  alias_product_no: string
  existing_name: string | null
  existing_image_count: number
  /** safe = 名称一致、候选唯一，可按别名覆盖；high = 绝不自动覆盖 */
  risk: 'safe' | 'high'
  reason: string
}

export interface ImportInvalidRow {
  row: number
  product_no: string
  reason: string
}

export interface ImportPreflightPayload {
  token: string
  expires_at: string
  file_name: string
  size: number
  sha256: string
  header_row: number
  total_rows: number
  new_count: number
  /** 精确编号命中的已存在产品数（= existing_count，保留旧字段兼容） */
  existing_count: number
  exact_existing_count: number
  /** 只差前导 P-、未精确命中的行数 */
  alias_conflict_count: number
  /** 名称一致、候选唯一，可按别名覆盖的行数 */
  alias_safe_count: number
  /** 名称不同 / 候选不唯一 / 产品已删除：绝不自动覆盖 */
  alias_high_risk_count: number
  invalid_count: number
  /** 会被新建的标签（表格里还没有的），用于在弹窗里先告知用户 */
  new_tags: Array<{ name: string; tag_type: string | null }>
  new_tag_count: number
  new_tag_type_default: string
  conflicts: ImportConflictRow[]
  conflicts_truncated: boolean
  alias_conflicts: ImportAliasConflictRow[]
  alias_conflicts_truncated: boolean
  invalid: ImportInvalidRow[]
  invalid_truncated: boolean
  notes: string[]
  image_warnings: string[]
  unknown_headers: string[]
}

export interface ImportCommitPayload {
  total: number
  success_count: number
  fail_count: number
  failures: Array<{ row: number; product_no: string; reason: string }>
  created_count: number
  updated_count: number
  appended_count: number
  skipped_count: number
  alias_updated_count: number
  alias_created_count: number
  images_replaced: number
  images_appended: number
  created_tags: number
  new_tag_names: string[]
  mode: ImportMode | 'create'
  backup_id: string | null
  notes: string[]
  image_count: number
  scene_image_count: number
  uploaded_count: number
  image_sources: string[]
  image_warnings: string[]
  header_row: number
  unknown_headers: string[]
  blank_rows: number
}

export const productApi = {
  list: (params?: ProductListParams) =>
    api.get('/products', { params }) as Promise<ApiEnvelope<Paginated<ProductListItem>>>,
  /*
   * 三级筛选导航的选项：不带 parent_id 返回二级，带 parent_id 返回该二级下的三级。
   * 选项与计数全部由后端按产品数据实时聚合，前端不缓存、也不写死任何分类名。
   */
  filterOptions: (params: { dimension: ProductFilterDimension; parent_id?: string }) =>
    api.get('/products/filter-options', { params }) as Promise<ApiEnvelope<ProductFilterOptionsData>>,
  get: (id: string) => api.get(`/products/${id}`, { suppressErrorMessage: true }),
  create: (data: unknown) => api.post('/products', data),
  update: (id: string, data: unknown) => api.put(`/products/${id}`, data),
  delete: (id: string) => api.delete(`/products/${id}`),
  updateStatus: (id: string, status: string) =>
    api.patch(`/products/${id}/status`, { status }),
  clone: (id: string) => api.post(`/products/${id}/clone`),
  export: (params?: Record<string, unknown>) =>
    api.get('/products/export', { params, responseType: 'blob' }),
  importTemplate: () =>
    api.get('/products/import-template', { responseType: 'blob' }) as unknown as Promise<Blob>,
  /*
   * 带图导入的请求跟别的接口不是一个量级：上传本身可能几十上百 MB，服务端还要解包、
   * 逐张算 sha256、逐张传 MinIO。默认的 30s 超时会在后端还在干活时就把连接掀掉
   * （前端报错、后端继续写库 → 用户以为失败、其实导入了一半）。
   * 905s 是跟 nginx 的 proxy_read_timeout 900s（docker/nginx/nginx.conf 里
   * location /api/v1/products/import）对齐，多留 5s 让网关先返回它的 504。
   * suppressErrorMessage：Import.vue 要按 413 / 超时 / detail.msg 分别给提示，
   * 不走拦截器那条通用 toast，否则同一个错误弹两遍。
   */
  import: (
    data: unknown,
    params?: Record<string, unknown>,
    onProgress?: (percent: number) => void
  ) =>
    api.post('/products/import', data, {
      params,
      timeout: 905000,
      suppressErrorMessage: true,
      onUploadProgress: onProgress
        ? (event: AxiosProgressEvent) => {
            if (event.total) onProgress(Math.round((event.loaded * 100) / event.total))
          }
        : undefined,
    }),
  /*
   * 重传产品包的两段式入口：
   *   preflight 只上传 + 解析 + 查重，零写库，返回 token 与冲突清单；
   *   commit    带着 token 和用户选的模式（overwrite / append / skip）真正写库。
   * 两段都用 905s 超时，理由同上：大包在服务端解图/传 MinIO 的时间远超默认 30s。
   */
  importPreflight: (data: unknown, onProgress?: (percent: number) => void) =>
    api.post('/products/import/preflight', data, {
      timeout: 905000,
      suppressErrorMessage: true,
      onUploadProgress: onProgress
        ? (event: AxiosProgressEvent) => {
            if (event.total) onProgress(Math.round((event.loaded * 100) / event.total))
          }
        : undefined,
    }) as Promise<{ code: number; data: ImportPreflightPayload }>,
  importCommit: (payload: {
    token: string
    mode: ImportMode
    backup?: boolean
    new_tag_type?: string
    alias_action?: ImportAliasAction
    alias_decisions?: Array<{ row: number; action: ImportAliasAction }>
  }) =>
    api.post('/products/import/commit', payload, {
      timeout: 905000,
      suppressErrorMessage: true,
    }) as Promise<{ code: number; data: ImportCommitPayload }>,
  cancelImportPreflight: (token: string) =>
    api.delete(`/products/import/preflight/${encodeURIComponent(token)}`, {
      suppressErrorMessage: true,
    }),
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

// ---------------------------------------------------------------------------
// Track C: 项目空间（楼层/房间/区域）
// ---------------------------------------------------------------------------

export const projectSpaceApi = {
  list: (projectId: string) =>
    api.get(`/projects/${projectId}/spaces`) as Promise<ApiEnvelope<ProjectSpace[]>>,

  create: (projectId: string, data: {
    space_name: string
    space_type?: string
    parent_id?: string | null
    sort?: number
  }) => api.post(`/projects/${projectId}/spaces`, data) as Promise<ApiEnvelope<ProjectSpace>>,

  update: (projectId: string, spaceId: string, data: {
    space_name?: string
    space_type?: string
    parent_id?: string | null
    sort?: number
  }) => api.put(`/projects/${projectId}/spaces/${spaceId}`, data) as Promise<ApiEnvelope<ProjectSpace>>,

  delete: (projectId: string, spaceId: string) =>
    api.delete(`/projects/${projectId}/spaces/${spaceId}`) as Promise<
      ApiEnvelope<{ id: string; deleted: number }>
    >,
}

export const proposalApi = {
  list: (params?: ProposalListParams) =>
    api.get('/proposals', { params }) as Promise<ApiEnvelope<Paginated<Proposal>>>,
  get: (id: string) => normalizeProposalEnvelope(
    api.get(`/proposals/${id}`) as Promise<ApiEnvelope<Proposal>>,
  ),
  create: (data: ProposalCreateRequest, options?: { suppressErrorMessage?: boolean }) => normalizeProposalEnvelope(
    api.post('/proposals', data, options) as Promise<ApiEnvelope<Proposal>>,
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
  // 分享页自己渲染密码门 / 失效提示，拦截器再弹 toast 只会和页面上的 alert 说同一句话
  get: (token: string, password?: string) =>
    api.post(`/share/${token}`, password ? { password } : {}, {
      skipAuth: true,
      suppressErrorMessage: true,
    }),
  revoke: (id: string) => api.delete(`/shares/${id}`),
}

export const userApi = {
  list: (params?: Record<string, unknown>) => api.get('/users', { params }),
  get: (id: string) => api.get(`/users/${id}`),
  create: (data: unknown, config?: { suppressErrorMessage?: boolean }) =>
    api.post('/users', data, config),
  update: (id: string, data: unknown, config?: { suppressErrorMessage?: boolean }) =>
    api.put(`/users/${id}`, data, config),
  delete: (id: string, config?: { suppressErrorMessage?: boolean }) =>
    api.delete(`/users/${id}`, config),
  resetPassword: (
    id: string,
    data: { new_password: string },
    config?: { suppressErrorMessage?: boolean }
  ) => api.post(`/users/${id}/reset-password`, data, config),
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
