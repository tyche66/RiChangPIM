<template>
  <div class="crm-page">
    <el-card class="crm-card">
      <template #header>
        <div class="crm-card__header">
          <span class="crm-card__title">独立选题</span>
          <div class="crm-card__actions">
            <el-button
              class="crm-btn"
              :loading="loading"
              @click="loadRuns"
            >
              刷新
            </el-button>
          </div>
        </div>
      </template>

      <el-alert
        v-if="!hasPerm('content:generate')"
        type="info"
        :closable="false"
        title="需要 content:generate 权限才能创建选题"
        class="crm-alert"
      />

      <el-form
        v-if="hasPerm('content:generate')"
        :model="genForm"
        label-width="88px"
        class="gen-form"
      >
        <el-row :gutter="16">
          <el-col :span="6">
            <el-form-item
              label="选题 Skill"
            >
              <el-select
                v-model="genForm.skill_code"
                class="crm-select"
                clearable
                placeholder="自动选择"
              >
                <el-option label="自动选择" :value="null" />
                <el-option
                  v-for="skill in topicSkills"
                  :key="skill.code"
                  :label="skill.source_dna_label || skill.name"
                  :value="skill.code"
                />
              </el-select>
              <div class="crm-hint">
                仅展示禹橙 DNA与言也 DNA；未选择时由模型自动选择
              </div>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="平台">
              <el-select
                v-model="genForm.platform"
                class="crm-select"
                clearable
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
          <el-col :span="6">
            <el-form-item label="语气">
              <el-select
                v-model="genForm.tone"
                class="crm-select"
                clearable
              >
                <el-option
                  v-for="opt in CONTENT_TONE_OPTIONS"
                  :key="opt"
                  :label="opt"
                  :value="opt"
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
        </el-row>

        <el-form-item
          label="主题"
          required
        >
          <el-input
            v-model="genForm.topic"
            type="textarea"
            :rows="2"
            class="crm-input"
            placeholder="如：现代办公空间的弧形会议桌怎么选"
          />
        </el-form-item>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="关联产品">
              <el-select
                v-model="genForm.product_ids"
                class="crm-select"
                multiple
                filterable
                remote
                reserve-keyword
                :remote-method="searchProducts"
                :loading="productLoading"
                placeholder="可留空"
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
            <el-form-item label="选题数量">
              <el-input-number
                v-model="genForm.requested_count"
                :min="1"
                :max="10"
              />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-button
              type="primary"
              class="crm-btn"
              :loading="generating"
              @click="handleCreateRun"
            >
              生成选题
            </el-button>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <el-card class="crm-card">
      <template #header>
        <div class="crm-card__header">
          <span class="crm-card__title">选题列表</span>
          <span
            v-if="currentRun"
            class="topic-run__meta"
          >
            <el-tag :type="runStatusTagType(currentRun.status)">
              {{ runStatusLabel(currentRun.status) }}
            </el-tag>
            <span v-if="currentRun.model_name">{{ currentRun.model_name }}</span>
            <span v-if="currentRun.latency_ms != null">{{ currentRun.latency_ms }}ms</span>
            <span v-if="currentRun.skill_code">来源：{{ skillLabel(currentRun.skill_code) }}</span>
          </span>
        </div>
      </template>

      <el-alert
        v-if="currentRun && currentRun.status === 'failed'"
        type="error"
        :closable="false"
        :title="`生成失败：${currentRun.error_msg || '未知原因'}`"
        class="crm-alert"
      />

      <div
        v-if="currentRun && currentRun.items.length"
        class="topic-items"
      >
        <div
          v-for="item in currentRun.items"
          :key="item.id"
          class="topic-item"
        >
          <div class="topic-item__head">
            <span class="topic-item__title">{{ item.title }}</span>
            <el-tag :type="statusTagType(item.status)">
              {{ statusLabel(item.status) }}
            </el-tag>
          </div>
          <p
            v-if="item.angle"
            class="topic-item__angle"
          >
            <b>角度：</b>{{ item.angle }}
          </p>
          <p
            v-if="item.audience"
            class="topic-item__meta"
          >
            <b>人群：</b>{{ item.audience }}
          </p>
          <p
            v-if="item.reason"
            class="topic-item__meta"
          >
            <b>理由：</b>{{ item.reason }}
          </p>
          <p
            v-if="item.suggested_platform"
            class="topic-item__meta"
          >
            <b>建议平台：</b>{{ item.suggested_platform }}
          </p>
          <p v-if="item.pillar_code" class="topic-item__meta">
            <b>内容支柱：</b>{{ pillarLabel(item.pillar_code) }}（{{ item.pillar_code }}）
          </p>
          <p v-if="item.source_skill_code" class="topic-item__meta">
            <b>DNA：</b>{{ skillLabel(item.source_skill_code) }}
          </p>
          <p v-if="item.verification_gaps?.length" class="topic-item__meta">
            <b>待核验：</b>{{ item.verification_gaps.join('；') }}
          </p>
          <div class="topic-item__actions">
            <el-button
              v-if="hasPerm('content:adopt') && item.status === 'draft'"
              size="small"
              type="primary"
              @click="handleAdopt(item)"
            >
              采纳
            </el-button>
            <el-button
              v-if="hasPerm('content:adopt') && item.status === 'draft'"
              size="small"
              @click="handleReject(item)"
            >
              不采纳
            </el-button>
            <el-button
              v-if="item.status === 'adopted'"
              size="small"
              type="primary"
              plain
              @click="handleUse(item)"
            >
              带去内容工坊
            </el-button>
          </div>
        </div>
      </div>
      <el-empty
        v-else-if="!loading && currentRun && currentRun.status === 'failed'"
        description="本次生成失败，可调整主题后重试"
      />
      <el-empty
        v-else-if="!loading"
        description="暂无选题，填写主题后可自动选择 DNA 来源"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { contentApi, type ContentSkill, type ContentTopicItem, type ContentTopicRun } from '@/api/content'
