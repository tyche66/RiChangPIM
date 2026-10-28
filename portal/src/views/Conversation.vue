<script setup lang="ts">
/**
 * 查询工作台。
 *
 * 版式参考 reeoo.com 首屏：巨号标题 + 胶囊输入 + 扇形铺开的卡片堆 +
 * 一条能力入口，回答、动作、比较表、来源、技术详情全部放在首屏下方，
 * 向下滚动逐段淡入。
 *
 * 展示原则：
 * 1. 用户先看答案、产品和来源；追踪 ID、SSE 原始事件、token 用量这些
 *    对使用者没有意义的内容统一折进「技术详情」，默认收起。
 * 2. 后端枚举、字段名和占位值一律经 utils/format 翻译，不直接渲染。
 * 3. 正文里的 [chunk:uuid] 由 utils/citations 折成脚注角标，引用关系不丢。
 * 4. 卡片堆始终是叠卡（最多 5 张），结果超过 5 张时在卡堆内用滚轮循环
 *    翻页，页面主体不跟滚；未查询时放推荐产品，取不到推荐（门户 viewer
 *    没有 product:view）就退化成空白占位卡，**不编造数据**。
 * 5. 查询后不自动滚动，改用卡片下方的「向下查看回答」提示，滚动由用户决定。
 * 6. 答案正文是 AI 生成的 Markdown，由 utils/markdown 渲染成可视元素；
 *    该模块对输入先做 HTML 转义再只输出白名单标签，XSS 没有注入面。
 */
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  confirmPendingAction,
  getSource,
  listProducts,
  runKnowledgeQuery,
  streamKnowledgeQuery,
  type KnowledgeResponse,
  type KnowledgeSource,
  type PendingAction,
  type StreamEvent,
} from '@/api'
import AnswerBody from '@/components/AnswerBody.vue'
import AppHeader from '@/components/AppHeader.vue'
import CapabilityBar from '@/components/CapabilityBar.vue'
import ChatInput from '@/components/ChatInput.vue'
import CollapseSection from '@/components/CollapseSection.vue'
import CompareTable from '@/components/CompareTable.vue'
import EventStream from '@/components/EventStream.vue'
import HeroDeck from '@/components/HeroDeck.vue'
import PendingActionCard from '@/components/PendingActionCard.vue'
import SourceCard from '@/components/SourceCard.vue'
import SourceDialog from '@/components/SourceDialog.vue'
import { useAuthStore } from '@/stores/auth'
import { buildAnswer, citationIndexBySource } from '@/utils/citations'
import { isEmbedded } from '@/utils/embed'
import {
  confidenceLabel,
  formatDateTime,
  formatDuration,
  phaseLabel,
  shortId,
} from '@/utils/format'
import { vReveal } from '@/utils/reveal'

const RESULT_STATUS_LABELS: Record<string, string> = {
  completed: '已完成',
  partial: '部分完成',
  cancelled: '已取消',
  failed: '失败',
}
/** 首屏推荐卡数量。叠卡同屏最多 5 张，推荐位就按 5 张铺。 */
const RECOMMEND_SIZE = 5

/**
 * 浏览器本地查询历史的存储键与容量上限。
 *
 * 历史只回答一个问题：这一轮到底问的是什么。所以条目里只有查询文本和时间，
 * 绝不写 token、账号、session_id、trace_id、产品数据，也不发任何新请求。
 */
const QUERY_HISTORY_KEY = 'richangpim.portal.queryHistory.v1'
const QUERY_HISTORY_LIMIT = 30

/** 一条本地查询历史：只有查询文本和 ISO 时间，不含任何身份或结果数据。 */
interface QueryHistoryItem {
  message: string
  at: string
}

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

/**
 * 被后台「AI 选品」以 iframe 嵌入时不重复渲染门户自己的顶栏：后台已经有一整
 * 套顶栏和账户操作，这里再出一个「退出」按钮会误清共享的登录态。
 */
const embedded = isEmbedded()

const busy = ref(false)
const error = ref('')
const notice = ref('')
const answer = ref('')
const lastQuery = ref('')
const phaseText = ref('')
const products = ref<Array<Record<string, unknown>>>([])
const recommended = ref<Array<Record<string, unknown>>>([])
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
const composer = ref<InstanceType<typeof ChatInput> | null>(null)

/** 本地查询历史：新到旧，最多 QUERY_HISTORY_LIMIT 条。 */
const queryHistory = ref<QueryHistoryItem[]>([])
const historyOpen = ref(false)
const lastQueryAt = ref('')

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
/** 本次查询的时间戳：查询后立刻能看到「这一轮问的是什么、什么时候问的」。 */
const lastQueryTime = computed(() => (lastQueryAt.value ? formatDateTime(lastQueryAt.value) : ''))
/** 折叠行的文案：「历史查询 12 条 ▾」。 */
const historySummary = computed(() => {
  const count = queryHistory.value.length
  return count ? `历史查询 ${count} 条` : '历史查询'
})
/** 门户 viewer 只有 ai:* 权限，取产品列表会 403，所以先判断再请求。 */
const canViewProducts = computed(
  () => auth.roleCode === 'admin' || auth.permissions.includes('product:view'),
)

