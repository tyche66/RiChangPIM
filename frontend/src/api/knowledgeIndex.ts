/**
 * 向量索引管理 API（v1.9.9）。
 *
 * 对应后端 app/api/v1/knowledge_index_admin.py：
 *   GET  /knowledge-index/settings   配置 + 调度状态
 *   PUT  /knowledge-index/settings   更新配置（run_now_max_products 为后端硬上限只读）
 *   GET  /knowledge-index/status     状态卡：心跳/下次调度/队列/隔离
 *   GET  /knowledge-index/runs       最近运行报告
 *   POST /knowledge-index/run-now    手动运行（后端强制每次 ≤200 个产品）
 *   POST /knowledge-index/jobs/reset 授权的失败任务重置
 *
 * 安全约定：任何响应都不含密钥；token 用量区分实测/估算。
 */
import api from '@/api'
import type { ApiEnvelope } from '@/types/sales'

export interface KnowledgeIndexSettings {
  enabled: boolean
  timezone: string
  window_start: string
  window_end: string
  safety_cutoff_minutes: number
  reconcile_batch_size: number
  embedding_batch_size: number
  request_interval_seconds: number
  request_timeout_seconds: number
  max_attempts: number
  backoff_base_seconds: number
  backoff_max_seconds: number
  dead_retention_days: number
  stale_lock_minutes: number
  run_now_max_products: number
  run_now_max_duration_seconds: number
}

export type SchedulerStatus =
  | 'idle'
  | 'window_active'
  | 'run_now_active'
  | 'stopping'
  | 'disabled'

export interface SchedulerState {
  status: SchedulerStatus
  holder: string | null
  heartbeat_at: string | null
  next_window_start_at: string | null
  next_cutoff_at: string | null
  current_run_id: string | null
  last_run_id: string | null
  last_run_finished_at: string | null
}

export interface SettingsResponse {
  settings: KnowledgeIndexSettings
  scheduler: SchedulerState
  effective_embedding_model: string | null
  effective_embedding_version: string | null
}

export interface QueueOverview {
  by_status: Record<string, number>
  backlog: number
  quarantined: number
  dead_retention_days: number
  dead_expired_purgeable: number
  dead_retained: number
  oldest_dead_at: string | null
}

export interface KnowledgeIndexRunReport {
  id: string
  trigger_type: 'scheduled' | 'run_now'
  operator: string | null
  status: 'running' | 'completed' | 'stopped' | 'failed'
  started_at: string | null
  finished_at: string | null
  timezone: string | null
  window_start_at: string | null
  window_end_at: string | null
  cutoff_at: string | null
  scanned_count: number
  queued_count: number
  embedding_success_count: number
  hash_skipped_count: number
  failed_count: number
  quarantined_count: number
  batch_count: number
  rate_limited_count: number
  stale_reclaimed_count: number
  dead_purged_count: number
  backlog_before: number
  backlog_after: number
  embedding_model: string | null
  embedding_version: string | null
  token_usage_actual: number | null
  token_usage_estimated: number | null
  error_summary: string | null
  details: Record<string, unknown> | null
}

export interface StatusResponse {
  enabled: boolean
  scheduler_status: SchedulerStatus
  heartbeat_at: string | null
  heartbeat_stale: boolean
  next_window_start_at: string
  next_cutoff_at: string
  window_active: boolean
  current_run: KnowledgeIndexRunReport | null
  last_run: KnowledgeIndexRunReport | null
  queue: QueueOverview
}

export interface KnowledgeIndexSettingsUpdatePayload {
  enabled?: boolean | null
  timezone?: string | null
  window_start?: string | null
  window_end?: string | null
  safety_cutoff_minutes?: number | null
  reconcile_batch_size?: number | null
  embedding_batch_size?: number | null
  request_interval_seconds?: number | null
  request_timeout_seconds?: number | null
  max_attempts?: number | null
  backoff_base_seconds?: number | null
  backoff_max_seconds?: number | null
  dead_retention_days?: number | null
  stale_lock_minutes?: number | null
  run_now_max_duration_seconds?: number | null
}

export interface RunNowResult {
  accepted: boolean
  max_products: number
  max_duration_seconds: number
}

export interface JobResetResult {
  reset: number
}

/** 约定：`@/api` 的响应拦截器已解包为 `{code, data}` envelope。 */
export async function fetchKnowledgeIndexSettings(): Promise<SettingsResponse> {
  const resp = (await api.get('/knowledge-index/settings')) as unknown as ApiEnvelope<SettingsResponse>
  return resp.data
}

export async function updateKnowledgeIndexSettings(
  payload: KnowledgeIndexSettingsUpdatePayload,
): Promise<KnowledgeIndexSettings> {
  const resp = (await api.put('/knowledge-index/settings', payload)) as unknown as ApiEnvelope<KnowledgeIndexSettings>
  return resp.data
}

export async function fetchKnowledgeIndexStatus(): Promise<StatusResponse> {
  const resp = (await api.get('/knowledge-index/status')) as unknown as ApiEnvelope<StatusResponse>
  return resp.data
}

export async function fetchKnowledgeIndexRuns(limit = 30): Promise<KnowledgeIndexRunReport[]> {
  const resp = (await api.get('/knowledge-index/runs', { params: { limit } })) as unknown as ApiEnvelope<{ items: KnowledgeIndexRunReport[] }>
  return resp.data?.items ?? []
}

export async function runKnowledgeIndexNow(): Promise<RunNowResult> {
  const resp = (await api.post('/knowledge-index/run-now')) as unknown as ApiEnvelope<RunNowResult>
  return resp.data
}

export async function resetKnowledgeIndexJobs(payload: {
  job_ids?: string[]
  scope?: 'dead' | 'failed'
  limit?: number
}): Promise<JobResetResult> {
  const resp = (await api.post('/knowledge-index/jobs/reset', payload)) as unknown as ApiEnvelope<JobResetResult>
  return resp.data
}
