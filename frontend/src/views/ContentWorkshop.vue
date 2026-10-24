<template>
  <div class="crm-page">
    <el-card class="crm-card">
      <template #header>
        <div class="crm-card__header">
          <span class="crm-card__title">内容工坊</span>
          <div class="crm-card__actions">
            <el-button
              class="crm-btn"
              :loading="loading"
              @click="loadItems"
            >
              刷新
            </el-button>
          </div>
        </div>
      </template>

      <el-form
        v-if="hasPerm('content:generate')"
        :model="genForm"
        label-width="88px"
        class="gen-form"
      >
        <el-alert
          v-if="topicItem"
          type="success"
          :closable="false"
          class="crm-alert"
        >
          <template #title>
            已带入选题：{{ topicItem.title }}
          </template>
          <div
            v-if="topicItem.angle || topicItem.audience"
            class="topic-banner__meta"
          >
            <span v-if="topicItem.angle">角度：{{ topicItem.angle }}</span>
            <span v-if="topicItem.audience">人群：{{ topicItem.audience }}</span>
          </div>
        </el-alert>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item
              label="批次标题"
              required
            >
              <el-input
                v-model="genForm.title"
                class="crm-input"
                placeholder="如：618 橱柜种草"
              />
            </el-form-item>
          </el-col>
          <el-col :span="4">
            <el-form-item label="平台">
              <el-select
                v-model="genForm.platform"
                class="crm-select"
              >
                <el-option
                  v-for="(label, value) in CONTENT_PLATFORM_MAP"
                  :key="value"
                  :label="label"
                  :value="value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="4">
            <el-form-item label="语气">
              <el-select
                v-model="genForm.tone"
                class="crm-select"
                clearable
                placeholder="默认"
              >
                <el-option
                  v-for="t in CONTENT_TONE_OPTIONS"
                  :key="t.value"
                  :label="t.label"
                  :value="t.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="4">
            <el-form-item label="创作 Skills">
              <el-select
                v-model="genForm.skill_code"
                class="crm-select"
                clearable
                placeholder="自动选择"
              >
                <el-option label="自动选择" :value="null" />
                <el-option
                  v-for="skill in contentSkills"
                  :key="skill.code"
                  :label="skill.name || skill.source_dna_label || skill.code"
                  :value="skill.code"
                >
                  <span>{{ skill.name || skill.code }}</span>
                  <span
                    v-if="skill.source_dna_label"
                    class="skill-option__dna"
                  >{{ skill.source_dna_label }}</span>
                </el-option>
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="产品">
              <el-select
                v-model="genForm.product_ids"
                class="crm-select"
                multiple
                filterable
                remote
                reserve-keyword
                :remote-method="searchProducts"
                :loading="productLoading"
                placeholder="搜索并选择产品（可选）"
              >
                <el-option
                  v-for="p in productOptions"
                  :key="p.id"
                  :label="`${p.product_name}（${p.product_no}）`"
                  :value="p.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="模型">
              <el-select
                v-model="genForm.model_name"
                class="crm-select"
                clearable
                placeholder="自动（服务端默认）"
              >
                <el-option
                  label="自动（服务端默认）"
                  :value="null"
                />
                <el-option
                  v-for="model in modelOptions"
                  :key="model"
                  :label="model"
                  :value="model"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="条数">
              <el-input-number
                v-model="genForm.requested_count"
                :min="1"
                :max="5"
                class="full-width"
              />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item
              label="主题"
              required
            >
              <el-input
                v-model="genForm.topic"
                type="textarea"
                :rows="3"
                class="crm-input crm-input--area"
                placeholder="描述内容主题、卖点方向（不得包含客户/成本信息）"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item>
          <el-button
            type="primary"
            class="crm-btn crm-btn--primary"
            :loading="generating"
            @click="handleGenerate"
          >
            生成内容
          </el-button>
          <span class="gen-hint">AI 生成约需数十秒，请勿重复点击。</span>
        </el-form-item>
      </el-form>

      <div class="crm-section">
        <h3 class="crm-section__title">
          内容条目
          <span class="crm-kpi__label">{{ items.length }} 条</span>
        </h3>
        <p
          v-if="!items.length"
          class="crm-empty"
        >
          暂无内容条目，先在上方生成一批吧。
        </p>
        <div
          v-else
          class="crm-content-grid"
        >
          <article
            v-for="item in items"
            :key="item.id"
            class="crm-content-card"
          >
            <div class="content-card__head">
              <span class="crm-content-card__title">{{ item.title || '（无标题）' }}</span>
              <el-tag
                :type="statusTagType(item.display_state)"
                class="crm-tag"
              >
                {{ labelOf(CONTENT_DISPLAY_STATE_MAP, item.display_state) }}
              </el-tag>
            </div>
            <div class="crm-list-item__meta">
              <span>{{ labelOf(CONTENT_PLATFORM_MAP, item.platform) }}</span>
              <span>{{ formatBeijingTime(item.create_time) }}</span>
              <span v-if="item.source_skill_code">来源：{{ skillSourceLabel(item.source_skill_code) }}</span>
            </div>
            <div class="crm-content-card__body">
              {{ item.body }}
            </div>
            <div
              v-if="item.hashtags.length"
              class="crm-hashtags"
            >
              <el-tag
                v-for="tag in item.hashtags"
                :key="tag"
                size="small"
                type="info"
                class="crm-tag"
              >
                #{{ tag }}
              </el-tag>
            </div>
            <div
              v-if="item.verification_gaps.length"
              class="crm-warning"
            >
              待核验：{{ item.verification_gaps.join('；') }}
            </div>
            <div
              v-if="item.warnings.length"
              class="crm-warning"
            >
              ⚠ {{ item.warnings.join('；') }}
            </div>
            <div class="crm-content-card__foot">
              <el-button
                v-if="hasPerm('content:adopt') && item.status === 'draft'"
                size="small"
                type="primary"
                class="crm-btn crm-btn--primary"
                @click="handleAdopt(item)"
              >
                采纳
              </el-button>
              <el-button
                v-if="hasPerm('content:adopt') && item.status === 'draft'"
                size="small"
                class="crm-btn"
                @click="handleReject(item)"
              >
                不采纳
              </el-button>
              <el-button
                v-if="hasPerm('content:adopt') && item.status === 'adopted'"
                size="small"
                type="primary"
                class="crm-btn crm-btn--primary"
                @click="handleProduce(item)"
              >
                标记制成
              </el-button>
              <el-button
                v-if="hasPerm('content:publish') && ['adopted', 'produced'].includes(item.status)"
                size="small"
                class="crm-btn"
                @click="goPublish(item)"
              >
                去发布
              </el-button>
              <el-button
                v-if="hasPerm('content:generate')"
                size="small"
                class="crm-btn"
                @click="handleDuplicate(item)"
              >
                复制
              </el-button>
              <el-button
                v-if="canEdit(item)"
                size="small"
                text
                class="crm-link"
                @click="openEdit(item)"
              >
                编辑
              </el-button>
            </div>
          </article>
        </div>
      </div>
    </el-card>

    <el-dialog
      v-model="editVisible"
      title="编辑内容"
      width="640px"
      align-center
    >
      <el-form
        v-if="editItem"
        label-width="72px"
      >
        <el-form-item label="标题">
          <el-input
            v-model="editForm.title"
            class="crm-input"
          />
        </el-form-item>
        <el-form-item label="正文">
          <el-input
            v-model="editForm.body"
            type="textarea"
            :rows="8"
            class="crm-input crm-input--area"
            :disabled="editItem.status === 'published'"
          />
        </el-form-item>
        <el-form-item label="标签">
          <el-input
            v-model="editForm.hashtags"
            class="crm-input"
            placeholder="用空格或逗号分隔"
          />
        </el-form-item>
        <p
          v-if="editItem.status === 'published'"
          class="edit-hint"
        >
          已发布条目的正文已锁定，仅可修改标题与标签。
        </p>
      </el-form>
      <template #footer>
        <el-button
          class="crm-btn"
          @click="editVisible = false"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          class="crm-btn crm-btn--primary"
          :loading="saving"
          @click="saveEdit"
        >
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { productApi } from '@/api'
import type { ProductListItem } from '@/types/sales'
import { contentApi, type ContentItem, type ContentItemResult, type ContentSkill, type ContentTopicItemDetail } from '@/api/content'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'
import {
  CONTENT_DISPLAY_STATE_MAP,
  CONTENT_PLATFORM_MAP,
  CONTENT_TONE_OPTIONS,
  labelOf,
} from '@/constants/crm'
import { formatBeijingTime } from '@/utils/beijingTime'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

