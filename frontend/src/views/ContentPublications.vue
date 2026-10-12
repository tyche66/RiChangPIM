<template>
  <div class="crm-page">
    <el-card class="crm-card">
      <template #header>
        <div class="crm-card__header">
          <span class="crm-card__title">发布与曝光</span>
          <div class="crm-card__actions">
            <input
              ref="importInput"
              type="file"
              accept=".xlsx"
              class="hidden-input"
              @change="onImportFile"
            >
            <el-button
              v-if="hasPerm('content:metric')"
              class="crm-btn"
              :loading="importing"
              @click="triggerImport"
            >
              Excel 导入曝光
            </el-button>
          </div>
        </div>
      </template>

      <el-tabs v-model="activeTab">
        <!-- 发布登记 -->
        <el-tab-pane
          v-if="hasPerm('content:publish')"
          label="发布登记"
          name="register"
        >
          <el-form
            :model="publishForm"
            label-width="96px"
            class="publish-form"
          >
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item
                  label="内容条目"
                  required
                >
                  <el-select
                    v-model="publishForm.content_item_id"
                    class="crm-select"
                    filterable
                    allow-create
                    default-first-option
                    placeholder="选择或输入条目 ID"
                  >
                    <el-option
                      v-for="it in itemOptions"
                      :key="it.id"
                      :label="it.title || it.id"
                      :value="it.id"
                    />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="平台">
                  <el-select
                    v-model="publishForm.platform"
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
              <el-col :span="12">
                <el-form-item label="账号">
                  <el-input
                    v-model="publishForm.account_name"
                    class="crm-input"
                    placeholder="发布账号（可选）"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="发布时间">
                  <el-date-picker
                    v-model="publishForm.published_at"
                    type="datetime"
                    class="full-width"
                    placeholder="默认当前时间"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="24">
                <el-form-item
                  label="发布链接"
                  required
                >
                  <el-input
                    v-model="publishForm.publish_url"
                    class="crm-input"
                    placeholder="https://…"
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item>
              <el-button
                type="primary"
                class="crm-btn crm-btn--primary"
                :loading="publishing"
                @click="submitPublish"
              >
                登记发布
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- 曝光录入 -->
        <el-tab-pane
          v-if="hasPerm('content:metric')"
          label="曝光录入"
          name="metric"
        >
          <el-form
            :model="metricForm"
            label-width="96px"
            class="publish-form"
          >
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item
                  label="发布记录"
                  required
                >
                  <el-select
                    v-model="metricForm.publication_id"
                    class="crm-select"
                    filterable
                    allow-create
                    default-first-option
                    placeholder="选择或输入发布 ID"
                  >
                    <el-option
                      v-for="p in publications"
                      :key="p.id"
                      :label="`${labelOf(CONTENT_PLATFORM_MAP, p.platform)} · ${p.publish_url}`"
                      :value="p.id"
                    />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="采集日期">
                  <el-date-picker
                    v-model="metricForm.captured_date"
                    type="date"
                    value-format="YYYY-MM-DD"
                    class="full-width"
                    placeholder="默认今天（同日 upsert）"
                  />
                </el-form-item>
              </el-col>
              <el-col
                v-for="field in metricFields"
                :key="field.key"
                :span="8"
              >
                <el-form-item :label="field.label">
                  <el-input-number
                    v-model="metricForm[field.key]"
                    :min="0"
                    :controls="false"
                    class="full-width"
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item>
              <el-button
                type="primary"
                class="crm-btn crm-btn--primary"
                :loading="savingMetric"
                @click="submitMetric"
              >
                保存曝光
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- 发布列表 -->
        <el-tab-pane
          label="发布列表"
          name="list"
        >
          <p
            v-if="!publications.length"
            class="crm-empty"
          >
            暂无发布记录
          </p>
          <el-table
            v-else
            :data="publications"
            class="crm-table"
            stripe
          >
            <el-table-column
              label="平台"
              width="100"
            >
              <template #default="{ row }">
                {{ labelOf(CONTENT_PLATFORM_MAP, row.platform) }}
              </template>
            </el-table-column>
            <el-table-column
              label="标题"
              min-width="160"
              show-overflow-tooltip
            >
              <template #default="{ row }">
                {{ row.item_title || row.content_item_id }}
              </template>
            </el-table-column>
            <el-table-column
              label="链接"
              min-width="180"
              show-overflow-tooltip
            >
              <template #default="{ row }">
                <a
                  :href="row.publish_url"
                  target="_blank"
                  rel="noopener noreferrer"
                >{{ row.publish_url }}</a>
              </template>
            </el-table-column>
            <el-table-column
              label="发布时间"
              width="170"
            >
              <template #default="{ row }">
                <span class="crm-mono">{{ formatBeijingTime(row.published_at) }}</span>
              </template>
            </el-table-column>
            <el-table-column
              label="曝光/点赞/评论/留资"
              min-width="180"
            >
              <template #default="{ row }">
                <span v-if="row.latest_metrics">
                  {{ num(row.latest_metrics.views) }} / {{ num(row.latest_metrics.likes) }} /
                  {{ num(row.latest_metrics.comments) }} / {{ num(row.latest_metrics.leads) }}
                </span>
                <span
                  v-else
                  class="crm-mono"
                >待录入</span>
              </template>
            </el-table-column>
            <el-table-column
              v-if="hasPerm('content:metric')"
              label="操作"
              width="120"
              align="center"
            >
              <template #default="{ row }">
                <el-button
                  size="small"
                  text
                  class="crm-link"
                  @click="fillMetric(row)"
                >
                  录入曝光
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 导入回执 -->
    <el-dialog
      v-model="receiptVisible"
      title="导入回执"
      width="640px"
      align-center
    >
      <el-descriptions
        v-if="receipt"
        :column="4"
        border
      >
        <el-descriptions-item label="总数">
          {{ receipt.total }}
        </el-descriptions-item>
        <el-descriptions-item label="新增">
          {{ receipt.created }}
        </el-descriptions-item>
        <el-descriptions-item label="更新">
          {{ receipt.updated }}
        </el-descriptions-item>
        <el-descriptions-item label="失败">
          {{ receipt.failed }}
        </el-descriptions-item>
      </el-descriptions>
      <el-table
        v-if="receipt && receipt.errors.length"
        :data="receipt.errors"
        class="crm-table receipt-table"
      >
        <el-table-column
          prop="row"
          label="行"
          width="70"
        />
        <el-table-column
          prop="publish_url"
          label="发布链接"
          show-overflow-tooltip
        />
        <el-table-column
          prop="error_msg"
          label="原因"
          width="180"
        />
      </el-table>
      <a
        v-if="receipt?.error_file_url"
        :href="receipt.error_file_url"
        class="error-file"
      >下载失败行文件</a>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  contentApi,
  type ContentItem,
  type ContentPublication,
  type MetricImportResult,
} from '@/api/content'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'
import { CONTENT_PLATFORM_MAP, labelOf } from '@/constants/crm'
import { formatBeijingTime } from '@/utils/beijingTime'

