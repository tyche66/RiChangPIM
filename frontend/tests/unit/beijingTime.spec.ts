import { describe, it, expect } from 'vitest'
import { beijingLocalToInstant, formatBeijingTime } from '@/utils/beijingTime'

/**
 * 操作日志的时间口径：展示一律北京时间 24 小时制，筛选值反向换算成 UTC 瞬时。
 * 这两个方向必须互为逆运算，否则「筛出来的区间」和「看到的时间」对不上。
 */
describe('formatBeijingTime', () => {
  it('把带 Z 的 UTC 瞬时换算成北京时间（+8）', () => {
    expect(formatBeijingTime('2026-07-31T08:14:13.228999Z')).toBe('2026-07-31 16:14:13')
    expect(formatBeijingTime('2026-07-20T08:00:00Z')).toBe('2026-07-20 16:00:00')
  })

  it('跨日和零点用 00 表示，不出现 24', () => {
    expect(formatBeijingTime('2026-07-20T16:30:00Z')).toBe('2026-07-21 00:30:00')
    // UTC 16:00 正好是北京次日 00:00。
    expect(formatBeijingTime('2026-12-31T16:00:00Z')).toBe('2027-01-01 00:00:00')
    expect(formatBeijingTime('2026-07-20T15:59:59Z')).toBe('2026-07-20 23:59:59')
  })

  it('带显式偏移的值按该偏移解析', () => {
    // 同一瞬时的三种写法必须给出同一个北京时间。
    expect(formatBeijingTime('2026-07-20T16:00:00+08:00')).toBe('2026-07-20 16:00:00')
    expect(formatBeijingTime('2026-07-20T08:00:00+00:00')).toBe('2026-07-20 16:00:00')
    expect(formatBeijingTime('2026-07-20T04:00:00-04:00')).toBe('2026-07-20 16:00:00')
  })

  it('不带时区标记时按 UTC 解析，不跟随本机时区', () => {
    expect(formatBeijingTime('2026-07-20T10:00:00')).toBe('2026-07-20 18:00:00')
    // 后端若换成空格分隔也要认。
    expect(formatBeijingTime('2026-07-20 10:00:00')).toBe('2026-07-20 18:00:00')
  })

  it('空值给空串，解析不出来的原样回显（不编造时间）', () => {
    expect(formatBeijingTime(null)).toBe('')
    expect(formatBeijingTime(undefined)).toBe('')
    expect(formatBeijingTime('')).toBe('')
    expect(formatBeijingTime('not-a-time')).toBe('not-a-time')
  })
})

describe('beijingLocalToInstant', () => {
  it('把北京时间字面量换算成 UTC 瞬时', () => {
    expect(beijingLocalToInstant('2026-07-20T00:00:00')).toBe('2026-07-19T16:00:00.000Z')
    expect(beijingLocalToInstant('2026-07-20T16:00:00')).toBe('2026-07-20T08:00:00.000Z')
  })

  it('秒可省略，空格分隔也认', () => {
    expect(beijingLocalToInstant('2026-07-20T16:00')).toBe('2026-07-20T08:00:00.000Z')
    expect(beijingLocalToInstant('2026-07-20 16:00:00')).toBe('2026-07-20T08:00:00.000Z')
  })

  it('认不出的格式原样返回，交给后端报错', () => {
    expect(beijingLocalToInstant('2026/07/20 16:00')).toBe('2026/07/20 16:00')
    expect(beijingLocalToInstant('')).toBe('')
  })

  it('和展示方向互为逆运算', () => {
    const shown = '2026-07-31 16:14:13'
    const instant = beijingLocalToInstant(shown.replace(' ', 'T'))
    expect(formatBeijingTime(instant)).toBe(shown)
  })
})