function hasPerm(perm: string): boolean {
  return hasPermission(authStore.permissions, perm)
}

const loading = ref(false)
const generating = ref(false)
const saving = ref(false)
const productLoading = ref(false)
const items = ref<ContentItem[]>([])
const productOptions = ref<ProductListItem[]>([])
const contentSkills = ref<ContentSkill[]>([])
const modelOptions = ref<string[]>([])

const genForm = reactive({
  title: '',
  topic: '',
  platform: 'xhs',
  tone: '' as string,
  product_ids: [] as string[],
  requested_count: 3,
  skill_code: null as string | null,
  model_name: null as string | null,
  // 来自独立选题（?topic_id=）的上下文
  topic_id: null as string | null,
  content_batch_id: null as string | null,
})

const editVisible = ref(false)
const editItem = ref<ContentItem | null>(null)
const editForm = reactive({ title: '', body: '', hashtags: '' })

function statusTagType(state: string): 'success' | 'danger' | 'warning' | 'info' {
  if (state === 'published' || state === 'closed') return 'success'
  if (state === 'rejected') return 'danger'
  if (state === 'adopted' || state === 'produced' || state === 'tracking') return 'warning'
  return 'info'
}

function canEdit(item: ContentItem): boolean {
  return item.status !== 'rejected'
}

