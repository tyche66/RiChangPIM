/**
 * 展示层格式化工具。
 *
 * 原则：后端字段名、内部枚举和原始 ID 不直接暴露给使用者，
 * 统一在这里翻译成业务语言；缺失值统一表达为“资料未提供”，
 * 不用 0 / null / - 之类的占位值冒充真实数据。
 */

export const MISSING_TEXT = '资料未提供'

const SOURCE_TYPE_LABELS: Record<string, string> = {
  document: '文档资料',
  product: '产品数据',
  database_fact: '数据库事实',
}

export function sourceTypeLabel(sourceType?: string | null): string {
  if (!sourceType) return '来源'
  return SOURCE_TYPE_LABELS[sourceType] || sourceType
}

/** 比较表展示的属性行：行是属性、列是产品（见 AI-Docs/04 §3.2）。 */
export const COMPARE_FIELDS: Array<{ key: string; label: string }> = [
  { key: 'product_name', label: '产品名称' },
  { key: 'brand_name', label: '品牌' },
  { key: 'category_name', label: '类目' },
  { key: 'specification', label: '规格' },
  { key: 'material', label: '材质' },
  { key: 'colors', label: '颜色' },
]

const FIELD_LABELS: Record<string, string> = {
  ...Object.fromEntries(COMPARE_FIELDS.map((field) => [field.key, field.label])),
  product_no: '产品编号',
  face_price: '价格',
  stock_status: '库存状态',
  section: '章节',
  page: '页码',
  observed_at: '数据时点',
}

export function fieldLabel(key: string): string {
  return FIELD_LABELS[key] || key
}

/** 单元格文本：空字符串、null、undefined 与占位符 `-` 都视为资料缺失。 */
export function cellText(value: unknown): string {
  if (value === null || value === undefined) return MISSING_TEXT
  if (Array.isArray(value)) {
    const joined = value.filter((item) => item !== null && item !== undefined && item !== '').join('、')
    return joined || MISSING_TEXT
  }
  const text = String(value).trim()
  if (!text || text === '-' || text === 'null' || text === 'undefined') return MISSING_TEXT
  return text
}

/**
 * 价格展示。后端可能返回 99999 或“待核价”占位，
 * 前端禁止把占位值渲染成真实价格（见 AI-Docs/04 §3.1）。
 */
export function formatPrice(value: unknown): string {
  if (value === 99999 || value === '99999' || value === '待核价' || value === null || value === undefined) {
    return '待核价'
  }
  const price = Number(value)
  if (!Number.isFinite(price)) return String(value)
  return `¥${price.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`
}

export function formatStock(value: unknown): string {
  if (value === 'unknown' || value === null || value === undefined || value === '') return '库存待确认'
  return String(value)
}

/** 长 ID 只在技术信息里展示；界面上默认收敛成短码，避免占用注意力。 */
export function shortId(value?: string | null, keep = 8): string {
  if (!value) return ''
  const text = String(value)
  if (text.length <= keep + 3) return text
  return `${text.slice(0, keep)}…`
}

const PHASE_LABELS: Record<string, string> = {
  planning: '正在识别意图',
  retrieving: '正在检索产品资料',
  answering: '正在生成答案',
  acting: '正在准备待确认动作',
}

export function phaseLabel(name?: unknown, label?: unknown): string {
  const explicit = typeof label === 'string' ? label.trim() : ''
  if (explicit) return explicit
  const key = typeof name === 'string' ? name : ''
  return PHASE_LABELS[key] || '正在处理'
}

const CONFIDENCE_LABELS: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
}

export function confidenceLabel(value?: string | null): string {
  if (!value) return ''
  return CONFIDENCE_LABELS[value] || value
}

const ACTION_TYPE_LABELS: Record<string, string> = {
  'proposal.create_draft': '创建方案草稿',
  'proposal.update_draft': '更新方案草稿',
}

export function actionTypeLabel(actionType: string): string {
  return ACTION_TYPE_LABELS[actionType] || actionType
}

const ACTION_STATUS_LABELS: Record<string, string> = {
  proposed: '待确认',
  pending: '待确认',
  confirmed: '已确认',
  executing: '执行中',
  succeeded: '已完成',
  failed: '执行失败',
  cancelled: '已取消',
  expired: '已过期',
}

export function actionStatusLabel(status: string): string {
  return ACTION_STATUS_LABELS[status] || status
}

export function formatDateTime(value?: string | null): string {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return String(value)
  return parsed.toLocaleString('zh-CN', { hour12: false })
}

export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return ''
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(1)} 秒`
}

type TimelineInput = { event: string; data: Record<string, unknown> }

/**
 * 把 SSE 事件翻译成一句人能读懂的过程说明。
 * 返回 null 表示该事件不单独占一行（例如逐字增量）。
 */
export function eventSummary(item: TimelineInput): { label: string; detail: string } | null {
  const data = item.data || {}
  switch (item.event) {
    case 'meta':
      return { label: '会话已建立', detail: '' }
    case 'phase':
      return { label: phaseLabel(data.name, data.label), detail: '' }
    case 'answer_delta':
      return null
    case 'source':
      return { label: '引用来源', detail: `${sourceTypeLabel(data.source_type as string)} · ${String(data.title || '')}`.trim() }
    case 'products': {
      const items = Array.isArray(data.items) ? data.items.length : 0
      return { label: '返回候选产品', detail: `${items} 个` }
    }
    case 'pending_action':
      return { label: '生成待确认动作', detail: actionTypeLabel(String(data.type || data.action_type || '')) }
    case 'done': {
      const confidence = confidenceLabel(data.confidence as string)
      return { label: '生成完成', detail: confidence ? `置信度${confidence}` : '' }
    }
    case 'error':
      return { label: '出现错误', detail: String(data.message || data.code || '') }
    default:
      return { label: item.event, detail: '' }
  }
}
