<template>
  <div class="ai-select-page">
    <el-row :gutter="20">
      <!-- Chat panel -->
      <el-col
        :xs="24"
        :md="16"
      >
        <el-card class="chat-card">
          <template #header>
            <div class="card-header">
              <span>AI 智能对话</span>
              <el-tag
                size="small"
                type="info"
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
              @keydown.enter="handleSend"
            >
              <template #append>
                <el-button
                  type="primary"
                  :loading="aiLoading"
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
        <el-card class="recommend-card">
          <template #header>
            <span>AI 智能选品</span>
          </template>

          <el-form label-position="top">
            <el-form-item label="需求描述">
              <el-input
                v-model="recommendInput"
                type="textarea"
                :rows="4"
                placeholder="描述您的需求，例如：需要一款适合油性皮肤的保湿乳液，预算100元以内"
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="recommendLoading"
                style="width: 100%;"
                @click="handleRecommend"
              >
                AI 推荐
              </el-button>
            </el-form-item>
          </el-form>

          <el-divider content-position="left">
            推荐结果
          </el-divider>

          <!-- Degraded / parse-failed banner -->
          <el-alert
            v-if="recommendDegraded"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 12px;"
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
              style="margin-right: 4px;"
            >
              筛选条件
            </el-tag>
            <el-tag
              v-for="(val, key) in filteredFilters"
              :key="key"
              size="small"
              style="margin: 2px;"
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
              class="result-item"
            >
              <div class="result-header">
                <el-tag
                  size="small"
                  type="success"
                >
                  {{ item.product_name }}
                </el-tag>
                <el-tag
                  v-if="item._verified"
                  size="small"
                  type="warning"
                  effect="dark"
                  style="margin-left: 6px;"
                >
                  已验证
                  <span v-if="item._verified_by"> by {{ item._verified_by }}</span>
                </el-tag>
              </div>
              <div class="result-meta">
                <span v-if="item.product_no">编号: {{ item.product_no }}</span>
                <span v-if="item.face_price">面价: ¥{{ item.face_price }}</span>
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
.ai-select-page {
  padding: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

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
}

.message {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  padding: 0 16px;
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
  background: #e6e8eb;
  flex-shrink: 0;
}

.message-user .message-avatar {
  background: #d9ecff;
}

.message-content {
  max-width: 80%;
}

.message-text {
  background: #f4f4f5;
  padding: 10px 14px;
  border-radius: 8px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.message-user .message-text {
  background: #ecf5ff;
}

.message-sources {
  margin-top: 8px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.chat-input {
  border-top: 1px solid #ebeef5;
  padding-top: 16px;
}

.recommend-card :deep(.el-card__body) {
  overflow-y: auto;
}

.recommend-rationale {
  margin-bottom: 12px;
  padding: 10px 12px;
  background: #f0f7ff;
  border-radius: 4px;
  border-left: 3px solid #409eff;
}

.recommend-rationale p {
  margin: 6px 0 0;
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
}

.recommend-filters {
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
}

.result-item {
  margin-bottom: 12px;
  padding: 10px;
  background: #f5f7fa;
  border-radius: 4px;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.result-meta {
  font-size: 12px;
  color: #909399;
  display: flex;
  gap: 12px;
  margin-bottom: 4px;
}

.result-desc {
  margin: 4px 0 0;
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
}
</style>