const topicItem = ref<ContentTopicItemDetail | null>(null)

function skillSourceLabel(code: string): string {
  const skill = contentSkills.value.find((item) => item.code === code)
  if (skill?.source_dna_label) return skill.source_dna_label
  if (code.startsWith('yuc-')) return '禹橙 DNA'
  if (code.startsWith('yanye-')) return '言也 DNA'
  if (code === 'content-default') return '禹橙 DNA（兼容回退）'
  if (code === 'topic-basic') return '禹橙 DNA（兼容回退）'
  return code
}

/**
 * 读取 ?topic_id= 预填生成表单：选题的标题/角度/人群/建议平台/关联产品
 * 都会带入，避免用户在工坊里重新抄一遍。
 */
async function loadTopicContext() {
  const topicId = route.query.topic_id
  if (typeof topicId !== 'string' || !topicId) return
  genForm.topic_id = topicId
  const batchId = route.query.batch_id
  if (typeof batchId === 'string' && batchId) genForm.content_batch_id = batchId
  try {
    const res = await contentApi.getTopicItem(topicId)
    topicItem.value = res.data
    if (res.data.platform || res.data.suggested_platform) {
      genForm.platform = res.data.platform || res.data.suggested_platform || genForm.platform
    }
    if (!genForm.title) genForm.title = res.data.title
    if (!genForm.topic) genForm.topic = res.data.topic_context || res.data.title
    if (!genForm.product_ids.length && res.data.related_product_ids?.length) {
      genForm.product_ids = [...res.data.related_product_ids]
    }
    // 预填关联产品前先把它们加进候选项，否则多选框显示不出标签
    await searchProducts(res.data.title)
  } catch {
    ElMessage.warning('未找到对应选题，已按普通批次处理')
  }
}

function toContentItem(result: ContentItemResult, platform: string): ContentItem {
  return {
    id: result.id,
    batch_id: '',
    item_type: 'text',
    platform,
    title: result.title,
    body: result.body,
    hashtags: result.hashtags,
    status: 'draft',
    display_state: 'draft',
    adopted_by: null,
    adopted_at: null,
    rejected_reason: null,
    produced_at: null,
    published_at: null,
    closed_at: null,
    edited: false,
    verified_payload: null,
    warnings: result.warnings,
    verification_gaps: result.verification_gaps || [],
    source_skill_code: result.source_skill_code || null,
    external_ref: null,
    model_provider: null,
    model_name: null,
    generation_version: '',
    create_time: new Date().toISOString(),
  }
}

async function searchProducts(query: string) {
  productLoading.value = true
  try {
    const res = await productApi.list({ keyword: query || undefined, page: 1, size: 20 })
    productOptions.value = res.data.list
  } catch {
    // ignore
  } finally {
    productLoading.value = false
  }
}

async function loadItems() {
  loading.value = true
  try {
    const res = await contentApi.listItems({ page: 1, size: 50 })
    items.value = res.data.list
  } catch {
    // 列表端点缺失时保持现有（可能是刚生成的）条目
  } finally {
    loading.value = false
  }
}

async function loadContentSkills() {
  try {
    const res = await contentApi.listSkills({ skill_type: 'content' })
    contentSkills.value = (res.data || []).filter((skill) => skill.selectable !== false)
  } catch {
    contentSkills.value = []
  }
}

async function loadModelOptions() {
  try {
    const res = await contentApi.listModels()
    modelOptions.value = res.data?.models || []
  } catch {
    modelOptions.value = []
  }
}

