/**
 * 提醒 / 通知 API（HLD §8.5）。
 *
 * 列表响应是 { code, data: { list, total } }（不是分页 page/size 形状）。
 * 完成 / 推迟 / 取消 都要求 reminder:edit。
 */
import api from '@/api'
import type { ApiEnvelope } from '@/types/sales'

export interface Reminder {
  id: string
  rule_code: string
  target_type: string
  target_id: string
  assignee_id: string
  title: string
  body: string | null
  due_at: string | null
  status: string
  dedupe_key: string
  snoozed_until: string | null
  fired_at: string | null
  done_at: string | null
  attempts: number
  escalated: boolean
  payload: Record<string, unknown>
  create_time: string | null
}

export interface Notification {
  id: string
  user_id: string
  title: string
  body: string | null
  kind: string
  link: string | null
  reminder_id: string | null
  read_at: string | null
  create_time: string | null
}

export interface ReminderListResult {
  list: Reminder[]
  total: number
}

export interface NotificationListResult {
  list: Notification[]
  total: number
}

export const reminderApi = {
  list: (params?: { status?: string; assignee_id?: string }) =>
    api.get('/reminders', { params }) as Promise<ApiEnvelope<ReminderListResult>>,

  done: (id: string) => api.post(`/reminders/${id}/done`) as Promise<ApiEnvelope<Reminder>>,

  snooze: (id: string, until: string) =>
    api.post(`/reminders/${id}/snooze`, null, { params: { until } }) as Promise<
      ApiEnvelope<Reminder>
    >,

  cancel: (id: string) => api.post(`/reminders/${id}/cancel`) as Promise<ApiEnvelope<Reminder>>,

  notifications: (params?: { unread?: boolean }) =>
    api.get('/reminders/notifications', { params }) as Promise<
      ApiEnvelope<NotificationListResult>
    >,

  markRead: (data: { ids?: string[]; all?: boolean }) =>
    api.post('/reminders/notifications/read', data) as Promise<ApiEnvelope<{ updated: number }>>,
}
