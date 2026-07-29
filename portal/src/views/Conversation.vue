<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  confirmPendingAction,
  getSource,
  type PendingAction,
  runKnowledgeQuery,
  streamKnowledgeQuery,
  type KnowledgeResponse,
  type KnowledgeSource,
  type StreamEvent,
} from '@/api'
import ChatInput from '@/components/ChatInput.vue'
import CompareTable from '@/components/CompareTable.vue'
import EventStream from '@/components/EventStream.vue'
import PendingActionCard from '@/components/PendingActionCard.vue'
import ProductCard from '@/components/ProductCard.vue'
import SourceCard from '@/components/SourceCard.vue'
import { useAuthStore } from '@/stores/auth'
import logoUrl from '../../../logo/RiChangPIM.png'

const auth = useAuthStore()
const route = useRoute()
const busy = ref(false)
const error = ref('')
const answer = ref('')
const products = ref<Array<Record<string, unknown>>>([])
const sources = ref<KnowledgeSource[]>([])
const pendingActions = ref<PendingAction[]>([])
const events = ref<StreamEvent[]>([])
const meta = ref<KnowledgeResponse | null>(null)
const controller = ref<AbortController | null>(null)

const traceId = computed(() => meta.value?.trace_id || '')
const hasResults = computed(
  () => Boolean(answer.value || products.value.length || sources.value.length || pendingActions.value.length || error.value),
)

async function submit(message: string) {
  const token = await auth.ensureToken()
  if (!token) { error.value = '请先登录'; return }
  error.value = ''
  answer.value = ''
  products.value = []
  sources.value = []
  pendingActions.value = []
  events.value = []
  busy.value = true
  controller.value = new AbortController()
  const body = { message, capabilities: { stream: true, supports_actions: true } }
  try {
    await streamKnowledgeQuery(body, token, controller.value.signal, (event) => {
      events.value.push(event)
      if (event.event === 'answer_delta') {
        answer.value += String(event.data.text || '')
      }
      if (event.event === 'source') {
        sources.value.push(event.data as KnowledgeSource)
      }
      if (event.event === 'products') {
        products.value = (event.data.items as Array<Record<string, unknown>>) || []
      }
      if (event.event === 'pending_action') {
        pendingActions.value.push(event.data as PendingAction)
      }
      if (event.event === 'meta') {
        meta.value = {
          trace_id: String(event.data.trace_id || ''),
          session_id: String(event.data.session_id || ''),
          answer: '', facts: [], sources: [], products: [], pending_actions: [],
          confidence: 'medium', insufficient_sources: false, usage: {},
        }
      }
    })
    if (!answer.value) {
      const response = await runKnowledgeQuery({ message, capabilities: { stream: false, supports_actions: true } }, token)
      meta.value = response
      answer.value = response.answer
      products.value = response.products
      sources.value = response.sources
      pendingActions.value = response.pending_actions
    }
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '请求失败'
  } finally {
    busy.value = false
    controller.value = null
  }
}

function stop() { controller.value?.abort(); busy.value = false }

function reset() {
  answer.value = ''
  products.value = []
  sources.value = []
  pendingActions.value = []
  events.value = []
  meta.value = null
  error.value = ''
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
  busy.value = true; error.value = ''
  try {
    const confirmed = await confirmPendingAction(action, token)
    pendingActions.value = pendingActions.value.map((item) => item.id === confirmed.id ? confirmed : item)
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '确认失败'
  } finally {
    busy.value = false
  }
}

async function openSource(sourceId: string) {
  const token = await auth.ensureToken()
  if (!token) return
  try {
    const source = await getSource(sourceId, token)
    const text = [source.title, source.section, source.quote].filter(Boolean).join('\n\n')
    window.alert(text)
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '无法打开来源'
  }
}

onMounted(() => {
  const initial = route.query.q
  if (typeof initial === 'string' && initial) { void submit(initial) }
})
</script>

<template>
  <main class="chat-shell">
    <!-- Minimal sticky header -->
    <header class="site-header">
      <a class="brand-mark" href="/" aria-label="RiChangPIM Portal">
        <img :src="logoUrl" alt="RiChangPIM" />
        <span>Portal</span>
      </a>
      <button type="button" class="button button--secondary" @click="reset">清空</button>
    </header>

    <!-- Centered intro + input (reference chatbot style) -->
    <section class="chat-intro">
      <div>
        <h1>把产品、资料和质量记录放到同一个查询入口。</h1>
        <p>输入型号、场景、材质、预算或对比需求，AI 会返回答案、候选产品、引用来源和需要确认的动作。</p>
      </div>
      <div class="chat-input-wrap">
        <!-- Pre-set prompt tags (left-aligned strip inside container) -->
        <div class="tag-strip" aria-label="快捷产品类型">
          <button v-for="p in ['办公桌','会议桌','安装资料','价格库存']" :key="p" type="button" class="chip" @click="submit(p)">
            {{ p }}
          </button>
        </div>
        <ChatInput :busy="busy" @submit="submit" @stop="stop" />
      </div>
    </section>

    <!-- Results: single centered column, same width as input -->
    <section v-if="hasResults || busy" class="workspace">
      <!-- Answer -->
      <article class="answer-panel" :class="{ 'answer-panel--empty': !hasResults && !busy }">
        <div class="panel__header">
          <div>
            <p class="eyebrow">Assistant summary</p>
            <h2>回答</h2>
          </div>
          <span v-if="traceId" class="trace-pill">{{ traceId }}</span>
        </div>
        <p v-if="busy && !answer" class="muted-text">正在匹配产品与知识来源…</p>
        <p v-else>{{ answer || '等待查询' }}</p>
        <p v-if="error" class="error-text">{{ error }}</p>
      </article>

      <!-- Compare -->
      <CompareTable :products="products" />

      <!-- Products -->
      <section v-if="products.length" class="card-list product-grid" aria-label="产品结果">
        <ProductCard
          v-for="item in products"
          :key="String(item.id || item.product_no)"
          :product="item"
          :detail-url="productDetailUrl(item)"
        />
      </section>

      <!-- Pending actions -->
      <section v-if="pendingActions.length" class="card-list" aria-label="待确认操作">
        <PendingActionCard
          v-for="action in pendingActions"
          :key="action.id"
          :action="action"
          :busy="busy"
          @confirm="confirmAction"
        />
      </section>

      <!-- Sources -->
      <section v-if="sources.length" class="card-list source-grid" aria-label="引用来源">
        <SourceCard v-for="source in sources" :key="source.source_id" :source="source" @open="openSource" />
      </section>

      <!-- Stream events (collapsible / compact) -->
      <section v-if="events.length" class="side-panel" aria-label="流式事件">
        <div class="panel__header">
          <p class="eyebrow">Stream events</p>
          <span>{{ events.length }}</span>
        </div>
        <EventStream :events="events" />
      </section>
    </section>
  </main>
</template>