async function handleGenerate() {
  if (!genForm.title.trim() || !genForm.topic.trim()) {
    ElMessage.warning('请填写批次标题与主题')
    return
  }
  generating.value = true
  try {
    const res = await contentApi.generate({
      title: genForm.title,
      topic: genForm.topic,
      platform: genForm.platform,
      tone: genForm.tone || null,
      product_ids: genForm.product_ids,
      requested_count: genForm.requested_count,
      skill_code: genForm.skill_code,
      model_name: genForm.model_name,
      ...(genForm.topic_id ? { topic_item_id: genForm.topic_id } : {}),
    })
    const created = res.data.items.map((it) => toContentItem(it, genForm.platform))
    const existing = new Set(items.value.map((i) => i.id))
    items.value = [...created.filter((c) => !existing.has(c.id)), ...items.value]
    ElMessage.success(`已生成 ${created.length} 条内容`)
  } catch {
    // 拦截器已提示（含 503 AI 不可用）
  } finally {
    generating.value = false
  }
}

async function handleAdopt(item: ContentItem) {
  const needConfirm = item.warnings.length > 0
  if (needConfirm) {
    try {
      await ElMessageBox.confirm('该内容含合规警告，确认仍要采纳吗？', '采纳确认', {
        confirmButtonText: '确认采纳',
        cancelButtonText: '取消',
        type: 'warning',
      })
    } catch {
      return
    }
  }
  try {
    await contentApi.adopt(item.id, needConfirm)
    ElMessage.success('已采纳')
    updateLocalStatus(item.id, 'adopted', 'adopted')
  } catch {
    // ignore
  }
}

async function handleReject(item: ContentItem) {
  let reason = ''
  try {
    const { value } = await ElMessageBox.prompt('请填写不采纳原因', '不采纳', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '原因',
    })
    reason = value
  } catch {
    return
  }
  try {
    await contentApi.reject(item.id, reason)
    ElMessage.success('已标记为不采纳')
    updateLocalStatus(item.id, 'rejected', 'rejected')
  } catch {
    // ignore
  }
}

async function handleProduce(item: ContentItem) {
  try {
    await contentApi.produce(item.id)
    ElMessage.success('已标记制成')
    updateLocalStatus(item.id, 'produced', 'produced')
  } catch {
    // ignore
  }
}

async function handleDuplicate(item: ContentItem) {
  try {
    await contentApi.duplicate(item.id)
    ElMessage.success('已复制为新草稿')
    loadItems()
  } catch {
    // ignore
  }
}

function goPublish(item: ContentItem) {
  router.push({ path: '/content/publications', query: { item: item.id, platform: item.platform } })
}

function updateLocalStatus(id: string, status: string, displayState: string) {
  const target = items.value.find((i) => i.id === id)
  if (target) {
    target.status = status
    target.display_state = displayState
  }
}

function openEdit(item: ContentItem) {
  editItem.value = item
  editForm.title = item.title ?? ''
  editForm.body = item.body
  editForm.hashtags = item.hashtags.join(' ')
  editVisible.value = true
}

async function saveEdit() {
  if (!editItem.value) return
  const hashtags = editForm.hashtags
    .split(/[\s,，]+/)
    .map((t) => t.replace(/^#/, '').trim())
    .filter(Boolean)
  saving.value = true
  try {
    const payload: { title?: string; body?: string; hashtags?: string[] } = {
      title: editForm.title,
      hashtags,
    }
    if (editItem.value.status !== 'published') payload.body = editForm.body
    const res = await contentApi.updateItem(editItem.value.id, payload)
    const idx = items.value.findIndex((i) => i.id === editItem.value?.id)
    if (idx >= 0) items.value[idx] = { ...items.value[idx], ...res.data }
    ElMessage.success('已保存')
    editVisible.value = false
  } catch {
    // ignore
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadItems()
  loadContentSkills()
  loadModelOptions()
  searchProducts('')
  loadTopicContext()
})
</script>

<style scoped>
.gen-form {
  margin-bottom: 8px;
}

.topic-banner__meta {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: var(--pim-text-secondary);
}

.skill-option__dna {
  float: right;
  margin-left: 12px;
  font-size: 12px;
  color: var(--pim-text-secondary);
}

.gen-hint {
  margin-left: 12px;
  color: var(--pim-text-secondary);
  font-size: 12px;
}

.full-width {
  width: 100%;
}

.content-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.edit-hint {
  margin: 0;
  color: var(--pim-text-secondary);
  font-size: 12px;
}
</style>