import { productApi } from '@/api'
import { hasPermission } from '@/types/permissions'
import { useAuthStore } from '@/stores/auth'

const CONTENT_PLATFORM_MAP: Record<string, string> = {
  xhs: '小红书',
  douyin: '抖音',
  moments: '朋友圈',
  seo: 'SEO/官网',
  other: '其他',
}
const CONTENT_TONE_OPTIONS = ['种草', '测评', '干货', '故事']

const router = useRouter()
const authStore = useAuthStore()

const hasPerm = (perm: string) => hasPermission(authStore.permissions, perm)

const loading = ref(false)
const generating = ref(false)
const productLoading = ref(false)
const productOptions = ref<Array<{ id: string; product_name: string; product_no: string }>>([])
const topicSkills = ref<ContentSkill[]>([])
const modelOptions = ref<string[]>([])
const currentRun = ref<ContentTopicRun | null>(null)

const genForm = reactive({
  skill_code: null as string | null,
  model_name: null as string | null,
  topic: '',
  platform: '',
  tone: '',
  product_ids: [] as string[],
  requested_count: 3,
})

const statusLabel = (status: string) => {
  const map: Record<string, string> = {
    draft: '草稿',
    adopted: '已采纳',
    rejected: '不采纳',
    used: '已用于生成',
  }
  return map[status] || status
}

const skillLabel = (code: string | null | undefined) => {
  const skill = topicSkills.value.find((item) => item.code === code)
  if (code === 'topic-basic') return '禹橙 DNA（兼容回退）'
  if (code === 'yuc-topic') return '禹橙 DNA'
  if (code === 'yanye-topic') return '言也 DNA'
  return skill?.source_dna_label || skill?.name || code || '自动选择'
}

const pillarLabel = (code: string) => ({
  A: '办公空间解决方案',
  B: '真实项目与安装案例',
  C: '产品知识与选型避坑',
  D: '交付安装与协同',
  E: '本地服务与客户沟通',
}[code] || code)

const runStatusLabel = (status: string) => {
  const map: Record<string, string> = {
    running: '生成中',
    done: '已完成',
    failed: '失败',
    pending: '待生成',
  }
  return map[status] || status
}

const statusTagType = (status: string) => {
  const map: Record<string, string> = {
    draft: 'info',
    adopted: 'success',
    rejected: 'danger',
    used: 'warning',
  }
  return map[status] || 'info'
}