/**
 * 卡堆的展示状态，五种状态互斥，不允许互相顶替：
 * 1. result     —— AI 返回了产品，卡堆显示真实产品图；
 * 2. loading    —— 查询进行中且还没有产品，显示骨架卡；
 * 3. empty      —— 查过了但没产品，显示明确的空状态（不是空白卡）；
 * 4. recommend  —— 未查询，显示首屏推荐产品；
 * 5. placeholder—— 未查询且拿不到推荐（门户 viewer 没有 product:view），
 *                  退化成空白占位卡，**不编造数据**。
 */
const deckMode = computed<'result' | 'recommend' | 'loading' | 'empty' | 'placeholder'>(() => {
  if (products.value.length) return 'result'
  if (busy.value) return 'loading'
  if (lastQuery.value) return 'empty'
  if (recommended.value.length) return 'recommend'
  return 'placeholder'
})
const deckProducts = computed(() =>
  deckMode.value === 'recommend' ? recommended.value : products.value,
)
const deckLabel = computed(() => {
  if (deckMode.value === 'result') return '产品结果'
  if (deckMode.value === 'recommend') return '推荐产品'
  if (deckMode.value === 'loading') return '产品检索中'
  if (deckMode.value === 'empty') return '产品结果'
  return '推荐产品位'
})
/** 卡片堆的说明文字必须让人分清「AI 返回」「推荐」「没有数据」三种情况。 */
const deckCaption = computed(() => {
  if (deckMode.value === 'result') {
    const base = `查询返回 ${products.value.length} 个产品`
    return products.value.length > RECOMMEND_SIZE ? `${base} · 卡堆内滚轮可循环翻看` : base
  }
  if (deckMode.value === 'loading') return '正在检索产品'
  if (deckMode.value === 'empty') {
    if (error.value) return '查询没有返回产品，可以换个说法再试一次'
    return '本次查询没有返回产品'
  }
  if (deckMode.value === 'recommend') {
    return `推荐产品 ${recommended.value.length} 个 · 查询后替换为 AI 返回的结果`
  }
  if (!canViewProducts.value) return '当前账号没有产品浏览权限，查询后这里显示 AI 返回的产品'
  return '暂时没有可展示的产品，查询后这里显示 AI 返回的结果'
})

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
  lastQueryAt.value = ''
}

/* ===== 浏览器本地查询历史 =====
 * 用户原话：「点击查询之后，我看不到本轮查询的是什么。需要有一个地方显示查询历史，
 * 最好是浏览器本地存储，不在服务器端存储。」所以这里只动 localStorage：
 * 不新增接口、不落服务器、不写 token / session_id / trace_id / 产品数据。
 * localStorage 在隐私模式、存储被禁用或配额已满时会抛错，统一静默降级——
 * 读失败当没有历史，写失败只丢这一条历史，查询流程本身不受影响。
 */
function safeLocalStorage(): Storage | null {
  try {
    return window.localStorage
  } catch {
    return null
  }
}

function parseHistoryItem(value: unknown): QueryHistoryItem | null {
  if (typeof value !== 'object' || value === null) return null
  const record = value as Record<string, unknown>
  const message = typeof record.message === 'string' ? record.message.trim() : ''
  if (!message) return null
  const at = typeof record.at === 'string' ? record.at : ''
  if (at && Number.isNaN(new Date(at).getTime())) return null
  return { message, at }
}

