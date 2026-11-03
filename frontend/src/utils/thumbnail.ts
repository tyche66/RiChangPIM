/**
 * 媒体地址缩略图工具。
 *
 * 后端 `/api/v1/files/{id}/content?token=...` 支持 `w` 参数（白名单
 * 96/192/240/480/960），按需生成缩略图。网格/卡片里必须用缩略图：
 * 真实数据里存在 17MB 级平面图原图，浏览器按原尺寸解码会直接把内存打爆
 * （表现为页面「Out of memory」崩溃）。全屏查看器仍用原图地址。
 */

export const TABLE_THUMB_WIDTH = 192
export const TILE_THUMB_WIDTH = 480

export function withThumbWidth(url: string | null | undefined, width: number): string {
  if (!url) return ''
  return `${url}${url.includes('?') ? '&' : '?'}w=${width}`
}
