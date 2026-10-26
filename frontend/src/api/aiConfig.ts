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

export async function fetchAiConfig(): Promise<AiConfigItem[]> {
  const resp = await api.get<ApiEnvelope<{ items: AiConfigItem[] }>>('/ai/config')
  return resp.data.data?.items ?? []
}

export async function updateAiConfig(
  scope: AiConfigScope,
  payload: AiConfigUpdatePayload,
): Promise<AiConfigItem> {
  const resp = await api.put<ApiEnvelope<AiConfigItem>>(`/ai/config/${scope}`, payload)
  return resp.data.data
}

export async function testAiConfig(scope: AiConfigScope): Promise<AiConfigTestResult> {
  const resp = await api.post<ApiEnvelope<AiConfigTestResult>>(`/ai/config/${scope}/test`)
  return resp.data.data
}
