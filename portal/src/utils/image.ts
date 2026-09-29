/**
 * 产品图片地址统一处理。
 *
 * 门户会消费两种结构完全不同的产品数据：
 * 1. AI 知识查询返回的候选产品（backend/app/knowledge/tools/product.py
 *    的 `_product_card`）——只有一个 `cover_image_url`，而且只在产品
 *    **显式设了主图**（`ProductImage.is_cover`）时才有值。
 * 2. 首屏推荐产品（backend/app/api/v1/products.py 的列表响应）——除
 *    `cover_image_url` 外还带完整的 `images[].file_url`。
 *
 * 所以这里按优先级做字段兼容：主图拿不到就退回第一张产品图，再拿不到
 * 才交给占位。任何情况下都不允许把 `undefined` / `null` / 空字符串塞进
 * `<img src>`——那正是 broken image 图标的来源。
 */

/** 只有这些协议的地址才允许出现在 `<img src>` 里。 */
const SAFE_PROTOCOLS = ['http:', 'https:', 'blob:']

/**
 * 按优先级尝试的字段。`cover_image_url` 是后端两处接口的正式字段，
 * 其余是历史接口/外部数据源的别名，做兼容用。
 */
const IMAGE_FIELDS = [
  'cover_image_url',
  'coverUrl',
  'cover_url',
  'image_url',
  'imageUrl',
  'cover_image',
  'cover',
  'main_image_url',
  'thumbnail_url',
  'thumbnailUrl',
  'thumbnail',
  'pic_url',
  'img_url',
] as const

/** 图片数组里每个元素可能长成的样子。 */
type ImageLike = Record<string, unknown>

function firstString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === 'string') {
      const text = value.trim()
      if (text) return text
    }
  }
  return null
}

/** 递归地从「字符串 / 字符串数组 / 对象 / 对象数组」里取出第一个可用的地址。 */
function collect(value: unknown, depth = 0): string[] {
  if (depth > 3 || value === null || value === undefined) return []
  if (typeof value === 'string') {
    const text = value.trim()
    return text ? [text] : []
  }
  if (Array.isArray(value)) return value.flatMap((item) => collect(item, depth + 1))
  if (typeof value === 'object') {
    const record = value as ImageLike
    return [
      ...firstStringAll(record.file_url, record.fileUrl, record.url, record.image_url, record.imageUrl, record.src),
    ]
  }
  return []
}

function firstStringAll(...values: unknown[]): string[] {
  const text = firstString(...values)
  return text ? [text] : []
}

/**
 * 归一化单条地址：
 * - `//host/x` 协议相对地址、`/api/...` 站内相对地址、`http(s)://` 绝对地址放行；
 * - `data:` 只放行 `image/*`；
 * - `javascript:` / `vbscript:` / `file:` 一律判死（返回 null）。
 */
export function normalizeImageUrl(raw: unknown): string | null {
  const url = firstString(raw)
  if (!url) return null
  if (url.startsWith('//')) return url
  if (/^data:/i.test(url)) return /^data:image\//i.test(url) ? url : null
  const scheme = /^([a-z][a-z0-9+.\-]*):/i.exec(url)
  if (scheme) {
    return SAFE_PROTOCOLS.includes(`${scheme[1].toLowerCase()}:`) ? url : null
  }
  return url
}

/** 从一条产品数据里解析出可用的图片地址；解析不到返回 null。 */
export function resolveImageUrl(product: Record<string, unknown> | null | undefined): string | null {
  if (!product) return null
  const candidates: string[] = []
  for (const field of IMAGE_FIELDS) {
    candidates.push(...collect(product[field]))
  }
  // images 里可能同时存在主图和非主图，兜底时按顺序取第一张。
  candidates.push(...collect(product.images))
  candidates.push(...collect(product.scene_images))
  for (const candidate of candidates) {
    const normalized = normalizeImageUrl(candidate)
    if (normalized) return normalized
  }
  return null
}

