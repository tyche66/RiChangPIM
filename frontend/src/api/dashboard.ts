/**
 * 驾驶舱 API（HLD §8.4）。挂 /api/v1/stats/dashboard/*。
 *
 * 空态约定：任何指标无数据 → { value: null, empty_reason }，前端用 EmptyMetric
 * 渲染「待录入/无权限/未启用」，禁止 0 占位。
 */
import api from '@/api'
import type { ApiEnvelope } from '@/types/sales'

export type EmptyReason = 'no_data' | 'no_permission' | 'module_disabled' | string

export interface MetricValue {
  value: number | null
  prev?: number
  trend?: number | null
  threshold_days?: number
  empty_reason?: EmptyReason
}

export interface ConfirmedAmount {
  visible: boolean
  value?: number | null
  currency?: string
  empty_reason?: EmptyReason
}

export interface OverviewData {
  range: { from: string; to: string }
  new_customers: MetricValue
  active_projects: MetricValue
  overdue_follow_ups: MetricValue
  stalled_projects: MetricValue
  confirmed_amount: ConfirmedAmount
  generated_at?: string
  cached?: boolean
}

export interface FunnelBucket {
  stage: string
  count: number
}

export interface FunnelData {
  customer_funnel: FunnelBucket[]
  project_stages: FunnelBucket[]
  cached?: boolean
}

export interface SalesRankRow {
  follower_id: string
  name: string
  count: number
  rank: number
}

export interface SalesData {
  ranking: SalesRankRow[]
  my_row: SalesRankRow | null
  cached?: boolean
}

export interface TodoReminder {
  id: string
  title: string
  body: string | null
  due_at: string | null
  status: string
  rule_code: string
}

export interface TodoFollowUp {
  id: string
  customer_id: string
  project_id: string | null
  method: string
  content: string
  next_follow_at: string | null
}

export interface TodosData {
  reminders: TodoReminder[]
  follow_ups: TodoFollowUp[]
  total_pending: number
  cached?: boolean
}

export interface ContentDashboardData {
  empty: boolean
  empty_reason: EmptyReason
}

export type DashboardRange = '7d' | '30d' | '90d'

export const dashboardApi = {
  overview: (range: DashboardRange) =>
    api.get('/stats/dashboard/overview', { params: { range } }) as Promise<
      ApiEnvelope<OverviewData>
    >,

  funnel: () =>
    api.get('/stats/dashboard/funnel') as Promise<ApiEnvelope<FunnelData>>,

  sales: (range: DashboardRange) =>
    api.get('/stats/dashboard/sales', { params: { range } }) as Promise<ApiEnvelope<SalesData>>,

  todos: (limit = 20) =>
    api.get('/stats/dashboard/todos', { params: { limit } }) as Promise<ApiEnvelope<TodosData>>,

  content: (range: DashboardRange) =>
    api.get('/stats/dashboard/content', { params: { range } }) as Promise<
      ApiEnvelope<ContentDashboardData>
    >,
}
