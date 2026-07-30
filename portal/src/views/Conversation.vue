<script setup lang="ts">
/**
 * 查询工作台。
 *
 * 展示原则：
 * 1. 用户先看答案、产品和来源；追踪 ID、SSE 原始事件、token 用量这些
 *    对使用者没有意义的内容统一折进「技术详情」，默认收起。
 * 2. 后端枚举、字段名和占位值一律经 utils/format 翻译，不直接渲染。
 * 3. 正文里的 [chunk:uuid] 由 utils/citations 折成脚注角标，引用关系不丢。
 */
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  confirmPendingAction,
  getSource,
  runKnowledgeQuery,
  streamKnowledgeQuery,
  type KnowledgeResponse,
  type KnowledgeSource,
  type PendingAction,
  type StreamEvent,
} from '@/api'
import AnswerBody from '@/components/AnswerBody.vue'
import AppHeader from '@/components/AppHeader.vue'
import ChatInput from '@/components/ChatInput.vue'
import CollapseSection from '@/components/CollapseSection.vue'
import CompareTable from '@/components/CompareTable.vue'
import EventStream from '@/components/EventStream.vue'
import PendingActionCard from '@/components/PendingActionCard.vue'
import ProductCard from '@/components/ProductCard.vue'
import SourceCard from '@/components/SourceCard.vue'
import SourceDialog from '@/components/SourceDialog.vue'
import { useAuthStore } from '@/stores/auth'
import { buildAnswer, citationIndexBySource } from '@/utils/citations'
import { confidenceLabel, formatDuration, phaseLabel, shortId } from '@/utils/format'

const RESULT_STATUS_LABELS: Record<string, string> = {
  completed: '已完成',
  partial: '部分完成',
  cancelled: '已取消',
  failed: '失败',
}

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const busy = ref(false)
const error = ref('')
const notice = ref('')
const answer = ref('')
const lastQuery = ref('')
const phaseText = ref('')
const products = ref<Array<Record<string, unknown>>>([])
const sources = ref<KnowledgeSource[]>([])
const pendingActions = ref<PendingAction[]>([])
const events = ref<StreamEvent[]>([])
const traceId = ref('')
const sessionId = ref('')
const resultStatus = ref('')
const confidence = ref('')
const usage = ref<Record<string, unknown>>({})
const insufficient = ref(false)
const elapsedMs = ref(0)
const activeSource = ref<KnowledgeSource | null>(null)
const copied = ref(false)
const controller = ref<AbortController | null>(null)
const resultsEl = ref<HTMLElement | null>(null)

const rendered = computed(() => buildAnswer(answer.value, sources.value, busy.value))
const segments = computed(() => rendered.value.segments)
const citationIndex = computed(() => citationIndexBySource(rendered.value.citations))
const confidenceText = computed(() => confidenceLabel(confidence.value))
const statusText = computed(() => phaseText.value || '正在处理')
const hasResults = computed(() =>
  Boolean(
    answer.value ||
      products.value.length ||
      sources.value.length ||
      pendingActions.value.length ||
      error.value,
  ),
)
const started = computed(() => busy.value || hasResults.value || Boolean(lastQuery.value))

const usageText = computed(() => {
  const total = usage.value.total_tokens ?? usage.value.total
  if (total !== null && total !== undefined) return `${total} tokens`
  return Object.keys(usage.value).length ? JSON.stringify(usage.value) : ''
})

const techRows = computed<Array<[string, string]>>(() => {
  const rows: Array<[string, string]> = []
  if (resultStatus.value) rows.push(['结果状态', RESULT_STATUS_LABELS[resultStatus.value] || resultStatus.value])
  if (confidenceText.value) rows.push(['置信度', confidenceText.value])
  const elapsed = formatDuration(elapsedMs.value)
  if (elapsed) rows.push(['用时', elapsed])
  if (usageText.value) rows.push(['模型用量', usageText.value])
  if (sessionId.value) rows.push(['会话编号', shortId(sessionId.value, 14)])
  if (traceId.value) rows.push(['追踪编号', shortId(traceId.value, 14)])
  return rows
})
const techHint = computed(() => `${events.value.length} 条过程事件`)
function clearResults() {
  error.value = ''
  notice.value = ''
  answer.value = ''
  phaseText.value = ''
  products.value = []
  sources.value = []
  pendingActions.value = []
  events.value = []
  traceId.value = ''
  sessionId.value = ''
  resultStatus.value = ''
  confidence.value = ''
  usage.value = {}
  insufficient.value = false
  elapsedMs.value = 0
  activeSource.value = null
}