const runStatusTagType = (status: string) => {
  const map: Record<string, string> = {
    running: 'warning',
    done: 'success',
    failed: 'danger',
    pending: 'info',
  }
  return map[status] || 'info'
}

async function loadSkills() {
  try {
    const res = await contentApi.listSkills({ skill_type: 'topic' })
    topicSkills.value = (res.data || []).filter((skill) => skill.selectable !== false)
  } catch {
    topicSkills.value = []
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

async function loadRuns() {
  loading.value = true
  try {
    const res = await contentApi.listTopicRuns({ page: 1, size: 1 })
    const runs = res.data?.list || []
    if (runs.length) {
      const detail = await contentApi.getTopicRun(runs[0].id)
      currentRun.value = detail.data
    }
  } catch {
    currentRun.value = null
  } finally {
    loading.value = false
  }
}

async function handleCreateRun() {
  if (!genForm.topic.trim()) {
    ElMessage.warning('请填写主题')
    return
  }
  generating.value = true
  try {
    const res = await contentApi.createTopicRun({
      skill_code: genForm.skill_code,
      model_name: genForm.model_name,
      topic: genForm.topic.trim(),
      platform: genForm.platform || null,
      tone: genForm.tone || null,
      product_ids: genForm.product_ids,
      requested_count: genForm.requested_count,
    })
    currentRun.value = res.data
    if (currentRun.value?.status === 'done' && currentRun.value.items.length) {
      ElMessage.success(`已生成 ${currentRun.value.items.length} 条选题`)
    } else {
      ElMessage.warning('本次没有生成有效选题，请调整主题后重试')
    }
  } catch (error: unknown) {
    const detail = (error as { response?: { data?: { detail?: { msg?: string } } } })?.response
      ?.data?.detail
    ElMessage.error(detail?.msg || '选题生成失败')
    // 生成失败后刷新一次，保证列表显示最新一次运行的失败原因
    loadRuns()
  } finally {
    generating.value = false
  }
}

async function handleAdopt(item: ContentTopicItem) {
  try {
    const res = await contentApi.adoptTopicItem(item.id)
    if (currentRun.value) {
      currentRun.value.items = currentRun.value.items.map((i) =>
        i.id === item.id ? res.data : i,
      )
    }
    ElMessage.success('已采纳，可带去内容工坊生成正文')
  } catch {
    ElMessage.error('采纳失败')
  }
}

async function handleReject(item: ContentTopicItem) {
  try {
    const { value } = await ElMessageBox.prompt('请输入不采纳原因（可留空）', '不采纳', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    const res = await contentApi.rejectTopicItem(item.id, value || undefined)
    if (currentRun.value) {
      currentRun.value.items = currentRun.value.items.map((i) =>
        i.id === item.id ? res.data : i,
      )
    }
  } catch {
    // 用户取消
  }
}

function handleUse(item: ContentTopicItem) {
  // 带上 topic_id（预填用）与 content_batch_id（工坊回写用）
  router.push({
    path: '/content/workshop',
    query: {
      topic_id: item.id,
      topic: item.title,
      ...(item.content_batch_id ? { batch_id: item.content_batch_id } : {}),
    },
  })
}

async function searchProducts(keyword: string) {
  productLoading.value = true
  try {
    const res = await productApi.list({ keyword: keyword || undefined, page: 1, size: 20 })
    productOptions.value = (res.data?.list || []).map((p: { id: string; product_name: string; product_no: string }) => ({
      id: p.id,
      product_name: p.product_name,
      product_no: p.product_no,
    }))
  } catch {
    productOptions.value = []
  } finally {
    productLoading.value = false
  }
}

onMounted(() => {
  loadSkills()
  loadModelOptions()
  loadRuns()
  searchProducts('')
})
</script>

<style scoped>
.topic-items {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.topic-item {
  padding: 12px;
  border: 1px solid var(--color-border, #ebeef5);
  border-radius: 6px;
}

.topic-item__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.topic-run__meta {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--color-muted-foreground, #606266);
}

.topic-item__title {
  font-weight: 600;
}

.topic-item__angle,
.topic-item__meta {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--color-muted-foreground, #606266);
}

.topic-item__actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
}
</style>
