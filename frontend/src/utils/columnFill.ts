/**
 * 表格列宽的确定性填充算法（纯函数，不碰 DOM，所以能单测）。
 *
 * 为什么不用 Element Plus 自带的 fit：它把剩余宽度**平均**分给弹性列。产品列表 10 列的
 * 宽窄语义完全不同（产品名称要长、状态两个字就够），平均分的结果是名称被裁、状态列大片留白。
 * 而 `:fit="false"` + 写死列宽是另一种坏法：所有列宽之和是个常数，容器再宽也补不上，
 * 右侧留一大块白 —— 2K 屏上尤其明显，这是 2026-07-31 验收退回的那一条。
 *
 * 规则：每列给「最小宽 / 最大宽 / 弹性权重」，先按内容量出自然宽度，再把容器剩下的横向
 * 空间按权重分出去，谁先撞到 max 谁退出后续分配，四舍五入的零头全部记到锚列
 * （产品名称，max 不限）。只要 `container >= Σ min`，返回值就严格满足 `Σ 列宽 == container`。
 * 容器连 Σ min 都装不下时不再压缩，让表格横向滚动 —— 比把列压到看不清更诚实。
 */
export interface FillColumn {
  prop: string
  /** 按内容量出的期望宽度（含单元格左右内边距），会被 clamp 到 [min, max] */
  natural: number
  min: number
  /** 不限上限时传 Number.POSITIVE_INFINITY */
  max: number
  /** 剩余空间的分配权重；0 = 固定列，不参与伸缩 */
  grow: number
}

/** 亚像素残差小于这个值就认为分配完了，避免浮点尾数把循环拖满 */
const EPSILON = 0.5
/** 每轮至少让一列撞到 max/min 才会继续，列数远小于这个上限 */
const MAX_PASSES = 12

export function fillColumnWidths(
  columns: FillColumn[],
  container: number,
  anchorProp?: string,
): Record<string, number> {
  const widths = new Map<string, number>()
  for (const col of columns) {
    widths.set(col.prop, Math.min(Math.max(col.natural, col.min), col.max))
  }
  const total = () => columns.reduce((sum, col) => sum + widths.get(col.prop)!, 0)

  if (container > 0) {
    // 空间有余：按权重加宽，撞到 max 的列退出下一轮
    for (let pass = 0; pass < MAX_PASSES; pass++) {
      const rest = container - total()
      if (rest <= EPSILON) break
      const pool = columns.filter((col) => col.grow > 0 && widths.get(col.prop)! < col.max - EPSILON)
      if (!pool.length) break
      const grow = pool.reduce((sum, col) => sum + col.grow, 0)
      for (const col of pool) {
        widths.set(col.prop, Math.min(widths.get(col.prop)! + (rest * col.grow) / grow, col.max))
      }
    }
    // 空间不够：按权重收窄，撞到 min 的列退出下一轮
    for (let pass = 0; pass < MAX_PASSES; pass++) {
      const over = total() - container
      if (over <= EPSILON) break
      const pool = columns.filter((col) => col.grow > 0 && widths.get(col.prop)! > col.min + EPSILON)
      if (!pool.length) break
      const grow = pool.reduce((sum, col) => sum + col.grow, 0)
      for (const col of pool) {
        widths.set(col.prop, Math.max(widths.get(col.prop)! - (over * col.grow) / grow, col.min))
      }
    }
  }

  const result: Record<string, number> = {}
  for (const col of columns) result[col.prop] = Math.round(widths.get(col.prop)!)

  const anchor = anchorProp ? columns.find((col) => col.prop === anchorProp) : undefined
  const minTotal = columns.reduce((sum, col) => sum + col.min, 0)
  if (anchor && container > 0 && container >= minTotal) {
    const residue = container - columns.reduce((sum, col) => sum + result[col.prop], 0)
    if (residue !== 0) result[anchor.prop] = Math.max(result[anchor.prop] + residue, anchor.min)
  }
  return result
}
