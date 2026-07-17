<template>
  <div class="ai-select-page">
    <el-row :gutter="20">
      <!-- Chat panel -->
      <el-col
        :xs="24"
        :md="16"
      >
        <el-card class="chat-card glass-card">
          <template #header>
            <div class="card-header">
              <span class="card-title">AI 智能对话</span>
              <el-tag
                size="small"
                type="info"
                class="capsule-tag session-tag"
              >
                会话: {{ sessionId }}
              </el-tag>
            </div>
          </template>

          <div
            ref="messagesContainer"
            class="chat-messages"
          >
            <div
              v-for="(msg, idx) in messages"
              :key="idx"
              :class="['message', msg.role === 'user' ? 'message-user' : 'message-ai']"
            >
              <div class="message-avatar">
                <el-icon v-if="msg.role === 'user'">
                  <User />
                </el-icon>
                <el-icon v-else>
                  <Cpu />
                </el-icon>
              </div>
              <div class="message-content">
                <div class="message-text">
                  {{ msg.content }}
                </div>
                <div
                  v-if="msg.sources?.length"
                  class="message-sources"
                >
                  <el-tag
                    v-for="(s, sidx) in msg.sources"
                    :key="sidx"
                    size="small"
                    type="info"
                    class="capsule-tag"
                  >
                    {{ s }}
                  </el-tag>
                </div>
              </div>
            </div>
            <div
              v-if="aiLoading"
              class="message message-ai"
            >
              <div class="message-avatar">
                <el-icon><Cpu /></el-icon>
              </div>
              <div class="message-content">
                <el-skeleton
                  :rows="2"
                  animated
                />
              </div>
            </div>
          </div>

          <div class="chat-input">
            <el-input
              v-model="userInput"
              placeholder="输入您的问题，例如：推荐适合夏季的护肤品"
              :disabled="aiLoading"
              class="capsule-input"
              @keydown.enter="handleSend"
            >
              <template #append>
                <el-button
                  type="primary"
                  :loading="aiLoading"
                  class="capsule-btn capsule-btn-primary send-btn"
                  @click="handleSend"
                >
                  发送
                </el-button>
              </template>
            </el-input>
          </div>
        </el-card>
      </el-col>

      <!-- Recommend panel -->
      <el-col
        :xs="24"
        :md="8"
      >
        <el-card class="recommend-card glass-card">
          <template #header>
            <span class="card-title">AI 智能选品</span>
          </template>

          <el-form label-position="top">
            <el-form-item label="需求描述">
              <el-input
                v-model="recommendInput"
                type="textarea"
                :rows="4"
                placeholder="描述您的需求，例如：需要一款适合油性皮肤的保湿乳液，预算100元以内"
                class="capsule-textarea"
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="recommendLoading"
                class="capsule-btn capsule-btn-primary full-width"
                @click="handleRecommend"
              >
                AI 推荐
              </el-button>
            </el-form-item>
          </el-form>

          <el-divider
            content-position="left"
            class="glass-divider"
          >
            推荐结果
          </el-divider>

          <!-- Degraded / parse-failed banner -->
          <el-alert
            v-if="recommendDegraded"
            type="warning"
            :closable="false"
            show-icon
            class="glass-alert"
          >
            <template #title>
              {{ parseFailed ? 'AI 解析失败，请修正需求后重试' : 'AI 服务暂时不可用，未生成推荐结果' }}
            </template>
          </el-alert>

          <!-- Rationale -->
          <div
            v-if="recommendRationale"
            class="recommend-rationale"
          >
            <el-tag
              type="primary"
              size="small"
              class="capsule-tag"
            >
              选品思路
            </el-tag>
            <p>{{ recommendRationale }}</p>
          </div>

          <!-- Filters applied -->
          <div
            v-if="hasFilters"
            class="recommend-filters"
          >
            <el-tag
              type="info"
              size="small"
              class="capsule-tag"
            >
              筛选条件
            </el-tag>
            <el-tag
              v-for="(val, key) in filteredFilters"
              :key="key"
              size="small"
              class="capsule-tag filter-tag"
            >
              {{ key }}: {{ formatFilterValue(val) }}
            </el-tag>
          </div>

          <!-- Products -->
          <div
            v-if="recommendResults.length"
            class="recommend-results"
          >
            <div
              v-for="(item, idx) in recommendResults"
              :key="idx"
              class="result-item glass-item"
            >
              <div class="result-header">
                <el-tag
                  size="small"
                  type="success"
                  class="capsule-tag result-name"
                >
                  {{ item.product_name }}
                </el-tag>
                <el-tag
                  v-if="item._verified"
                  size="small"
                  type="warning"
                  effect="dark"
                  class="capsule-tag"
                >
                  已验证
                  <span v-if="item._verified_by"> by {{ item._verified_by }}</span>
                </el-tag>
              </div>
              <div class="result-meta">
                <span v-if="item.product_no">编号: <span class="mono-text">{{ item.product_no }}</span></span>
                <span v-if="item.face_price">面价: <span class="price-text">¥{{ item.face_price }}</span></span>
                <span v-if="item.stock_status">状态: {{ item.stock_status }}</span>
              </div>
              <p
                v-if="item.description"
                class="result-desc"
              >
                {{ item.description }}
              </p>
            </div>
          </div>
          <el-empty
            v-else-if="!recommendLoading && !recommendDegraded"
            description="暂无推荐结果"
          />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { User, Cpu } from '@element-plus/icons-vue'