const route = useRoute()
const authStore = useAuthStore()

function hasPerm(perm: string): boolean {
  return hasPermission(authStore.permissions, perm)
}

type MetricKey = 'views' | 'likes' | 'comments' | 'shares' | 'favorites' | 'leads'

const metricFields: Array<{ key: MetricKey; label: string }> = [
  { key: 'views', label: '播放/浏览' },
  { key: 'likes', label: '点赞' },
  { key: 'comments', label: '评论' },
  { key: 'shares', label: '分享' },
  { key: 'favorites', label: '收藏' },
  { key: 'leads', label: '留资' },
]

const activeTab = ref('list')
const publishing = ref(false)
const savingMetric = ref(false)
const importing = ref(false)
const publications = ref<ContentPublication[]>([])
const itemOptions = ref<ContentItem[]>([])
const importInput = ref<HTMLInputElement | null>(null)
const receiptVisible = ref(false)
const receipt = ref<MetricImportResult | null>(null)

const publishForm = reactive({
  content_item_id: '',
  platform: 'xhs',
  account_name: '',
  publish_url: '',
  published_at: null as Date | null,
})

const metricForm = reactive<Record<MetricKey | 'publication_id' | 'captured_date', string | number | null>>({
  publication_id: '',
  captured_date: null,
  views: null,
  likes: null,
  comments: null,
  shares: null,
  favorites: null,
  leads: null,
})