function readQueryHistory(): QueryHistoryItem[] {
  const store = safeLocalStorage()
  if (!store) return []
  try {
    const raw = store.getItem(QUERY_HISTORY_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .map((item) => parseHistoryItem(item))
      .filter((item): item is QueryHistoryItem => item !== null)
      .slice(0, QUERY_HISTORY_LIMIT)
  } catch {
    return []
  }
}

function writeQueryHistory(list: QueryHistoryItem[]) {
  const store = safeLocalStorage()
  if (!store) return
  try {
    store.setItem(QUERY_HISTORY_KEY, JSON.stringify(list))
  } catch {
    // 配额已满或被禁用：这一条历史不入库，界面上已有的列表照常可用。
  }
}

/**
 * 成功后留档。同句重复查询时把旧条目上提到最前并更新时间戳，
 * 因此既不会堆重复项，也不会因为「相邻重复」凭空多出记录。
 */
function recordQueryHistory(message: string) {
  const text = message.trim()
  if (!text) return
  const kept = queryHistory.value.filter((item) => item.message !== text)
  queryHistory.value = [{ message: text, at: new Date().toISOString() }, ...kept].slice(
    0,
    QUERY_HISTORY_LIMIT,
  )
  writeQueryHistory(queryHistory.value)
}

function clearQueryHistory() {
  queryHistory.value = []
  historyOpen.value = false
  writeQueryHistory([])
}

/** 点历史条目：先把该句填回输入框，再立即重新执行这一次查询。 */
function rerunQuery(item: QueryHistoryItem) {
  if (busy.value) return
  historyOpen.value = false
  composer.value?.prefill(item.message)
  void submit(item.message)
}

/** 相对时间：让列表里一眼分出「刚刚」和「三天前」，再早退回具体日期。 */
function relativeTime(at: string): string {
  if (!at) return ''
  const parsed = Date.parse(at)
  if (Number.isNaN(parsed)) return ''
  const diff = Date.now() - parsed
  if (diff < 0) return '刚刚'
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(hours / 24)
  if (days <= 7) return `${days} 天前`
  return formatDateTime(at)
}

/** 历史条目上的完整时间提示（悬停 / 读屏都能拿到确切时间）。 */
function historyTimeTitle(item: QueryHistoryItem): string {
  return item.at ? formatDateTime(item.at) : '时间未记录'
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

/** 只有用户点「向下查看回答」时才滚动，查询本身不抢走视口。 */
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
  lastQueryAt.value = new Date().toISOString()
  phaseText.value = '正在识别意图'
  busy.value = true
  const startedAt = Date.now()
  controller.value = new AbortController()
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
    // 查询走通才留档：失败和中止的尝试不进历史，列表里只留下真正问过的问题。
    recordQueryHistory(message)
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
  if (canViewProducts.value) return `/admin${detailPath}`
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

/** 能力入口只把关键词填进输入框，最后一步仍由用户按发送。 */
function prefill(text: string) {
  composer.value?.prefill(text)
}

/**
 * 首屏推荐产品。403 或后端不可用时保持空数组，让卡位退化成空白占位卡，
 * 绝不用假数据填充。
 */
async function loadRecommended() {
  if (!canViewProducts.value) return
  const token = await auth.ensureToken()
  if (!token) return
  try {
    recommended.value = await listProducts(token, RECOMMEND_SIZE)
  } catch {
    recommended.value = []
  }
}

function signOut() {
  auth.clear()
  void router.push('/')
}

onMounted(() => {
  // 本地历史与服务器会话无关：进页面即读，login/刷新后照样看得到。
  queryHistory.value = readQueryHistory()
  const initial = route.query.q
  if (typeof initial === 'string' && initial) void submit(initial)
  void loadRecommended()
})
</script>

<template>
  <!--
    顶栏右侧只放文字入口：不要按钮容器（无背景 / 边框 / 圆角 / 阴影 / 胶囊），
    颜色由 .site-header__link 统一控制。「进入后台」指向后台那个独立 SPA
    （nginx 把它挂在 /admin/，门户路由里没有这条路径），所以用原生 <a href>，
    与产品卡跳 /admin/products/:id 的做法一致；「退出」仍走门户自己的登录态清理。
  -->
  <AppHeader v-if="!embedded" :show-sub-label="false">
    <button v-if="started" type="button" class="site-header__link" @click="reset">清空结果</button>
    <a class="site-header__link" href="/admin/products">进入后台</a>
    <button type="button" class="site-header__link" @click="signOut">退出</button>
  </AppHeader>

  <main class="chat-shell" :class="{ 'chat-shell--embedded': embedded }">
    <section class="chat-hero" :class="{ 'chat-hero--compact': started }">
      <div class="chat-intro">
        <h1>把产品、资料和质量记录放到同一个查询入口。</h1>
        <p v-if="!started">
          输入型号、场景、材质、预算或对比需求，AI 会返回答案、候选产品、引用来源和需要确认的动作。
        </p>
      </div>

      <div class="composer-wrap">
        <ChatInput ref="composer" :busy="busy" @submit="submit" @stop="stop" />

        <!--
          查询历史（仅浏览器本地）。默认折叠成一行，展开后点任意一条即把该句
          填回输入框并重新执行；「清空历史」只清本地，不碰任何服务器数据。
        -->
        <div v-if="queryHistory.length" class="query-history">
          <div class="query-history__bar">
            <button
              type="button"
              class="query-history__toggle"
              :aria-expanded="historyOpen"
              aria-controls="query-history-list"
              @click="historyOpen = !historyOpen"
            >
              <span>{{ historySummary }}</span>
              <svg
                class="query-history__caret"
                :class="{ 'query-history__caret--open': historyOpen }"
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M6 9l6 6l6-6"
                  stroke="currentColor"
                  stroke-width="1.8"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </button>
            <button type="button" class="button button--ghost button--small" @click="clearQueryHistory">
              清空历史
            </button>
          </div>
          <ul v-show="historyOpen" id="query-history-list" class="query-history__list" aria-label="本地查询历史">
            <li v-for="item in queryHistory" :key="item.message">
              <button
                type="button"
                class="query-history__item"
                :title="historyTimeTitle(item)"
                :aria-label="`重新查询：${item.message}，${historyTimeTitle(item)}`"
                @click="rerunQuery(item)"
              >
                <span class="query-history__text">{{ item.message }}</span>
                <span class="query-history__time">{{ relativeTime(item.at) }}</span>
              </button>
            </li>
          </ul>
        </div>
      </div>

      <HeroDeck
        :products="deckProducts"
        :detail-url="productDetailUrl"
        :variant="deckMode"
        :label="deckLabel"
        :placeholder-count="RECOMMEND_SIZE"
      />
      <p class="hero-status">{{ deckCaption }}</p>

      <CapabilityBar @pick="prefill" />

      <button v-if="started" type="button" class="scroll-cue" @click="scrollToResults">
        <span>向下查看回答</span>
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M12 5v14m-7-7l7 7l7-7"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
    </section>

    <section v-if="started" ref="resultsEl" class="workspace" aria-label="查询结果">
      <p v-if="lastQuery" class="query-echo">
        <span>本次查询</span>
        <strong>{{ lastQuery }}</strong>
        <time v-if="lastQueryTime" class="query-echo__time" :datetime="lastQueryAt">{{ lastQueryTime }}</time>
      </p>

      <article v-reveal class="panel panel--answer">
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
      <section v-if="pendingActions.length" v-reveal class="stack" aria-label="待确认动作">
        <PendingActionCard
          v-for="action in pendingActions"
          :key="action.id"
          :action="action"
          :busy="busy"
          @confirm="confirmAction"
        />
      </section>

      <!-- 比较表的根节点自带 v-if，套 v-reveal 会落到注释节点上，所以这里不做滚动淡入 -->
      <CompareTable :products="products" class="workspace__wide" />

      <template v-if="sources.length">
        <div class="section-head">
          <h2>引用来源</h2>
          <span class="section-head__count">{{ sources.length }} 条</span>
        </div>
        <section v-reveal class="card-list source-list" aria-label="引用来源">
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

<style scoped>
/* ===== 查询历史（浏览器本地）=====
 * 挂在输入框正下方，与胶囊输入同一条视觉动线：默认折叠成一行文字，展开是
 * 一张弱填充的列表。样式沿用 main.css 的令牌（ink / border / radius），
 * 深色主题自动跟随，不另写颜色。
 */

.query-history {
  margin-top: -6px;
}

/* 折叠行：左边「历史查询 N 条 ▾」，右边「清空历史」，两端对齐、不换行 */
.query-history__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 30px;
}

.query-history__toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border: none;
  background: none;
  color: var(--ink-muted);
  font-size: 12.5px;
  font-weight: 500;
  line-height: 1.6;
  cursor: pointer;
  transition: color .18s ease;
}
.query-history__toggle:hover { color: var(--ink); }
.query-history__toggle:focus-visible {
  outline: 2px solid var(--pine);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
}
.query-history__caret {
  width: 15px;
  height: 15px;
  flex: none;
  transition: transform .18s ease;
}
.query-history__caret--open { transform: rotate(180deg); }

