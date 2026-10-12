/**
 * 客户域 API（HLD §8.3）。响应统一为 { code, data }。
 *
 * 注意几个后端契约细节（与 app/api/v1/customers.py 对齐）：
 * - 子资源写接口（dialogues / requirements / follow-ups / proposals）用的是
 *   Query 参数而不是 JSON body，所以这里以 params 发送；
 * - 列表不返回 PII，只有 has_phone；详情返回掩码串；明文走 /pii（审计+限速）；
 * - 阶段迁移用 PATCH body { to_stage, reason? }；移交用 PUT ?new_owner_id=。
 */
import api from '@/api'
import type { ApiEnvelope, Paginated } from '@/types/sales'

export interface CustomerListItem {
  id: string
  customer_no: string | null
  name: string
  source: string
  level: string | null
  stage: string
  owner_sales_id: string
  has_phone: boolean
  budget_min: number | null
  budget_max: number | null
  project_count: number
  last_activity_at: string | null
  create_time: string | null
}

export interface CustomerDetail {
  id: string
  customer_no: string | null
  name: string
  source: string
  level: string | null
  stage: string
  owner_sales_id: string
  owner_sales_name: string | null
  phone_masked: string | null
  wechat_masked: string | null
  address_masked: string | null
  has_phone: boolean
  budget_min: number | null
  budget_max: number | null
  style_preference: string | null
  remark: string | null
  last_activity_at: string | null
  create_time: string | null
  update_time: string | null
}

export interface CustomerListParams {
  stage?: string
  level?: string
  owner_sales_id?: string
  q?: string
  page?: number
  size?: number
  sort?: string
}

export interface CustomerCreateRequest {
  name: string
  source?: string
  level?: string | null
  phone?: string | null
  wechat?: string | null
  address?: string | null
  budget_min?: number | null
  budget_max?: number | null
  style_preference?: string | null
  remark?: string | null
  owner_sales_id?: string | null
}

export type CustomerUpdateRequest = Partial<CustomerCreateRequest>

export interface CustomerPII {
  phone: string | null
  wechat: string | null
  address: string | null
}

export interface CustomerSummary {
  project_count: number
  proposal_count: number
  confirmed_amount: number | null
  confirmed_amount_visible: boolean
}

export interface CustomerTimelineItem {
  type: string
  id: string
  content: string
  created_at: string | null
  operator_name: string | null
}

export interface CustomerDialogue {
  id: string
  channel: string
  direction: string
  content: string
  occurred_at: string | null
  create_time?: string | null
}

export interface CustomerRequirement {
  id: string
  content: string
  source: string
  confirmed: boolean
  create_time?: string | null
}

export interface CustomerFollowUp {
  id: string
  method: string
  content: string
  result: string | null
  next_follow_at: string | null
  done_at: string | null
  create_time?: string | null
}

export interface CustomerProposalItem {
  id: string
  proposal_no: string | null
  proposal_name: string
  status: string
  total_face_value: number | null
  create_time: string | null
}

export const customerApi = {
  list: (params?: CustomerListParams) =>
    api.get('/customers', { params }) as Promise<ApiEnvelope<Paginated<CustomerListItem>>>,

  get: (id: string) => api.get(`/customers/${id}`) as Promise<ApiEnvelope<CustomerDetail>>,

  create: (data: CustomerCreateRequest, force = false) =>
    api.post('/customers', data, { params: force ? { force: true } : {} }) as Promise<
      ApiEnvelope<CustomerDetail>
    >,

  update: (id: string, data: CustomerUpdateRequest) =>
    api.put(`/customers/${id}`, data) as Promise<ApiEnvelope<CustomerDetail>>,

  transitionStage: (id: string, toStage: string, reason?: string) =>
    api.patch(`/customers/${id}/stage`, { to_stage: toStage, reason }) as Promise<
      ApiEnvelope<CustomerDetail>
    >,

  remove: (id: string, cascade = false) =>
    api.delete(`/customers/${id}`, { params: cascade ? { cascade: true } : {} }),

  getPii: (id: string) =>
    api.get(`/customers/${id}/pii`) as Promise<ApiEnvelope<CustomerPII>>,

  transferOwner: (id: string, newOwnerId: string) =>
    api.put(`/customers/${id}/owner`, null, { params: { new_owner_id: newOwnerId } }) as Promise<
      ApiEnvelope<CustomerDetail>
    >,

  summary: (id: string) =>
    api.get(`/customers/${id}/summary`) as Promise<ApiEnvelope<CustomerSummary>>,

  timeline: (id: string, params?: { page?: number; size?: number }) =>
    api.get(`/customers/${id}/timeline`, { params }) as Promise<
      ApiEnvelope<Paginated<CustomerTimelineItem>>
    >,

  dialogues: (id: string, params?: { page?: number; size?: number }) =>
    api.get(`/customers/${id}/dialogues`, { params }) as Promise<
      ApiEnvelope<Paginated<CustomerDialogue>>
    >,

  createDialogue: (
    id: string,
    data: { channel?: string; direction?: string; content: string },
  ) =>
    api.post(`/customers/${id}/dialogues`, null, { params: data }) as Promise<
      ApiEnvelope<CustomerDialogue>
    >,

  requirements: (id: string, params?: { page?: number; size?: number }) =>
    api.get(`/customers/${id}/requirements`, { params }) as Promise<
      ApiEnvelope<Paginated<CustomerRequirement>>
    >,

  createRequirement: (id: string, data: { content: string; source?: string }) =>
    api.post(`/customers/${id}/requirements`, null, { params: data }) as Promise<
      ApiEnvelope<CustomerRequirement>
    >,

  followUps: (id: string, params?: { page?: number; size?: number }) =>
    api.get(`/customers/${id}/follow-ups`, { params }) as Promise<
      ApiEnvelope<Paginated<CustomerFollowUp>>
    >,

  createFollowUp: (
    id: string,
    data: {
      method?: string
      content: string
      result?: string | null
      next_follow_at?: string | null
    },
  ) =>
    api.post(`/customers/${id}/follow-ups`, null, { params: data }) as Promise<
      ApiEnvelope<CustomerFollowUp>
    >,

  proposals: (id: string, params?: { page?: number; size?: number }) =>
    api.get(`/customers/${id}/proposals`, { params }) as Promise<
      ApiEnvelope<Paginated<CustomerProposalItem>>
    >,

  createProposal: (id: string, proposalName: string) =>
    api.post(`/customers/${id}/proposals`, null, {
      params: { proposal_name: proposalName },
    }) as Promise<ApiEnvelope<CustomerProposalItem>>,
}
