/**
 * 内容工坊 / 发布 / 曝光 API（HLD §8.5 / §9 / §10.4）。
 *
 * 已对齐后端 app/api/v1/content.py 的端点：
 *   POST /content/batches、GET /content/batches/{id}、GET /content/items/{id}、
 *   POST /content/items/{id}/{adopt|reject|produce|duplicate|publish}、
 *   POST /content/metrics、POST /content/metrics/import。
 *
 * 列表/编辑端点（GET /content/items、PUT /content/items/{id}、
 * GET /content/publications）按 HLD §12.1 的「列表/编辑」需要预留；
 * 若后端尚未提供，视图会落到空态而不是报错。
 */
import api from '@/api'
import type { ApiEnvelope, Paginated } from '@/types/sales'

export interface ContentItem {
  id: string
  batch_id: string
  item_type: string
  platform: string
  title: string | null
  body: string
  hashtags: string[]
  status: string
  display_state: string
  adopted_by: string | null
  adopted_at: string | null
  rejected_reason: string | null
  produced_at: string | null
  published_at: string | null
  closed_at: string | null
  edited: boolean
  verified_payload: Record<string, unknown> | null
  warnings: string[]
  external_ref: string | null
  model_provider: string | null
  model_name: string | null
  generation_version: string
  create_time: string | null
}

export interface ContentBatch {
  id: string
  title: string
  customer_id: string | null
  customer_name?: string | null
  project_id: string | null
  project_name?: string | null
  product_ids: string[]
  topic: string
  platform: string
  tone: string | null
  requested_count: number
  status: string
  error_msg: string | null
  model_provider: string | null
  model_name: string | null
  prompt_version: string
  latency_ms: number | null
  create_time: string | null
}

export interface ContentGenerateRequest {
  title: string
  topic: string
  platform: string
  tone?: string | null
  product_ids?: string[]
  customer_id?: string | null
  project_id?: string | null
  requested_count?: number
}

export interface ContentItemResult {
  id: string
  title: string | null
  body: string
  hashtags: string[]
  verified: boolean
  warnings: string[]
}

export interface ContentBatchResult {
  batch_id: string
  status: string
  items: ContentItemResult[]
}

export interface ContentPublication {
  id: string
  content_item_id: string
  platform: string
  account_name: string | null
  publish_url: string
  published_at: string
  video_attachment_id: string | null
  external_ref: string | null
  create_time: string | null
  /** 列表附带字段（后端可用时提供）。 */
  item_title?: string | null
  latest_metrics?: MetricSnapshot | null
}

export interface MetricSnapshot {
  id: string
  publication_id: string
  views: number | null
  likes: number | null
  comments: number | null
  shares: number | null
  favorites: number | null
  leads: number | null
  captured_at: string
  captured_date: string
  source: string
}

export interface MetricEntryRequest {
  publication_id: string
  views?: number | null
  likes?: number | null
  comments?: number | null
  shares?: number | null
  favorites?: number | null
  leads?: number | null
  captured_at?: string | null
  captured_date?: string | null
}

export interface MetricImportRow {
  row: number
  status: string
  publish_url: string | null
  captured_date: string | null
  error_code: string | null
  error_msg: string | null
}

export interface MetricImportResult {
  total: number
  created: number
  updated: number
  failed: number
  errors: MetricImportRow[]
  error_file_url: string | null
}

export interface PublishRequest {
  platform: string
  account_name?: string | null
  publish_url: string
  published_at?: string | null
  video_attachment_id?: string | null
  external_ref?: string | null
}

export const contentApi = {
  generate: (data: ContentGenerateRequest) =>
    api.post('/content/batches', data) as Promise<ApiEnvelope<ContentBatchResult>>,

  getBatch: (id: string) => api.get(`/content/batches/${id}`) as Promise<ApiEnvelope<ContentBatch>>,

  getItem: (id: string) => api.get(`/content/items/${id}`) as Promise<ApiEnvelope<ContentItem>>,

  listItems: (params?: { status?: string; platform?: string; page?: number; size?: number }) =>
    api.get('/content/items', { params, suppressErrorMessage: true }) as Promise<
      ApiEnvelope<Paginated<ContentItem>>
    >,

  updateItem: (id: string, data: { title?: string; body?: string; hashtags?: string[] }) =>
    api.put(`/content/items/${id}`, data) as Promise<ApiEnvelope<ContentItem>>,

  adopt: (id: string, confirm = false) =>
    api.post(`/content/items/${id}/adopt`, null, {
      params: confirm ? { confirm: true } : {},
    }) as Promise<ApiEnvelope<{ id: string; status: string }>>,

  reject: (id: string, reason: string) =>
    api.post(`/content/items/${id}/reject`, { reason }) as Promise<
      ApiEnvelope<{ id: string; status: string }>
    >,

  produce: (id: string) =>
    api.post(`/content/items/${id}/produce`) as Promise<ApiEnvelope<{ id: string; status: string }>>,

  duplicate: (id: string) =>
    api.post(`/content/items/${id}/duplicate`) as Promise<
      ApiEnvelope<{ id: string; status: string }>
    >,

  publish: (id: string, data: PublishRequest) =>
    api.post(`/content/items/${id}/publish`, data) as Promise<
      ApiEnvelope<{
        publication_id: string
        content_item_id: string
        platform: string
        publish_url: string
        published_at: string | null
      }>
    >,

  createMetric: (data: MetricEntryRequest) =>
    api.post('/content/metrics', data) as Promise<ApiEnvelope<MetricSnapshot>>,

  importMetrics: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/content/metrics/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }) as Promise<ApiEnvelope<MetricImportResult>>
  },

  listPublications: (params?: { page?: number; size?: number }) =>
    api.get('/content/publications', { params, suppressErrorMessage: true }) as Promise<
      ApiEnvelope<Paginated<ContentPublication>>
    >,

  publicationMetrics: (id: string) =>
    api.get(`/content/publications/${id}/metrics`) as Promise<
      ApiEnvelope<{ list: MetricSnapshot[]; total: number }>
    >,
}
