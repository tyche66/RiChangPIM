/**
 * AI-related TypeScript types mirroring backend schemas.
 * These types describe the shape of AI API responses so views
 * can render rationale, filters, verification state, and
 * structured polish results without guessing field names.
 */

/** Product returned by the recommend endpoint. */
export interface RecommendProduct {
  id: string
  product_no: string
  product_name: string
  brand_id: string
  category_id: string
  face_price: number
  cost_price?: number
  supplier_id: string
  material?: string
  stock_status: string
  description?: string
  /** Backend may attach verification flag when AI has vetted the item. */
  _verified?: boolean
  /** Backend may attach the verifier identity (e.g. model name or user). */
  _verified_by?: string
}

/** Response from POST /ai/recommend. */
export interface RecommendResponse {
  status: 'success' | 'parse_failed' | 'degraded' | 'unknown'
  filters_applied: Record<string, unknown>
  products: RecommendProduct[]
  rationale: string
  total: number
  sources?: Array<{ product_name?: string; doc_title?: string; [k: string]: unknown }>
}

/** Parsed content from POST /ai/proposal/:id/polish. */
export interface PolishContent {
  summary: string
  item_reasons: string[]
  industry_phrases: string[]
}

/** Response from POST /ai/proposal/:id/polish. */
export interface PolishResponse {
  summary: string
  item_reasons: string[]
  industry_phrases: string[]
  proposal_id: string
  polished_at: string
}

/** Chat response from POST /ai/chat. */
export interface ChatResponse {
  answer: string
  sources: unknown[]
  tool_calls: unknown[]
  session_id: string | null
}

/**
 * Try to parse a JSON string that may be wrapped in markdown code fences.
 * Returns null on any parse failure so callers can surface a degraded state.
 */
export function tryParseJson<T>(raw: string | null | undefined): T | null {
  if (!raw) return null
  let text = raw.trim()
  const match = text.match(/```(?:json)?\s*([\s\S]*?)\s*```/)
  if (match) {
    text = match[1].trim()
  }
  try {
    return JSON.parse(text) as T
  } catch {
    return null
  }
}

/** True when the recommend response indicates the AI failed to parse the requirement. */
export function isRecommendDegraded(resp: RecommendResponse): boolean {
  if (resp.status === 'parse_failed' || resp.status === 'degraded') return true
  const filters = resp.filters_applied
  const hasFilters =
    filters &&
    Object.keys(filters).some((k) => {
      const v = filters[k]
      return v !== null && v !== undefined && v !== '' && (!Array.isArray(v) || v.length > 0)
    })
  const parseFailed = !resp.rationale || resp.rationale === 'AI 解析失败'
  return parseFailed || !hasFilters
}

/** True when polish content is missing or could not be parsed into structured data. */
export function isPolishFailed(content: string | null | undefined): boolean {
  const parsed = tryParseJson<PolishContent>(content)
  if (!parsed) return true
  return !parsed.summary && (!parsed.item_reasons || parsed.item_reasons.length === 0)
}
