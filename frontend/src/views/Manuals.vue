<template>
  <div class="manuals-page">
    <section class="hero-card">
      <div>
        <p class="eyebrow">
          Knowledge Base
        </p>
        <h2>产品知识库</h2>
        <p>上传 PDF/DOCX 说明书，关联产品后解析、索引，并用可追溯来源回答问题。</p>
      </div>
      <el-button
        type="primary"
        @click="loadManuals"
      >
        刷新状态
      </el-button>
    </section>

    <el-row :gutter="16">
      <el-col
        :xs="24"
        :lg="9"
      >
        <el-card class="panel-card">
          <template #header>
            上传并创建说明书
          </template>
          <el-form label-position="top">
            <el-form-item label="关联产品 ID">
              <el-input
                v-model="form.productId"
                placeholder="请输入已存在的 product_id"
              />
            </el-form-item>
            <el-form-item label="文档类型">
              <el-select
                v-model="form.docType"
                style="width: 100%;"
              >
                <el-option
                  label="说明书"
                  value="manual"
                />
                <el-option
                  label="规格书"
                  value="spec"
                />
                <el-option
                  label="数据表"
                  value="datasheet"
                />
                <el-option
                  label="证书"
                  value="certificate"
                />
                <el-option
                  label="其他"
                  value="other"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="PDF/DOCX 附件">
              <input
                type="file"
                accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                @change="onFileChange"
              >
              <p
                v-if="selectedFile"
                class="file-name"
              >
                {{ selectedFile.name }}
              </p>
            </el-form-item>
            <el-button
              type="primary"
              :loading="uploading"
              @click="createManual"
            >
              上传并创建
            </el-button>
          </el-form>
        </el-card>
      </el-col>

      <el-col
        :xs="24"
        :lg="15"
      >
        <el-card class="panel-card">
          <template #header>
            说明书状态
          </template>
          <el-table
            :data="manuals"
            style="width: 100%;"
            empty-text="暂无说明书"
          >
            <el-table-column
              prop="doc_type"
              label="类型"
              width="90"
            />
            <el-table-column
              prop="product_id"
              label="产品"
              min-width="180"
              show-overflow-tooltip
            />
            <el-table-column
              label="解析"
              width="110"
            >
              <template #default="scope">
                <el-tag :type="statusType(scope.row.parse_status)">
                  {{ scope.row.parse_status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              label="索引"
              width="110"
            >
              <template #default="scope">
                <el-tag :type="statusType(scope.row.index_status)">
                  {{ scope.row.index_status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              label="解析器"
              min-width="120"
            >
              <template #default="scope">
                {{ scope.row.parser_name || '-' }} {{ scope.row.parser_version || '' }}
              </template>
            </el-table-column>
            <el-table-column
              label="失败原因"
              min-width="180"
              show-overflow-tooltip
            >
              <template #default="scope">
                {{ scope.row.parse_error || scope.row.index_error || '-' }}
              </template>
            </el-table-column>
            <el-table-column
              label="操作"
              width="210"
              fixed="right"
            >
              <template #default="scope">
                <el-button
                  v-if="canEditProduct && scope.row.parse_status === 'ocr_required'"
                  size="small"
                  type="warning"
                  :loading="busyId === scope.row.id"
                  @click="ocrManual(scope.row.id)"
                >
                  OCR
                </el-button>
                <el-button
                  v-if="canEditProduct"
                  size="small"
                  :loading="busyId === scope.row.id"
                  @click="parseManual(scope.row.id)"
                >
                  解析
                </el-button>
                <el-button
                  v-if="canIndex"
                  size="small"
                  type="primary"
                  :loading="busyId === scope.row.id"
                  @click="indexManual(scope.row.id)"
                >
                  索引
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="panel-card rag-card">
      <template #header>
        RAG 问答
      </template>
      <el-form label-position="top">
        <el-row :gutter="12">
          <el-col
            :xs="24"
            :md="8"
          >
            <el-form-item label="可选产品 ID 过滤">
              <el-input
                v-model="rag.productId"
                placeholder="留空则搜索全部已索引说明书"
              />
            </el-form-item>
          </el-col>
          <el-col
            :xs="24"
            :md="16"
          >
            <el-form-item label="问题">
              <el-input
                v-model="rag.query"
                placeholder="例如：这款产品支持哪些用电标准？"
                @keydown.enter="askRag"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-button
          type="primary"
          :loading="rag.loading"
          @click="askRag"
        >
          提问
        </el-button>
      </el-form>

      <el-alert
        v-if="rag.error"
        type="warning"
        :closable="false"
        show-icon
        class="answer-box"
        :title="rag.error"
      />
      <div
        v-if="rag.answer"
        class="answer-box"
      >
        <h3>{{ rag.insufficient ? '资料不足以确认' : '回答' }}</h3>
        <p>{{ rag.answer }}</p>
        <div
          v-if="rag.sources.length"
          class="sources"
        >
          <h4>Sources</h4>
          <article
            v-for="source in rag.sources"
            :key="source.chunk_id"
            class="source-card"
          >
            <div class="source-meta">
              <el-tag size="small">
                score {{ source.score }}
              </el-tag>
              <span>产品 {{ source.product_id }}</span>
              <span>chunk #{{ source.chunk_index }}</span>
            </div>
            <p>{{ truncate(source.chunk_text) }}</p>
          </article>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { fileApi, manualApi } from '@/api'
import type { ManualListResponse, ProductManual, RagAnswerResponse, RagSource } from '@/types/manuals'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'

const authStore = useAuthStore()
const canEditProduct = computed(() => hasPermission(authStore.userPermissions, 'product:edit'))
const canIndex = computed(() =>
  authStore.userRoleCode === 'admin' && hasPermission(authStore.userPermissions, 'ai:use')
)

const manuals = ref<ProductManual[]>([])
const selectedFile = ref<File | null>(null)
const uploading = ref(false)
const busyId = ref('')

const form = reactive({ productId: '', docType: 'manual' })
const rag = reactive({
  productId: '',
  query: '',
  answer: '',
  sources: [] as RagSource[],
  insufficient: false,
  loading: false,
  error: '',
})

function statusType(status: string) {
  if (status === 'indexed' || status === 'parsed') return 'success'
  if (status === 'processing') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}

function truncate(text: string) {
  return text.length > 180 ? `${text.slice(0, 180)}...` : text
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] || null
}

async function loadManuals() {
  const res = await manualApi.list({ page: 1, size: 50 }) as { data: ManualListResponse }
  manuals.value = res.data.list
}

async function createManual() {
  if (!form.productId || !selectedFile.value) {
    ElMessage.warning('请填写产品 ID 并选择 PDF/DOCX 文件')
    return
  }
  uploading.value = true
  try {
    const payload = new FormData()
    payload.append('file', selectedFile.value)
    const uploadRes = await fileApi.upload(payload) as { data: { attachment_id: string } }
    await manualApi.create({
      product_id: form.productId,
      attachment_id: uploadRes.data.attachment_id,
      doc_type: form.docType,
    })
    ElMessage.success('说明书已创建，请触发解析')
    selectedFile.value = null
    await loadManuals()
  } catch {
    ElMessage.error('说明书创建失败')
  } finally {
    uploading.value = false
  }
}

async function parseManual(id: string) {
  busyId.value = id
  try {
    await manualApi.parse(id)
    ElMessage.success('解析完成')
    await loadManuals()
  } catch {
    ElMessage.error('解析失败，请查看失败原因')
    await loadManuals()
  } finally {
    busyId.value = ''
  }
}

async function indexManual(id: string) {
  busyId.value = id
  try {
    await manualApi.index(id)
    ElMessage.success('索引完成')
    await loadManuals()
  } catch {
    ElMessage.error('索引失败，请查看失败原因')
    await loadManuals()
  } finally {
    busyId.value = ''
  }
}

async function ocrManual(id: string) {
  busyId.value = id
  try {
    await manualApi.ocr(id)
    ElMessage.success('OCR 识别完成')
    await loadManuals()
  } catch {
    ElMessage.error('OCR 识别失败，请查看失败原因')
    await loadManuals()
  } finally {
    busyId.value = ''
  }
}

async function askRag() {
  if (!rag.query.trim()) return
  rag.loading = true
  rag.error = ''
  rag.answer = ''
  rag.sources = []
  try {
    const res = await manualApi.answer({
      query: rag.query.trim(),
      product_id: rag.productId || undefined,
      top_k: 6,
      min_score: 0.65,
    }) as { data: RagAnswerResponse }
    rag.answer = res.data.answer || '资料不足以确认'
    rag.sources = res.data.sources || []
    rag.insufficient = res.data.insufficient_sources || rag.sources.length === 0
  } catch {
    rag.error = 'AI 服务未配置或暂时不可用，核心产品资料仍可查看'
  } finally {
    rag.loading = false
  }
}

onMounted(loadManuals)
</script>

<style scoped>
.manuals-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hero-card {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  padding: 24px;
  border-radius: 18px;
  color: #fff;
  background: linear-gradient(135deg, #183a5a, #0f766e);
}

.hero-card h2 {
  margin: 4px 0 8px;
  font-size: 28px;
}

.eyebrow {
  margin: 0;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  opacity: 0.75;
}

.panel-card {
  border-radius: 14px;
}

.file-name {
  margin: 8px 0 0;
  color: #606266;
}

.rag-card {
  margin-bottom: 16px;
}

.answer-box {
  margin-top: 16px;
}

.sources {
  display: grid;
  gap: 10px;
}

.source-card {
  padding: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 12px;
  background: #fafafa;
}

.source-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  color: #606266;
  font-size: 12px;
}

@media (max-width: 768px) {
  .hero-card {
    align-items: stretch;
    flex-direction: column;
    padding: 18px;
  }
}
</style>
