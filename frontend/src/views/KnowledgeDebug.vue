<template>
  <section class="debug-page">
    <div class="panel composer">
      <div>
        <p class="eyebrow">Knowledge Gateway / P1</p>
        <h2>统一只读智能层调试</h2>
        <p class="hint">仅调用 <code>/api/v1/knowledge/query</code>，不保存完整对话。</p>
      </div>
      <el-input
        v-model="message"
        type="textarea"
        :rows="6"
        maxlength="4000"
        show-word-limit
        placeholder="例如：比较 A100 和 A200，或查询哪些产品待核价"
      />
      <div class="actions">
        <el-switch v-model="stream" active-text="SSE" inactive-text="JSON" />
        <el-button type="primary" :loading="loading" @click="submit">发送</el-button>
        <el-button :disabled="!loading" @click="abort">停止生成</el-button>
      </div>
    </div>

    <div class="grid">
      <div class="panel">
        <h3>Trace</h3>
        <pre>{{ traceText }}</pre>
      </div>
      <div class="panel">
        <h3>Answer</h3>
        <p class="answer">{{ answer || '暂无回答' }}</p>
      </div>
      <div class="panel wide">
        <h3>Events</h3>
        <pre>{{ eventsText }}</pre>
      </div>
      <div class="panel wide">
        <h3>Products</h3>
        <pre>{{ JSON.stringify(products, null, 2) }}</pre>
      </div>
      <div class="panel wide">
        <h3>Sources</h3>
        <pre>{{ JSON.stringify(sources, null, 2) }}</pre>
      </div>
      <div class="panel wide error-panel" v-if="error">
        <h3>Error</h3>
        <pre>{{ error }}</pre>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

type GatewayEvent = { event: string; data: unknown }

const message = ref('')
const stream = ref(true)
const loading = ref(false)
const answer = ref('')
const trace = ref<Record<string, unknown>>({})
const products = ref<unknown[]>([])
const sources = ref<unknown[]>([])
const events = ref<GatewayEvent[]>([])
const error = ref('')
let controller: AbortController | null = null

const traceText = computed(() => JSON.stringify(trace.value, null, 2))
const eventsText = computed(() => events.value.map((e) => `${e.event}: ${JSON.stringify(e.data)}`).join('\n'))

async function submit() {
  if (!message.value.trim()) return
  reset()
  loading.value = true
  controller = new AbortController()
  const token = localStorage.getItem('token')
  try {
    const res = await fetch('/api/v1/knowledge/query', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(stream.value ? { Accept: 'text/event-stream' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        message: message.value,
        capabilities: { stream: stream.value, supports_actions: false },
        scope: { type: 'global', product_ids: [], filters: {} },
        client_context: { page: 'knowledge-debug', locale: 'zh-CN', timezone: 'Asia/Shanghai' },
      }),
      signal: controller.signal,
    })
    if (!res.ok) {
      error.value = await res.text()
      return
    }
    if (stream.value) await readStream(res)
    else await readJson(res)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
    controller = null
  }
}

async function readJson(res: Response) {
  const payload = await res.json()
  const data = payload.data || payload
  trace.value = { trace_id: data.trace_id, session_id: data.session_id, confidence: data.confidence, usage: data.usage }
  answer.value = data.answer || ''
  products.value = data.products || []
  sources.value = data.sources || []
  events.value.push({ event: 'json', data })
}

async function readStream(res: Response) {
  const reader = res.body?.getReader()
  if (!reader) return
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''
    for (const frame of frames) parseFrame(frame)
  }
  if (buffer.trim()) parseFrame(buffer)
}

function parseFrame(frame: string) {
  const eventLine = frame.split('\n').find((line) => line.startsWith('event:'))
  const dataLine = frame.split('\n').find((line) => line.startsWith('data:'))
  if (!eventLine || !dataLine) return
  const name = eventLine.slice(6).trim()
  const data = JSON.parse(dataLine.slice(5).trim())
  events.value.push({ event: name, data })
  if (name === 'meta') trace.value = { ...trace.value, ...(data as Record<string, unknown>) }
  if (name === 'answer_delta') answer.value += (data as { text?: string }).text || ''
  if (name === 'products') products.value = (data as { items?: unknown[] }).items || []
  if (name === 'source') sources.value.push(data)
  if (name === 'error') error.value = JSON.stringify(data, null, 2)
  if (name === 'done') trace.value = { ...trace.value, ...(data as Record<string, unknown>) }
}

function abort() {
  controller?.abort()
}

function reset() {
  answer.value = ''
  trace.value = {}
  products.value = []
  sources.value = []
  events.value = []
  error.value = ''
}
</script>

<style scoped>
.debug-page { display: grid; gap: 16px; }
.panel { border: 1px solid rgba(30, 50, 90, 0.12); border-radius: 24px; background: rgba(255, 255, 255, 0.72); padding: 18px; box-shadow: 0 16px 48px rgba(30, 50, 90, 0.06); }
.composer { display: grid; gap: 14px; }
.eyebrow { margin: 0 0 6px; color: rgba(30, 50, 90, 0.48); font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; }
h2, h3 { margin: 0 0 10px; color: rgba(30, 50, 90, 0.9); font-weight: 500; }
.hint { margin: 0; color: rgba(30, 50, 90, 0.56); }
.actions { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.wide { grid-column: span 2; }
pre { max-height: 360px; overflow: auto; white-space: pre-wrap; word-break: break-word; color: rgba(30, 50, 90, 0.78); }
.answer { min-height: 72px; color: rgba(30, 50, 90, 0.82); line-height: 1.8; }
.error-panel { border-color: rgba(190, 60, 60, 0.28); background: rgba(255, 240, 240, 0.78); }
@media (max-width: 720px) { .grid { grid-template-columns: 1fr; } .wide { grid-column: auto; } }
</style>