import { aiApi } from '@/api'
import type { RecommendProduct, RecommendResponse } from '@/types/ai'
import { isRecommendDegraded } from '@/types/ai'

const messagesContainer = ref<HTMLElement | null>(null)
const userInput = ref('')
const aiLoading = ref(false)
const sessionId = ref(Math.random().toString(36).slice(2, 10))
const messages = ref<{ role: string; content: string; sources?: string[] }[]>([])

const recommendInput = ref('')
const recommendLoading = ref(false)
const recommendResults = ref<RecommendProduct[]>([])
const recommendRationale = ref('')
const recommendFilters = ref<Record<string, unknown>>({})
const recommendSources = ref<string[]>([])

const parseFailed = ref(false)
const recommendStatus = ref<RecommendResponse['status']>('unknown')
const recommendDegraded = computed(() => {
  if (!recommendRationale.value && recommendResults.value.length === 0) return false
  const mockResp: RecommendResponse = {
    status: recommendStatus.value,
    filters_applied: recommendFilters.value,
    products: recommendResults.value as RecommendProduct[],
    rationale: recommendRationale.value,
    total: recommendResults.value.length,
    sources: [],
  }
  return isRecommendDegraded(mockResp)
})

const hasFilters = computed(() => {
  return Object.keys(recommendFilters.value).length > 0
})

const filteredFilters = computed(() => {
  const f: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(recommendFilters.value)) {
    if (v !== null && v !== undefined && v !== '' && (!Array.isArray(v) || v.length > 0)) {
      f[k] = v
    }
  }
  return f
})

function formatFilterValue(val: unknown): string {
  if (Array.isArray(val)) return val.join(', ')
  if (typeof val === 'boolean') return val ? '是' : '否'
  return String(val)
}

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

const handleSend = async () => {
  if (!userInput.value.trim() || aiLoading.value) return
  const question = userInput.value.trim()
  userInput.value = ''
  messages.value.push({ role: 'user', content: question })
  scrollToBottom()

  aiLoading.value = true
  try {
    const history = messages.value
      .filter(m => m.role !== 'ai')
      .map(m => ({ role: m.role, content: m.content }))

    const res = await aiApi.chat({
      session_id: sessionId.value,
      message: question,
      history: history.slice(-10),
      stream: false,
    }) as { data: { answer?: string; sources?: unknown[] } }

    const data = res.data
    messages.value.push({
      role: 'ai',
      content: data.answer || '暂无回复',
      sources: (data.sources as any[] | undefined)?.slice(0, 3).map((s) => (s as any)?.product_name || (s as any)?.doc_title || '未知来源'),
    })
  } catch {
    messages.value.push({ role: 'ai', content: 'AI 服务暂时不可用，请稍后重试' })
  } finally {
    aiLoading.value = false
    scrollToBottom()
  }
}

