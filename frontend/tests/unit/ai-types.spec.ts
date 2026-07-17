import { describe, it, expect } from 'vitest'
import {
  tryParseJson,
  isRecommendDegraded,
  isPolishFailed,
} from '@/types/ai'
import type { RecommendResponse, PolishContent } from '@/types/ai'

describe('tryParseJson', () => {
  it('parses plain JSON strings', () => {
    const result = tryParseJson<PolishContent>('{"summary":"good","item_reasons":["r1"],"industry_phrases":["p1"]}')
    expect(result).not.toBeNull()
    expect(result!.summary).toBe('good')
    expect(result!.item_reasons).toEqual(['r1'])
    expect(result!.industry_phrases).toEqual(['p1'])
  })

  it('parses JSON wrapped in markdown code fences', () => {
    const raw = '```json\n{"summary":"ok"}\n```'
    const result = tryParseJson<PolishContent>(raw)
    expect(result).not.toBeNull()
    expect(result!.summary).toBe('ok')
  })

  it('parses JSON with plain text fences (no lang)', () => {
    const raw = '```\n{"summary":"ok"}\n```'
    const result = tryParseJson<PolishContent>(raw)
    expect(result).not.toBeNull()
    expect(result!.summary).toBe('ok')
  })

  it('returns null for null/undefined/empty input', () => {
    expect(tryParseJson(null)).toBeNull()
    expect(tryParseJson(undefined)).toBeNull()
    expect(tryParseJson('')).toBeNull()
  })

  it('returns null for invalid JSON', () => {
    expect(tryParseJson('{not json}')).toBeNull()
    expect(tryParseJson('hello world')).toBeNull()
  })
})

describe('isRecommendDegraded', () => {
  const base: RecommendResponse = {
    filters_applied: {},
    products: [],
    rationale: 'some rationale',
    total: 0,
  }

  it('returns false when filters and rationale are present', () => {
    const resp: RecommendResponse = {
      ...base,
      filters_applied: { category_id: 'uuid', max_face_price: 100 },
      rationale: '基于预算和品类筛选',
      total: 5,
    }
    expect(isRecommendDegraded(resp)).toBe(false)
  })

  it('returns true when rationale is empty', () => {
    const resp: RecommendResponse = {
      ...base,
      rationale: '',
    }
    expect(isRecommendDegraded(resp)).toBe(true)
  })

  it('returns true when rationale is the parse-failure sentinel', () => {
    const resp: RecommendResponse = {
      ...base,
      rationale: 'AI 解析失败',
    }
    expect(isRecommendDegraded(resp)).toBe(true)
  })

  it('returns true when filters are empty and rationale is empty', () => {
    expect(isRecommendDegraded(base)).toBe(true)
  })

  it('returns true when filters only contain null/empty values', () => {
    const resp: RecommendResponse = {
      ...base,
      filters_applied: { category_id: null, keywords: [] },
      rationale: 'some rationale',
    }
    expect(isRecommendDegraded(resp)).toBe(true)
  })

  it('returns false when at least one meaningful filter exists', () => {
    const resp: RecommendResponse = {
      ...base,
      filters_applied: { category_id: 'uuid', keywords: [] },
      rationale: 'some rationale',
    }
    expect(isRecommendDegraded(resp)).toBe(false)
  })
})

describe('isPolishFailed', () => {
  it('returns true for null/undefined/empty content', () => {
    expect(isPolishFailed(null)).toBe(true)
    expect(isPolishFailed(undefined)).toBe(true)
    expect(isPolishFailed('')).toBe(true)
  })

  it('returns true for invalid JSON content', () => {
    expect(isPolishFailed('not json')).toBe(true)
  })

  it('returns true when summary is empty and item_reasons is empty', () => {
    expect(isPolishFailed('{"summary":"","item_reasons":[],"industry_phrases":[]}')).toBe(true)
  })

  it('returns false when summary is present', () => {
    expect(isPolishFailed('{"summary":"great products","item_reasons":[],"industry_phrases":[]}')).toBe(false)
  })

  it('returns false when item_reasons has entries', () => {
    expect(isPolishFailed('{"summary":"","item_reasons":["reason1"],"industry_phrases":[]}')).toBe(false)
  })
})
