/**
 * AI 配置中心 API（v1.9.5）。
 *
 * 对应后端 app/api/v1/ai_config.py：
 *   GET  /ai/config            两个 scope 的生效配置（密钥只出掩码）
 *   PUT  /ai/config/{scope}    局部更新（未出现的字段保持原值）
 *   POST /ai/config/{scope}/test  最小连通性探测
 *
 * 仅 admin 可用：后端对 role_code != admin 一律 403。
 */
import api from '@/api'
import type { ApiEnvelope } from '@/types/sales'

export type AiConfigScope = 'knowledge' | 'content'

export interface AiConfigItem {
  scope: AiConfigScope
  label: string
  api_url: string | null
  api_key_masked: string | null
  has_api_key: boolean
  chat_model: string | null
  chat_models: string[]
  embedding_model: string | null
  embedding_api_url: string | null
  embedding_api_key_masked: string | null
  timeout_seconds: number | null
  enabled: boolean
  /** db = 数据库覆盖生效；env = 当前回落自环境变量 */
  source: 'db' | 'env' | string
}

export interface AiConfigUpdatePayload {
  api_url?: string | null
  api_key?: string | null
  chat_model?: string | null
  chat_models?: string[] | null
  embedding_model?: string | null
  embedding_api_url?: string | null
  embedding_api_key?: string | null
  timeout_seconds?: number | null
  enabled?: boolean | null
}

export interface AiConfigTestResult {
  scope: AiConfigScope
  ok: boolean
  model: string | null
  latency_ms: number | null
  detail: string | null
}

/**
 * 约定：`@/api` 的响应拦截器已经做了 `response => response.data`，
 * 所以运行时拿到的就是后端 envelope `{code, data}`，业务字段在 `.data` 下。
 * 类型上沿用 api/content.ts 的做法显式 as 一次（axios 的泛型是 AxiosResponse<T>）。
 */

export async function fetchAiConfig(): Promise<AiConfigItem[]> {
  const resp = (await api.get('/ai/config')) as unknown as ApiEnvelope<{
    items: AiConfigItem[]
  }>
  return resp.data?.items ?? []
}

export async function updateAiConfig(
  scope: AiConfigScope,
  payload: AiConfigUpdatePayload,
): Promise<AiConfigItem> {
  const resp = (await api.put(`/ai/config/${scope}`, payload)) as unknown as ApiEnvelope<AiConfigItem>
  return resp.data
}

export async function testAiConfig(scope: AiConfigScope): Promise<AiConfigTestResult> {
  const resp = (await api.post(`/ai/config/${scope}/test`)) as unknown as ApiEnvelope<AiConfigTestResult>
  return resp.data
}