const handleRecommend = async () => {
  if (!recommendInput.value.trim() || recommendLoading.value) return
  recommendLoading.value = true
  recommendResults.value = []
  recommendRationale.value = ''
  recommendFilters.value = {}
  recommendSources.value = []
  parseFailed.value = false
  recommendStatus.value = 'unknown'
  try {
    const res = await aiApi.recommend({
      requirement: recommendInput.value.trim(),
    }) as { data: RecommendResponse }

    const data = res.data
    recommendStatus.value = data.status || 'unknown'
    recommendFilters.value = data.filters_applied || {}
    recommendRationale.value = data.rationale || ''
    recommendSources.value = (data.sources || []).map((s) => (s as any)?.product_name || (s as any)?.doc_title || '未知来源')

    parseFailed.value = data.status === 'parse_failed'

    recommendResults.value = (data.products || []).map((p) => ({
      id: p.id || '',
      product_no: p.product_no || '',
      product_name: p.product_name || '未知商品',
      brand_id: p.brand_id || '',
      category_id: p.category_id || '',
      face_price: p.face_price || 0,
      cost_price: p.cost_price,
      supplier_id: p.supplier_id || '',
      material: p.material,
      stock_status: p.stock_status || '',
      description: p.description,
      _verified: p._verified || false,
      _verified_by: p._verified_by,
    }))
  } catch {
    ElMessage.error('AI 推荐失败')
  } finally {
    recommendLoading.value = false
  }
}

onMounted(() => {
  messages.value.push({
    role: 'ai',
    content: '您好！我是 AI 选品助手，可以帮您推荐商品或回答产品相关问题。请告诉我您的需求。',
  })
})
</script>

<style scoped>
/* ===== CSS Variables ===== */
.ai-select-page {
  --brand-deep: rgba(30, 50, 90, 0.92);
  --brand-primary: rgba(30, 50, 90, 0.85);
  --brand-light: rgba(30, 50, 90, 0.08);
  --brand-lighter: rgba(30, 50, 90, 0.04);
  --text-primary: #5E6470;
  --text-secondary: rgba(30, 50, 90, 0.6);
  --bg-mist: #f0f0f0;
  --glass-bg: rgba(255, 255, 255, 0.72);
  --glass-border: rgba(255, 255, 255, 0.5);
  --radius-lg: 28px;
  --radius-md: 18px;
  --radius-sm: 12px;
  --shadow-soft: 0 4px 24px rgba(30, 50, 90, 0.06);
  --transition-fast: 200ms cubic-bezier(0.4, 0, 0.2, 1);
  padding: 16px;
  min-height: 100vh;
  background: var(--bg-mist);
}

/* ===== Glass Card ===== */
.glass-card {
  background: var(--glass-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-soft);
  overflow: hidden;
}

.glass-card :deep(.el-card__header) {
  background: transparent;
  border-bottom: 1px solid rgba(30, 50, 90, 0.06);
  padding: 16px 20px;
}

.glass-card :deep(.el-card__body) {
  padding: 16px 20px;
}

/* ===== Card Header ===== */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--brand-deep);
}

.session-tag {
  font-size: 11px;
  font-family: monospace;
}

/* ===== Chat Messages ===== */
.chat-card, .recommend-card {
  height: calc(100vh - 140px);
  display: flex;
  flex-direction: column;
}

.chat-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
  display: flex;
  flex-direction: column;
}

.message {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  padding: 0 20px;
  animation: fadeIn 300ms ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.message-user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: linear-gradient(135deg, rgba(30, 50, 90, 0.1), rgba(30, 50, 90, 0.2));
  color: var(--brand-deep);
}

.message-user .message-avatar {
  background: linear-gradient(135deg, rgba(30, 50, 90, 0.15), rgba(30, 50, 90, 0.25));
}

.message-content {
  max-width: 80%;
}