function reset() {
  clearResults()
  lastQuery.value = ''
}

function isAbortError(value: unknown): boolean {
  return value instanceof Error && value.name === 'AbortError'
}

function applyResponse(response: KnowledgeResponse) {
  answer.value = response.answer
  products.value = response.products
  sources.value = response.sources
  pendingActions.value = response.pending_actions
  traceId.value = response.trace_id
  sessionId.value = response.session_id
  confidence.value = response.confidence
  insufficient.value = response.insufficient_sources
  usage.value = response.usage || {}
  resultStatus.value = resultStatus.value || 'completed'
}
function handleEvent(event: StreamEvent) {
  events.value.push(event)
  const data = event.data || {}
  switch (event.event) {
    case 'meta':
      traceId.value = String(data.trace_id || '')
      sessionId.value = String(data.session_id || '')
      break
    case 'phase':
      phaseText.value = phaseLabel(data.name, data.label)
      break
    case 'answer_delta':
      answer.value += String(data.text || '')
      break
    case 'source':
      sources.value.push(data as unknown as KnowledgeSource)
      break
    case 'products':
      products.value = (data.items as Array<Record<string, unknown>>) || []
      break
    case 'pending_action':
      pendingActions.value.push(data as unknown as PendingAction)
      break
    case 'done':
      resultStatus.value = String(data.status || 'completed')
      confidence.value = String(data.confidence || '')
      usage.value = (data.usage as Record<string, unknown>) || {}
      insufficient.value = Boolean(data.insufficient_sources)
      break
    case 'error':
      error.value = String(data.message || data.code || '生成过程出现错误')
      break
    default:
      break
  }
}

async function scrollToResults() {
  await nextTick()
  const el = resultsEl.value
  if (!el) return
  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  el.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' })
}
async function submit(message: string) {
  const token = await auth.ensureToken()
  if (!token) {
    error.value = '登录状态已失效，请重新登录后再查询。'
    return
  }
  clearResults()
  lastQuery.value = message
  phaseText.value = '正在识别意图'
  busy.value = true
  const startedAt = Date.now()
  controller.value = new AbortController()
  void scrollToResults()
  try {
    let streamFailure: unknown = null
    try {
      await streamKnowledgeQuery(
        { message, capabilities: { stream: true, supports_actions: true } },
        token,
        controller.value.signal,
        handleEvent,
      )
    } catch (exc) {
      // 已经收到事件就说明流式是通的，这时的失败不该再退回一次性查询。
      if (isAbortError(exc) || events.value.length) throw exc
      streamFailure = exc
    }
    if (!events.value.length) {
      try {
        const response = await runKnowledgeQuery(
          { message, capabilities: { stream: false, supports_actions: true } },
          token,
        )
        applyResponse(response)
      } catch (exc) {
        throw streamFailure || exc
      }
    }
  } catch (exc) {
    if (isAbortError(exc)) notice.value = '已停止生成，下面是已经收到的内容。'
    else error.value = exc instanceof Error ? exc.message : '请求失败'
  } finally {
    busy.value = false
    elapsedMs.value = Date.now() - startedAt
    controller.value = null
  }
}

function stop() {
  controller.value?.abort()
}
async function copyAnswer() {
  const text = segments.value
    .map((segment) => (segment.kind === 'text' ? segment.text : `[${segment.index}]`))
    .join('')
  if (!text.trim()) return
  try {
    await navigator.clipboard.writeText(text)
    copied.value = true
    window.setTimeout(() => { copied.value = false }, 2000)
  } catch {
    notice.value = '浏览器拒绝了剪贴板访问，请手动选中正文复制。'
  }
}

async function openSource(sourceId: string) {
  const token = await auth.ensureToken()
  if (!token) {
    error.value = '登录状态已失效，请重新登录。'
    return
  }
  try {
    activeSource.value = await getSource(sourceId, token)
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '无法打开来源'
  }
}

function productDetailUrl(product: Record<string, unknown>) {
  const productId = String(product.id || '')
  if (!productId) return '/admin/login'
  const detailPath = `/products/${encodeURIComponent(productId)}`
  const canViewProduct = auth.roleCode === 'admin' || auth.permissions.includes('product:view')
  if (canViewProduct) return `/admin${detailPath}`
  return `/admin/login?redirect=${encodeURIComponent(detailPath)}`
}

