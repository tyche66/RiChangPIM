/**
 * CRM / 内容域的枚举与中文映射集中地（HLD §12.3：禁止散落字符串）。
 *
 * 状态机允许的迁移与「是否需要 reason」也在这里以纯函数给出，
 * 与后端 services/{customer,project}_state.py 的字典表保持一致；
 * 前端只做按钮/提示的门控，最终合法性仍以后端校验为准。
 */

export const STAGE_MAP: Record<string, string> = {
  lead: '线索',
  contacted: '已联系',
  needs: '需求确认',
  quoted: '已报价',
  won: '成交',
  lost: '流失',
}

/** 客户漏斗顺序（won 为终态，lost 为旁支，不在此列）。 */
export const CUSTOMER_STAGE_ORDER = ['lead', 'contacted', 'needs', 'quoted', 'won']

/** 客户阶段允许的迁移（对齐 customer_state.TRANSITIONS）。 */
export const CUSTOMER_STAGE_TRANSITIONS: Record<string, string[]> = {
  lead: ['contacted', 'needs', 'quoted', 'lost'],
  contacted: ['needs', 'quoted', 'lost', 'lead'],
  needs: ['quoted', 'won', 'lost', 'contacted', 'lead'],
  quoted: ['won', 'lost', 'needs', 'contacted', 'lead'],
  won: [],
  lost: ['contacted'],
}

/** 客户回退/reopen 必须带 reason（对齐 customer_state.BACKWARD_TRANSITIONS）。 */
export function customerTransitionNeedsReason(from: string, to: string): boolean {
  const backward = new Set([
    'contacted|lead',
    'needs|contacted',
    'needs|lead',
    'quoted|needs',
    'quoted|contacted',
    'quoted|lead',
    'lost|contacted',
  ])
  return backward.has(`${from}|${to}`)
}

export const CUSTOMER_SOURCE_MAP: Record<string, string> = {
  new_media: '新媒体',
  store: '门店',
  referral: '转介绍',
  exhibition: '展会',
  other: '其他',
}

export const CUSTOMER_LEVEL_MAP: Record<string, string> = {
  A: 'A（高意向）',
  B: 'B（中意向）',
  C: 'C（低意向）',
}

export const PROJECT_STAGE_MAP: Record<string, string> = {
  lead: '线索',
  measuring: '测量',
  design: '设计',
  quoted: '报价',
  producing: '生产',
  delivered: '交付',
  closed: '完成',
  cancelled: '已取消',
}

/** 项目阶段顺序（cancelled 为旁支终态）。 */
export const PROJECT_STAGE_ORDER = [
  'lead',
  'measuring',
  'design',
  'quoted',
  'producing',
  'delivered',
  'closed',
]

export const PROJECT_TERMINAL_STAGES = ['closed', 'cancelled']

/** 项目阶段允许的迁移：前进（含跳跃）、回退一格、任意非终态 → cancelled。 */
export function projectAllowedTransitions(from: string): string[] {
  if (PROJECT_TERMINAL_STAGES.includes(from)) return []
  const idx = PROJECT_STAGE_ORDER.indexOf(from)
  if (idx < 0) return []
  const out: string[] = []
  for (let i = idx + 1; i < PROJECT_STAGE_ORDER.length; i += 1) {
    out.push(PROJECT_STAGE_ORDER[i])
  }
  if (idx - 1 >= 0) out.push(PROJECT_STAGE_ORDER[idx - 1])
  out.push('cancelled')
  return out
}

/** 项目回退一格 / 取消必须带 reason（对齐 project_state.validate_transition）。 */
export function projectTransitionNeedsReason(from: string, to: string): boolean {
  if (to === 'cancelled') return true
  const fi = PROJECT_STAGE_ORDER.indexOf(from)
  const ti = PROJECT_STAGE_ORDER.indexOf(to)
  if (fi < 0 || ti < 0) return false
  return ti < fi
}

export const PROJECT_STATUS_MAP: Record<string, string> = {
  active: '进行中',
  paused: '已暂停',
  done: '已完成',
  cancelled: '已取消',
}

export const PROJECT_TYPE_MAP: Record<string, string> = {
  whole_house: '整装',
  kitchen: '橱柜',
  wardrobe: '衣柜',
  other: '其他',
}

export const DIALOGUE_CHANNEL_MAP: Record<string, string> = {
  wechat: '微信',
  phone: '电话',
  visit: '到店',
  offline: '线下',
  other: '其他',
}

export const DIALOGUE_DIRECTION_MAP: Record<string, string> = {
  in: '客户→我方',
  out: '我方→客户',
}

export const FOLLOW_UP_METHOD_MAP: Record<string, string> = {
  wechat: '微信',
  phone: '电话',
  visit: '到店',
  other: '其他',
}

export const MEMBER_ROLE_MAP: Record<string, string> = {
  sales: '销售',
  designer: '设计师',
  pm: '项目经理',
  other: '其他',
}

export const ASSET_CATEGORY_MAP: Record<string, string> = {
  design_drawing: '设计图',
  drawing: '图纸',
  render: '效果图',
  contract: '合同',
  photo: '现场照片',
  other: '其他',
}

export const ASSET_STATUS_MAP: Record<string, string> = {
  draft: '待审核',
  approved: '已通过',
  obsolete: '已作废',
}

export const CONTENT_STATUS_MAP: Record<string, string> = {
  draft: '草稿',
  adopted: '已采纳',
  rejected: '未采纳',
  produced: '已制作',
  published: '已发布',
}

/** 派生展示态（published 后由服务端判定）。 */
export const CONTENT_DISPLAY_STATE_MAP: Record<string, string> = {
  ...CONTENT_STATUS_MAP,
  tracking: '跟踪中',
  closed: '已结束',
}

export const CONTENT_PLATFORM_MAP: Record<string, string> = {
  xhs: '小红书',
  douyin: '抖音',
  moments: '朋友圈',
  seo: 'SEO/官网',
  other: '其他',
}

export const CONTENT_TONE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'professional', label: '专业理性' },
  { value: 'warm', label: '温暖亲和' },
  { value: 'playful', label: '轻松活泼' },
  { value: 'premium', label: '高端质感' },
]

export const REMINDER_STATUS_MAP: Record<string, string> = {
  pending: '待触发',
  sent: '已发送',
  done: '已完成',
  snoozed: '已推迟',
  cancelled: '已取消',
  overdue: '已逾期',
}

export const REMINDER_RULE_MAP: Record<string, string> = {
  R1: '视频制作检查',
  R1b: '发布检查',
  R2: '曝光数据录入',
  R3: '客户跟进',
  E1: '升级提醒',
}

export const NOTIFICATION_KIND_MAP: Record<string, string> = {
  reminder: '提醒',
  escalation: '升级',
  system: '系统',
}

/** 通用取标签：未知键回退为原始值，避免界面出现空白。 */
export function labelOf(map: Record<string, string>, key: string | null | undefined): string {
  if (!key) return '-'
  return map[key] ?? key
}
