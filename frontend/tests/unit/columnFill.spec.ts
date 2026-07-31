import { describe, it, expect } from 'vitest'
import { fillColumnWidths, type FillColumn } from '@/utils/columnFill'

/**
 * 这些用例钉的是 2026-07-31 验收退回的那一条：2K 屏上表格右侧留白。
 * 核心不变式只有一个 —— 只要容器装得下所有 min，列宽之和必须**严格等于**容器宽度。
 */

const INF = Number.POSITIVE_INFINITY

/** 产品列表的真实列配置（和 Products.vue 的 COLUMNS 同一套数字，含图片列） */
function productColumns(natural: Partial<Record<string, number>> = {}): FillColumn[] {
  const spec: FillColumn[] = [
    { prop: 'image', natural: 80, min: 80, max: 80, grow: 0 },
    { prop: 'productNo', natural: 138, min: 110, max: 260, grow: 0.6 },
    { prop: 'productName', natural: 300, min: 180, max: INF, grow: 3 },
    { prop: 'brandName', natural: 100, min: 92, max: 220, grow: 0.7 },
    { prop: 'categoryName', natural: 130, min: 96, max: 240, grow: 0.7 },
    { prop: 'facePrice', natural: 112, min: 104, max: 180, grow: 0.5 },
    { prop: 'costPrice', natural: 116, min: 108, max: 180, grow: 0.5 },
    { prop: 'stockStatus', natural: 80, min: 76, max: 130, grow: 0.4 },
    { prop: 'status', natural: 76, min: 72, max: 130, grow: 0.4 },
    { prop: 'operation', natural: 132, min: 132, max: 200, grow: 0.6 },
  ]
  return spec.map((col) => (natural[col.prop] ? { ...col, natural: natural[col.prop]! } : col))
}

const sum = (widths: Record<string, number>) => Object.values(widths).reduce((a, b) => a + b, 0)

describe('fillColumnWidths', () => {
  // 1280 = 笔记本，1920 = 常见桌面，2560 = 图1 那台 2K，3840 = 4K
  for (const container of [1280, 1920, 2560, 3840]) {
    it(`fills the container exactly at ${container}px (no right-hand gap)`, () => {
      const widths = fillColumnWidths(productColumns(), container, 'productName')
      expect(sum(widths)).toBe(container)
    })
  }

  it('respects every min and max', () => {
    const cols = productColumns()
    for (const container of [900, 1280, 1920, 2560, 3840]) {
      const widths = fillColumnWidths(cols, container, 'productName')
      for (const col of cols) {
        expect(widths[col.prop]).toBeGreaterThanOrEqual(col.min)
        if (col.max !== INF) expect(widths[col.prop]).toBeLessThanOrEqual(col.max)
      }
    }
  })

  it('keeps fixed columns (grow: 0) at their exact width on any container', () => {
    for (const container of [1280, 2560, 3840]) {
      const widths = fillColumnWidths(productColumns(), container, 'productName')
      expect(widths.image).toBe(80)
    }
  })

  it('gives the surplus mostly to the anchor column, not evenly to everyone', () => {
    const narrow = fillColumnWidths(productColumns(), 1280, 'productName')
    const wide = fillColumnWidths(productColumns(), 2560, 'productName')
    const nameGain = wide.productName - narrow.productName
    const statusGain = wide.status - narrow.status
    // 这正是不用 Element Plus 自带 fit 的原因：它会把余量平均分掉
    expect(nameGain).toBeGreaterThan(statusGain * 5)
  })

  it('caps capped columns and lets the anchor absorb the rest on a 4K container', () => {
    const widths = fillColumnWidths(productColumns(), 3840, 'productName')
    expect(widths.status).toBe(130)
    expect(widths.stockStatus).toBe(130)
    expect(widths.facePrice).toBe(180)
    expect(widths.operation).toBe(200)
    expect(widths.productName).toBeGreaterThan(1000)
    expect(sum(widths)).toBe(3840)
  })

  it('never wraps 面价/成本价: their width stays above the measured natural width', () => {
    // ¥19340.00 在 mono 600 14px 下约 74px + 28px 内边距 ≈ 102px
    const widths = fillColumnWidths(productColumns({ facePrice: 112 }), 2560, 'productName')
    expect(widths.facePrice).toBeGreaterThanOrEqual(112)
  })

  it('shrinks toward min when the container is narrower than the natural total', () => {
    const cols = productColumns()
    const naturalTotal = cols.reduce((s, c) => s + c.natural, 0)
    const widths = fillColumnWidths(cols, naturalTotal - 200, 'productName')
    expect(sum(widths)).toBe(naturalTotal - 200)
    expect(widths.productName).toBeLessThan(300)
    expect(widths.productName).toBeGreaterThanOrEqual(180)
  })

  it('stops shrinking at Σmin and lets the table scroll instead of crushing columns', () => {
    const cols = productColumns()
    const minTotal = cols.reduce((s, c) => s + c.min, 0)
    const widths = fillColumnWidths(cols, minTotal - 400, 'productName')
    // 容器装不下 Σmin 时不再压缩：总宽 == Σmin，横向滚动
    expect(sum(widths)).toBe(minTotal)
    for (const col of cols) expect(widths[col.prop]).toBe(col.min)
  })

  it('treats a pinned (dragged) column as fixed and still fills the container', () => {
    const cols = productColumns().map((col) =>
      col.prop === 'categoryName' ? { ...col, natural: 320, min: 320, max: 320, grow: 0 } : col,
    )
    const widths = fillColumnWidths(cols, 2560, 'productName')
    expect(widths.categoryName).toBe(320)
    expect(sum(widths)).toBe(2560)
  })

  it('handles the proposal-mode selection column being added', () => {
    const cols: FillColumn[] = [
      { prop: 'selection', natural: 50, min: 50, max: 50, grow: 0 },
      ...productColumns(),
    ]
    const widths = fillColumnWidths(cols, 2560, 'productName')
    expect(widths.selection).toBe(50)
    expect(sum(widths)).toBe(2560)
  })

  it('handles the cost column being hidden for users without permission', () => {
    const cols = productColumns().filter((col) => col.prop !== 'costPrice')
    const widths = fillColumnWidths(cols, 2560, 'productName')
    expect(widths.costPrice).toBeUndefined()
    expect(sum(widths)).toBe(2560)
  })

  it('returns integers only (Element Plus writes them straight into style="width:…")', () => {
    const widths = fillColumnWidths(productColumns(), 2561, 'productName')
    for (const value of Object.values(widths)) expect(Number.isInteger(value)).toBe(true)
    expect(sum(widths)).toBe(2561)
  })

  it('falls back to clamped natural widths when the container is unknown (0)', () => {
    const widths = fillColumnWidths(productColumns(), 0, 'productName')
    expect(widths.productName).toBe(300)
    expect(widths.brandName).toBe(100)
  })

  it('does not need an anchor to work', () => {
    const widths = fillColumnWidths(productColumns(), 2560)
    // 没有锚列时零头无处安放，允许最多 1px/列 的取整误差，但不允许出现留白量级的缺口
    expect(Math.abs(sum(widths) - 2560)).toBeLessThan(10)
  })
})