async function confirmAction(action: PendingAction) {
  const token = await auth.ensureToken()
  if (!token) return
  busy.value = true
  error.value = ''
  try {
    const confirmed = await confirmPendingAction(action, token)
    pendingActions.value = pendingActions.value.map((item) => (item.id === confirmed.id ? confirmed : item))
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '确认失败'
  } finally {
    busy.value = false
  }
}

function signOut() {
  auth.clear()
  void router.push('/')
}

onMounted(() => {
  const initial = route.query.q
  if (typeof initial === 'string' && initial) void submit(initial)
})
</script>

<template>
  <AppHeader>
    <button v-if="started" type="button" class="button button--secondary button--small" @click="reset">清空结果</button>
    <button type="button" class="button button--ghost button--small" @click="signOut">退出</button>
  </AppHeader>

  <main class="chat-shell">
    <section v-if="!started" class="chat-intro">
      <h1>把产品、资料和质量记录放到同一个查询入口。</h1>
      <p>输入型号、场景、材质、预算或对比需求，AI 会返回答案、候选产品、引用来源和需要确认的动作。</p>
    </section>

    <div class="composer-wrap">
      <ChatInput :busy="busy" @submit="submit" @stop="stop" />
    </div>
    <section v-if="started" ref="resultsEl" class="workspace" aria-label="查询结果">
      <p v-if="lastQuery" class="query-echo">
        <span>本次查询</span>
        <strong>{{ lastQuery }}</strong>
      </p>

      <article class="panel panel--answer">
        <div class="panel__header">
          <div class="panel__title">
            <h2>回答</h2>
            <span v-if="confidenceText" class="status-pill">置信度{{ confidenceText }}</span>
          </div>
          <div class="panel__tools">
            <button
              v-if="answer && !busy"
              type="button"
              class="button button--ghost button--small"
              @click="copyAnswer"
            >
              {{ copied ? '已复制' : '复制答案' }}
            </button>
          </div>
        </div>
        <p v-if="busy" class="status-line" aria-live="polite">
          <span class="spinner" aria-hidden="true" />
          <span>{{ statusText }}</span>
        </p>
        <AnswerBody
          v-if="segments.length || !busy"
          :segments="segments"
          placeholder="这次查询没有生成答案，可以换个更具体的说法再试一次。"
          @open="openSource"
        />
        <p v-if="insufficient" class="notice notice--warn">
          可用资料不足，答案只覆盖了能被来源支持的部分，请结合下方来源自行确认。
        </p>
        <p v-if="notice" class="notice">{{ notice }}</p>
        <p v-if="error" class="notice notice--error">{{ error }}</p>
      </article>
      <section v-if="pendingActions.length" class="stack" aria-label="待确认动作">
        <PendingActionCard
          v-for="action in pendingActions"
          :key="action.id"
          :action="action"
          :busy="busy"
          @confirm="confirmAction"
        />
      </section>

      <CompareTable :products="products" class="workspace__wide" />

      <template v-if="products.length">
        <div class="section-head workspace__wide">
          <h2>候选产品</h2>
          <span class="section-head__count">{{ products.length }} 个</span>
        </div>
        <section class="card-list product-grid workspace__wide" aria-label="产品结果">
          <ProductCard
            v-for="item in products"
            :key="String(item.id || item.product_no)"
            :product="item"
            :detail-url="productDetailUrl(item)"
          />
        </section>
      </template>

      <template v-if="sources.length">
        <div class="section-head">
          <h2>引用来源</h2>
          <span class="section-head__count">{{ sources.length }} 条</span>
        </div>
        <section class="card-list source-list" aria-label="引用来源">
          <SourceCard
            v-for="source in sources"
            :key="source.source_id"
            :source="source"
            :index="citationIndex[source.source_id] || 0"
            @open="openSource"
          />
        </section>
      </template>

      <CollapseSection v-if="events.length || techRows.length" title="技术详情" :hint="techHint">
        <div v-if="techRows.length" class="kv-grid">
          <template v-for="row in techRows" :key="row[0]">
            <span>{{ row[0] }}</span>
            <strong>{{ row[1] }}</strong>
          </template>
        </div>
        <EventStream v-if="events.length" :events="events" :busy="busy" />
      </CollapseSection>
    </section>
    <SourceDialog :source="activeSource" @close="activeSource = null" />

  </main>
</template>
