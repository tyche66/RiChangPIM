/**
 * 把答案正文里的原始引用标记（例如 `[chunk:ba324332-3993-411b-ab6c-2a970725a3bc]`）
 * 转成脚注式角标，并与来源卡片建立对应关系。
 *
 * 原始 UUID 对使用者没有意义，但引用关系必须保留，
 * 所以这里只做“折叠展示”，不删除可追溯性。
 */

export type AnswerSegment =
  | { kind: 'text'; text: string }
  | { kind: 'citation'; index: number; sourceId: string | null; token: string }

export type CitationRef = {
  index: number
  sourceId: string | null
  token: string
}

export type CitableSource = { source_id: string }

const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i
const BRACKET_RE = /\[([^[\]\n]{6,160})\]/g

/** 只有“看起来像 ID”的方括号内容才被当作引用，避免误吃 [注意] 这类正文。 */
function looksLikeSourceToken(inner: string): boolean {
  const text = inner.trim()
  if (!text) return false
  if (UUID_RE.test(text)) return true
  return text.length >= 8 && /^[A-Za-z0-9_:.\-]+$/.test(text) && /\d/.test(text) && /[:_-]/.test(text)
}

function normalize(value: string): string {
  return value.trim().toLowerCase()
}

function resolveSourceId(token: string, sources: CitableSource[]): string | null {
  const target = normalize(token)
  for (const source of sources) {
    if (normalize(source.source_id) === target) return source.source_id
  }
  const uuid = token.match(UUID_RE)?.[0]?.toLowerCase()
  if (uuid) {
    for (const source of sources) {
      if (source.source_id.toLowerCase().includes(uuid)) return source.source_id
    }
  }
  for (const source of sources) {
    if (source.source_id && target.includes(normalize(source.source_id))) return source.source_id
  }
  return null
}

/** 流式输出时，末尾可能是半个引用标记，先藏起来避免闪烁。 */
function trimPartialToken(text: string): string {
  const opened = text.lastIndexOf('[')
  if (opened < 0) return text
  if (text.indexOf(']', opened) >= 0) return text
  if (text.length - opened > 180) return text
  return text.slice(0, opened)
}

export function buildAnswer(
  answer: string,
  sources: CitableSource[],
  streaming = false,
): { segments: AnswerSegment[]; citations: CitationRef[] } {
  const source = streaming ? trimPartialToken(answer || '') : answer || ''
  const segments: AnswerSegment[] = []
  const citations: CitationRef[] = []
  const seen = new Map<string, number>()

  let cursor = 0
  BRACKET_RE.lastIndex = 0
  let match = BRACKET_RE.exec(source)
  while (match) {
    const inner = match[1]
    if (looksLikeSourceToken(inner)) {
      if (match.index > cursor) {
        segments.push({ kind: 'text', text: source.slice(cursor, match.index) })
      }
      const token = inner.trim()
      const sourceId = resolveSourceId(token, sources)
      const key = sourceId ? `id:${normalize(sourceId)}` : `token:${normalize(token)}`
      let index = seen.get(key)
      if (!index) {
        index = seen.size + 1
        seen.set(key, index)
        citations.push({ index, sourceId, token })
      }
      segments.push({ kind: 'citation', index, sourceId, token })
      cursor = match.index + match[0].length
    }
    match = BRACKET_RE.exec(source)
  }
  if (cursor < source.length) {
    segments.push({ kind: 'text', text: source.slice(cursor) })
  }
  return { segments, citations }
}

/** 来源卡片上展示的脚注编号；未被引用的来源不显示编号。 */
export function citationIndexBySource(citations: CitationRef[]): Record<string, number> {
  const map: Record<string, number> = {}
  for (const citation of citations) {
    if (citation.sourceId && !map[citation.sourceId]) map[citation.sourceId] = citation.index
  }
  return map
}
