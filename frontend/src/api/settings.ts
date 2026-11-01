/**
 * 全局设置 API（FR-3）。
 *
 * 对应后端 app/api/v1/settings.py：
 *   GET /settings          管理员读取全部设置（含 logo_url）
 *   PUT /settings          管理员嵌套局部更新（未知 key / 超范围直接 422）
 *   GET /settings/public   匿名品牌字段（仅 portal 侧使用）
 *   GET /settings/logo?v=  匿名 Logo（浏览器直接 <img>，不走这里）
 *
 * 仅 admin 可读写：后端显式断言 role_code，非管理员一律 403。
 */
import api from '@/api'
import type { ApiEnvelope } from '@/types/sales'

export interface BrandSettings {
  site_name: string
  portal_title: string
  portal_subtitle: string
  footer_text: string
  logo_attachment_id: string | null
}

export interface ShareSettings {
  share_default_expire_hours: number
  share_default_max_access_count: number
  share_default_require_password: boolean
}

export interface BusinessSettings {
  quotation_default_tax_rate: number
  amount_decimal_places: number
  currency_symbol: string
}

export interface SystemSettingsData {
  brand: BrandSettings
  share: ShareSettings
  business: BusinessSettings
  /** 后端按「附件 ID + 更新时间」生成的带版本号 URL；未配置时为 null */
  logo_url: string | null
}

/** PUT 请求体：字段全部可选，未出现的键保持原值；logo_attachment_id 传 null 清除 Logo */
export interface SystemSettingsUpdatePayload {
  brand?: Partial<BrandSettings>
  share?: Partial<ShareSettings>
  business?: Partial<BusinessSettings>
}

export const settingsApi = {
  get: () => api.get('/settings') as Promise<ApiEnvelope<SystemSettingsData>>,
  update: (payload: SystemSettingsUpdatePayload) =>
    api.put('/settings', payload) as Promise<ApiEnvelope<SystemSettingsData>>,
}