.query-history__list {
  list-style: none;
  margin: 6px 0 0;
  padding: 4px;
  max-height: 264px;
  overflow-y: auto;
  overscroll-behavior: contain;
  background: var(--surface-soft);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

/* 列表行：整行可点，hover 高亮；左边查询文本、右边相对时间 */
.query-history__item {
  display: flex;
  align-items: baseline;
  gap: 12px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: none;
  text-align: left;
  cursor: pointer;
  transition: background-color .18s ease;
}
.query-history__item + .query-history__item { margin-top: 2px; }
.query-history__item:hover { background: var(--surface-strong); }
.query-history__item:focus-visible {
  outline: 2px solid var(--pine);
  outline-offset: -2px;
}
.query-history__text {
  flex: 1 1 auto;
  min-width: 0;
  color: var(--ink);
  font-size: 13px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.query-history__time {
  flex: none;
  color: var(--ink-subtle);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* 「本次查询」回显：加一个右对齐的时间戳，滚动后翻回来也知道是这一轮的 */
.query-echo__time {
  margin-left: auto;
  color: var(--ink-subtle);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

@media (max-width: 640px) {
  .query-history__list { max-height: 208px; }
  .query-history__item { flex-wrap: wrap; }
  .query-history__time { flex-basis: 100%; }
}
</style>
