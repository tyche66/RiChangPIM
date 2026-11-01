/**
 * 公告 API（FR-4）。
 *
 * 列表响应是 { code, data: { list, total } } 信封；/active 为匿名接口，
 * 登录前后都可调用。已读状态存 localStorage，服务端不记录。
 */
import api from '@/api'
import type { ApiEnvelope } from '@/types/sales'

export type AnnouncementAudience = 'admin' | 'portal' | 'all'
export type AnnouncementLevel = 'info' | 'important'

/** 管理列表行的派生状态（disabled 含草稿/手动停用）。 */
export type AnnouncementStatus = 'active' | 'scheduled' | 'expired' | 'disabled'

export interface Announcement {
  id: string
  title: string
  content_md: string
  audience: AnnouncementAudience
  level: AnnouncementLevel
  enabled: boolean
  publish_at: string | null
  expire_at: string | null
  create_time: string | null
  update_time: string | null
  deleted_at: string | null
  is_deleted: boolean
}

export interface AnnouncementActive {
  id: string
  title: string
  content_md: string
  level: AnnouncementLevel
  audience: AnnouncementAudience
  publish_at: string | null
  update_time: string | null
}

export interface AnnouncementListResult {
  list: Announcement[]
  total: number
}

export interface AnnouncementPayload {
  title: string
  content_md: string
  audience: AnnouncementAudience
  level: AnnouncementLevel
  enabled: boolean
  publish_at: string | null
  expire_at: string | null
}

export const announcementApi = {
  list: (params?: {
    status?: AnnouncementStatus
    audience?: AnnouncementAudience
    page?: number
    page_size?: number
    include_deleted?: boolean
  }) => api.get('/announcements', { params }) as Promise<ApiEnvelope<AnnouncementListResult>>,

  create: (data: AnnouncementPayload) =>
    api.post('/announcements', data) as Promise<ApiEnvelope<Announcement>>,

  update: (id: string, data: Partial<AnnouncementPayload>) =>
    api.put(`/announcements/${id}`, data) as Promise<ApiEnvelope<Announcement>>,

  remove: (id: string) =>
    api.delete(`/announcements/${id}`) as Promise<ApiEnvelope<{ id: string }>>,

  /** 匿名接口：audience=admin 用于后台弹窗，portal 用于门户。 */
  active: (audience: 'admin' | 'portal') =>
    api.get('/announcements/active', { params: { audience } }) as Promise<
      ApiEnvelope<{ list: AnnouncementActive[] }>
    >,
}