.message-text {
  background: rgba(30, 50, 90, 0.05);
  padding: 12px 16px;
  border-radius: 18px;
  border-top-left-radius: 4px;
  line-height: 1.7;
  white-space: pre-wrap;
  font-size: 14px;
  color: var(--text-primary);
}

.message-user .message-text {
  background: rgba(30, 50, 90, 0.08);
  border-radius: 18px;
  border-top-right-radius: 4px;
}

.message-sources {
  margin-top: 8px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

/* ===== Chat Input ===== */
.chat-input {
  border-top: 1px solid rgba(30, 50, 90, 0.08);
  padding-top: 16px;
}

.chat-input :deep(.el-input__wrapper) {
  border-radius: 24px;
  box-shadow: 0 0 0 1px rgba(30, 50, 90, 0.1) inset;
  padding: 4px 16px;
}

.chat-input :deep(.el-input-group__append) {
  border-radius: 0 24px 24px 0;
}

.send-btn {
  border-radius: 0 24px 24px 0 !important;
  padding: 8px 18px;
}

/* ===== Capsule Tag ===== */
.capsule-tag {
  border-radius: 12px;
  padding: 2px 10px;
  font-weight: 500;
}

/* ===== Recommend Card ===== */
.recommend-card :deep(.el-card__body) {
  overflow-y: auto;
}

.capsule-textarea :deep(.el-textarea__inner) {
  border-radius: 16px;
  box-shadow: 0 0 0 1px rgba(30, 50, 90, 0.1) inset;
  transition: var(--transition-fast);
}

.capsule-textarea :deep(.el-textarea__inner):hover,
.capsule-textarea :deep(.el-textarea__inner):focus {
  box-shadow: 0 0 0 2px rgba(30, 50, 90, 0.15) inset;
}

.full-width {
  width: 100%;
}

/* ===== Divider ===== */
.glass-divider {
  border-color: rgba(30, 50, 90, 0.1);
  margin: 16px 0 12px;
}

.glass-divider :deep(.el-divider__text) {
  color: var(--brand-deep);
  font-weight: 600;
  font-size: 13px;
}

/* ===== Alert ===== */
.glass-alert {
  border-radius: var(--radius-sm);
  margin-bottom: 12px;
}

/* ===== Rationale ===== */
.recommend-rationale {
  margin-bottom: 12px;
  padding: 12px 14px;
  background: var(--brand-light);
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--brand-primary);
}

.recommend-rationale p {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.6;
}

/* ===== Filters ===== */
.recommend-filters {
  margin-bottom: 12px;
  padding: 10px 14px;
  background: var(--brand-lighter);
  border-radius: var(--radius-sm);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.filter-tag {
  font-size: 11px;
}

/* ===== Result Items ===== */
.recommend-results {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.glass-item {
  padding: 14px 16px;
  background: var(--brand-lighter);
  border-radius: var(--radius-md);
  border: 1px solid rgba(30, 50, 90, 0.04);
  transition: var(--transition-fast);
}

.glass-item:hover {
  background: var(--brand-light);
}

.result-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.result-name {
  font-size: 13px;
}

.result-meta {
  font-size: 12px;
  color: var(--text-secondary);
  display: flex;
  gap: 12px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}

.mono-text {
  font-family: monospace;
}

.price-text {
  color: var(--brand-deep);
  font-weight: 600;
  font-family: monospace;
}

.result-desc {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.6;
}

/* ===== Responsive ===== */
@media (max-width: 768px) {
  .ai-select-page {
    padding: 8px;
  }

  .glass-card {
    border-radius: var(--radius-md);
  }

  .glass-card :deep(.el-card__header),
  .glass-card :deep(.el-card__body) {
    padding: 12px 16px;
  }

  .chat-card, .recommend-card {
    height: auto;
    min-height: 300px;
  }

  .chat-card :deep(.el-card__body) {
    min-height: 300px;
  }

  .message {
    padding: 0 12px;
  }

  .message-content {
    max-width: 90%;
  }

  .el-row {
    display: flex;
    flex-direction: column;
  }

  .el-col {
    width: 100% !important;
  }
}
</style>
