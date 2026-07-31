/**
 * 北京时间（UTC+8）24 小时制的展示与筛选换算。
 *
 * 后端所有时间列都是 SQLAlchemy `DateTime(timezone=True)`（PostgreSQL timestamptz，
 * 库里存 UTC），pydantic 序列化出来形如 '2026-07-31T08:14:13.228999Z'。
 * 直接把这串里的 'T' 换成空格贴给用户，等于把 UTC 当本地时间显示 —— 比北京时间
 * 慢 8 小时（操作日志页曾经就是这么错的）。
 *
 * 中国自 1991 年起不再实行夏令时，Asia/Shanghai 恒为 UTC+8，所以筛选方向可以直接
 * 用固定偏移换算；展示方向仍走 Intl + IANA 时区，不自己做日期进位。
 */
const BEIJING_TIME_ZONE = 'Asia/Shanghai'
const BEIJING_OFFSET_MS = 8 * 60 * 60 * 1000

// 用 formatToParts 自己拼串而不是 toLocaleString：各引擎对 zh-CN + hour12:false
// 的默认 hourCycle 不一致（会出现「2026/7/31 24:00:00」或「下午4:14」），
// 而 parts 的字段名是稳定的，拼出来固定是 YYYY-MM-DD HH:mm:ss。
const beijingTimeFormatter = new Intl.DateTimeFormat('en-US', {
  timeZone: BEIJING_TIME_ZONE,
  hourCycle: 'h23',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})

/** UTC 瞬时 → 'YYYY-MM-DD HH:mm:ss'（北京时间，24 小时制）。 */
export function formatBeijingTime(value: unknown): string {
  if (value === null || value === undefined || value === '') return ''
  const raw = String(value)
  // 万一后端某天回了不带时区标记的值，按 UTC 解析（列本身是 timestamptz），
  // 否则 new Date() 会按浏览器所在时区解释，换台机器结果就不一样。
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/.test(raw) ? raw : `${raw.replace(' ', 'T')}Z`
  const date = new Date(normalized)
  // 解析不出来就原样回显，不编造时间。
  if (Number.isNaN(date.getTime())) return raw
  const parts: Record<string, string> = {}
  for (const part of beijingTimeFormatter.formatToParts(date)) parts[part.type] = part.value
  // 兜掉极少数引擎忽略 hourCycle 时把 0 点给成 '24' 的情况。
  const hour = parts.hour === '24' ? '00' : parts.hour
  return `${parts.year}-${parts.month}-${parts.day} ${hour}:${parts.minute}:${parts.second}`
}

/**
 * 筛选框里的北京时间字面量 → UTC 瞬时（…Z）。
 *
 * el-date-picker 给的是不带时区的 'YYYY-MM-DDTHH:mm:ss'，用户按上面的展示口径填的
 * 是北京时间。原样发出去会被 FastAPI 解析成 naive datetime（见
 * backend/app/api/v1/audit.py，它直接拿这个值和 timestamptz 列比较），时区取决于
 * 服务端环境（容器默认 UTC）→ 筛出来的区间比用户想要的偏 8 小时。
 * 认不出的格式原样返回，让后端去报错，而不是在这里猜一个时间。
 */
export function beijingLocalToInstant(value: string): string {
  const matched = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?$/.exec(value.trim())
  if (!matched) return value
  const [, year, month, day, hour, minute, second] = matched
  const utcMs =
    Date.UTC(
      Number(year),
      Number(month) - 1,
      Number(day),
      Number(hour),
      Number(minute),
      Number(second || 0),
    ) - BEIJING_OFFSET_MS
  return new Date(utcMs).toISOString()
}