function num(value: number | null | undefined): string {
  return value == null ? '—' : String(value)
}

async function loadPublications() {
  try {
    const res = await contentApi.listPublications({ page: 1, size: 50 })
    publications.value = res.data.list
  } catch {
    // 列表端点缺失时保持空态
  }
}

async function loadItems() {
  try {
    const res = await contentApi.listItems({ page: 1, size: 50 })
    itemOptions.value = res.data.list
  } catch {
    // ignore
  }
}

async function submitPublish() {
  if (!publishForm.content_item_id) {
    ElMessage.warning('请选择内容条目')
    return
  }
  if (!publishForm.publish_url.trim()) {
    ElMessage.warning('请填写发布链接')
    return
  }
  publishing.value = true
  try {
    await contentApi.publish(publishForm.content_item_id, {
      platform: publishForm.platform,
      account_name: publishForm.account_name || null,
      publish_url: publishForm.publish_url,
      published_at: publishForm.published_at ? publishForm.published_at.toISOString() : null,
    })
    ElMessage.success('发布已登记')
    publishForm.content_item_id = ''
    publishForm.publish_url = ''
    activeTab.value = 'list'
    loadPublications()
  } catch {
    // ignore
  } finally {
    publishing.value = false
  }
}

async function submitMetric() {
  if (!metricForm.publication_id) {
    ElMessage.warning('请选择发布记录')
    return
  }
  savingMetric.value = true
  try {
    await contentApi.createMetric({
      publication_id: String(metricForm.publication_id),
      views: metricForm.views as number | null,
      likes: metricForm.likes as number | null,
      comments: metricForm.comments as number | null,
      shares: metricForm.shares as number | null,
      favorites: metricForm.favorites as number | null,
      leads: metricForm.leads as number | null,
      captured_date: metricForm.captured_date ? String(metricForm.captured_date) : null,
    })
    ElMessage.success('曝光已保存')
    loadPublications()
  } catch {
    // ignore
  } finally {
    savingMetric.value = false
  }
}

function fillMetric(pub: ContentPublication) {
  metricForm.publication_id = pub.id
  metricForm.views = pub.latest_metrics?.views ?? null
  metricForm.likes = pub.latest_metrics?.likes ?? null
  metricForm.comments = pub.latest_metrics?.comments ?? null
  metricForm.shares = pub.latest_metrics?.shares ?? null
  metricForm.favorites = pub.latest_metrics?.favorites ?? null
  metricForm.leads = pub.latest_metrics?.leads ?? null
  activeTab.value = 'metric'
}

function triggerImport() {
  importInput.value?.click()
}

async function onImportFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  importing.value = true
  try {
    const res = await contentApi.importMetrics(file)
    receipt.value = res.data
    receiptVisible.value = true
    loadPublications()
  } catch {
    // ignore
  } finally {
    importing.value = false
    input.value = ''
  }
}

onMounted(() => {
  loadPublications()
  loadItems()
  const itemId = route.query.item as string | undefined
  const platform = route.query.platform as string | undefined
  if (itemId) {
    publishForm.content_item_id = itemId
    activeTab.value = 'register'
  }
  if (platform && CONTENT_PLATFORM_MAP[platform]) {
    publishForm.platform = platform
  }
})
</script>

<style scoped>
.hidden-input {
  display: none;
}

.full-width {
  width: 100%;
}

.publish-form {
  max-width: 900px;
}

.receipt-table {
  margin-top: 16px;
}

.error-file {
  display: inline-block;
  margin-top: 12px;
  color: var(--pim-accent-solid);
}
</style>
