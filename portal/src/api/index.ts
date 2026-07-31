export type KnowledgeSource = {
  source_id: string
  source_type: 'document' | 'product' | 'database_fact'
  title: string
  product_id?: string | null
  document_id?: string | null
  chunk_id?: string | null
  page?: number | null
  section?: string | null
  quote?: string | null
  observed_at?: string | null
  access_policy?: string
  score?: number | null
  channel?: string | null
  open_url?: string | null
}

export type KnowledgeResponse = {
  trace_id: string
  session_id: string
  answer: string
  facts: Array<Record<string, unknown>>
  sources: KnowledgeSource[]
  products: Array<Record<string, unknown>>
  pending_actions: PendingAction[]
  confidence: string
  insufficient_sources: boolean
  usage: Record<string, unknown>
}

export type PendingAction = {
  id: string
  action_type: string
  status: string
  idempotency_key: string
  payload: Record<string, unknown>
  source_ids: string[]
  result?: Record<string, unknown> | null
  expires_at?: string | null
}

export type StreamEvent = {
  event: string
  data: Record<string, unknown>
}

type LoginEnvelope = {
  code: number
  data: {
    access_token: string
    refresh_token: string
  }
}

async function apiFetch<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const response = await fetch(path, { ...init, headers })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload?.detail?.msg || payload?.msg || '请求失败')
  }
  return payload as T
}

export async function login(username: string, password: string): Promise<LoginEnvelope> {
  return apiFetch<LoginEnvelope>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export async function refreshToken(refreshTokenValue: string): Promise<LoginEnvelope> {
  return apiFetch<LoginEnvelope>(
    `/api/v1/auth/refresh?refresh_token=${encodeURIComponent(refreshTokenValue)}`,
    { method: 'POST' },
  )
}

export async function runKnowledgeQuery(
  body: Record<string, unknown>,
  token: string,
): Promise<KnowledgeResponse> {
  const payload = await apiFetch<{ code: number; data: KnowledgeResponse }>(
    '/api/v1/knowledge/query',
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
    token,
  )
  return payload.data
}

export async function streamKnowledgeQuery(
  body: Record<string, unknown>,
  token: string,
  signal: AbortSignal,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const response = await fetch('/api/v1/knowledge/query', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload?.detail?.msg || '流式请求失败')
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''
    for (const frame of frames) {
      const lines = frame.split('\n')
      const event = lines.find((line) => line.startsWith('event: '))?.slice(7) || 'message'
      const dataLine = lines.find((line) => line.startsWith('data: '))?.slice(6) || '{}'
      onEvent({ event, data: JSON.parse(dataLine) })
    }
  }
}

/**
 * 首屏推荐产品。需要 `product:view` 权限，门户 viewer 拿不到时会 403；
 * 调用方要把失败当成「没有推荐」处理，退化成占位卡，不允许编造数据。
 */
export async function listProducts(
  token: string,
  size = 6,
): Promise<Array<Record<string, unknown>>> {
  const payload = await apiFetch<{ code: number; data: { list?: Array<Record<string, unknown>> } }>(
    `/api/v1/products?page=1&size=${encodeURIComponent(size)}`,
    { method: 'GET' },
    token,
  )
  return payload.data?.list || []
}

export async function getSource(sourceId: string, token: string): Promise<KnowledgeSource> {
  const payload = await apiFetch<{ code: number; data: KnowledgeSource }>(
    `/api/v1/knowledge/sources/${encodeURIComponent(sourceId)}`,
    { method: 'GET' },
    token,
  )
  return payload.data
}

export async function confirmPendingAction(action: PendingAction, token: string): Promise<PendingAction> {
  const payload = await apiFetch<{ code: number; data: PendingAction }>(
    `/api/v1/ai/actions/${encodeURIComponent(action.id)}/confirm`,
    {
      method: 'POST',
      body: JSON.stringify({ idempotency_key: action.idempotency_key }),
    },
    token,
  )
  return payload.data
}

/* ===== 公开分享（/share/:token）===== */

export type ShareSceneImage = {
  id?: string
  name?: string | null
  image_url?: string | null
  sort?: number | null
}

export type ShareProductItem = {
  product_id?: string
  product_no?: string | null
  product_name?: string | null
  face_price?: number | null
  quantity?: number
  line_total?: number | null
  unit_price?: number | null
  tax_rate?: number | null
  subtotal?: number | null
  cover_image_url?: string | null
  scene_images?: ShareSceneImage[]
}

export type ShareProposalContent = {
  proposal_no?: string | null
  proposal_name?: string | null
  customer_name?: string | null
  status?: string | null
  total_face_value?: number | null
  items?: ShareProductItem[]
}

export type ShareQuotationContent = {
  quotation_no?: string | null
  status?: string | null
  total_amount?: number | null
  items?: ShareProductItem[]
}

export type ShareEnvelopeData = {
  share_type: 'proposal' | 'quotation'
  target_id: string
  access_count: number
  content: ShareProposalContent | ShareQuotationContent | null
}

/**
 * 分享访问失败时后端返回 `detail: {code, msg}`（见 backend/app/api/v1/share_token.py）：
 *   40304 需要/错误的访问密码、40301 已失效、40302 已过期、
 *   40303 访问次数用完、40401 分享不存在。
 * 页面要按 code 区分「输密码」和「彻底失效」两种形态，所以这里把 code 一起抛出来，
 * 不能像 apiFetch 那样只留一句 message。
 */
export class ShareAccessError extends Error {
  readonly code: number
  constructor(code: number, message: string) {
    super(message)
    this.name = 'ShareAccessError'
    this.code = code
  }
}

/** 公开分享内容。故意不带 Authorization：这是唯一豁免后台鉴权的接口。 */
export async function getShareContent(
  token: string,
  password?: string,
): Promise<ShareEnvelopeData> {
  const query = password ? `?password=${encodeURIComponent(password)}` : ''
  const response = await fetch(`/api/v1/share/${encodeURIComponent(token)}${query}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = (payload as { detail?: { code?: number; msg?: string } })?.detail
    throw new ShareAccessError(detail?.code ?? response.status, detail?.msg || '分享链接无效或已过期')
  }
  const data = (payload as { data?: ShareEnvelopeData })?.data
  if (!data) throw new ShareAccessError(0, '分享内容为空')
  return data
}

