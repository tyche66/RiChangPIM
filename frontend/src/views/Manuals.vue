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
        class="capsule-btn capsule-btn-light"
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
        <el-card class="panel-card glass-card">
          <template #header>
            <span class="panel-title">上传并创建说明书</span>
          </template>
          <el-form label-position="top">
            <el-form-item label="关联产品 ID">
              <el-input
                v-model="form.productId"
                placeholder="请输入已存在的 product_id"
                class="capsule-input"
              />
            </el-form-item>
            <el-form-item label="文档类型">
              <el-select
                v-model="form.docType"
                class="capsule-select full-width"
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
              <div class="file-upload-wrap">
                <input
                  type="file"
                  accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  class="file-input"
                  @change="onFileChange"
                >
                <div
                  v-if="selectedFile"
                  class="file-name capsule-tag"
                >
                  {{ selectedFile.name }}
                </div>
              </div>
            </el-form-item>
            <el-button
              type="primary"
              :loading="uploading"
              class="capsule-btn capsule-btn-primary full-width"
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
        <el-card class="panel-card glass-card">
          <template #header>
            <span class="panel-title">说明书状态</span>
          </template>
          <div class="table-wrapper">
            <el-table
              :data="manuals"
              class="manuals-table"
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
                align="center"
              >
                <template #default="scope">
                  <el-tag
                    :type="statusType(scope.row.parse_status)"
                    class="capsule-tag"
                  >
                    {{ scope.row.parse_status }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                label="索引"
                width="110"
                align="center"
              >
                <template #default="scope">
                  <el-tag
                    :type="statusType(scope.row.index_status)"
                    class="capsule-tag"
                  >
                    {{ scope.row.index_status }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                label="解析器"
                min-width="120"
              >
                <template #default="scope">
                  <span class="mono-text">{{ scope.row.parser_name || '-' }} {{ scope.row.parser_version || '' }}</span>
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
                align="center"
              >
                <template #default="scope">
                  <el-button
                    v-if="canEditProduct && scope.row.parse_status === 'ocr_required'"
                    size="small"
                    type="warning"
                    :loading="busyId === scope.row.id"
                    class="capsule-btn btn-sm"
                    @click="ocrManual(scope.row.id)"
                  >
                    OCR
                  </el-button>
                  <el-button
                    v-if="canEditProduct"
                    size="small"
                    :loading="busyId === scope.row.id"
                    class="capsule-btn btn-sm"
                    @click="parseManual(scope.row.id)"
                  >
                    解析
                  </el-button>
                  <el-button
                    v-if="canIndex"
                    size="small"
                    type="primary"
                    :loading="busyId === scope.row.id"
                    class="capsule-btn btn-sm capsule-btn-primary"
                    @click="indexManual(scope.row.id)"
                  >
                    索引
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="panel-card glass-card rag-card">
      <template #header>
        <span class="panel-title">RAG 问答</span>
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
                class="capsule-input"
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
                class="capsule-input"
                @keydown.enter="askRag"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-button
          type="primary"
          :loading="rag.loading"
          class="capsule-btn capsule-btn-primary"
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
        class="answer-box glass-alert"
        :title="rag.error"
      />
      <div
        v-if="rag.answer"
        class="answer-box"
      >
        <h3 class="answer-title">
          {{ rag.insufficient ? '资料不足以确认' : '回答' }}
        </h3>
        <p class="answer-text">
          {{ rag.answer }}
        </p>
        <div
          v-if="rag.sources.length"
          class="sources"
        >
          <h4 class="sources-title">
            Sources
          </h4>
          <article
            v-for="source in rag.sources"
            :key="source.chunk_id"
            class="source-card glass-item"
          >
            <div class="source-meta">
              <el-tag
                size="small"
                class="capsule-tag"
              >
                score {{ source.score }}
              </el-tag>
              <span class="mono-text">产品 {{ source.product_id }}</span>
              <span class="mono-text">chunk #{{ source.chunk_index }}</span>
            </div>
            <p class="source-text">
              {{ truncate(source.chunk_text) }}
            </p>
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
/* ===== CSS Variables ===== */
.manuals-page {
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
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ===== Hero Card ===== */
.hero-card {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: center;
  padding: 28px 32px;
  border-radius: var(--radius-lg);
  color: #fff;
  background: linear-gradient(135deg, rgba(30, 50, 90, 0.92), rgba(15, 118, 110, 0.9));
  backdrop-filter: blur(10px);
  box-shadow: 0 8px 32px rgba(30, 50, 90, 0.2);
}

.hero-card h2 {
  margin: 6px 0 10px;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.5px;
}

.hero-card p {
  margin: 0;
  font-size: 14px;
  opacity: 0.85;
  line-height: 1.6;
  max-width: 500px;
}

.eyebrow {
  margin: 0;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  opacity: 0.7;
  font-size: 11px;
  font-weight: 600;
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
  padding: 20px;
}

.panel-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--brand-deep);
}

/* ===== Capsule Components ===== */
.capsule-input :deep(.el-input__wrapper) {
  border-radius: 20px;
  box-shadow: 0 0 0 1px rgba(30, 50, 90, 0.1) inset;
  padding: 4px 16px;
  transition: var(--transition-fast);
}

.capsule-input :deep(.el-input__wrapper):hover {
  box-shadow: 0 0 0 1px rgba(30, 50, 90, 0.25) inset;
}

.capsule-select :deep(.el-select__wrapper),
.capsule-select :deep(.el-input__wrapper) {
  border-radius: 20px;
  box-shadow: 0 0 0 1px rgba(30, 50, 90, 0.1) inset;
  padding: 4px 16px;
}

.capsule-btn {
  border-radius: 20px !important;
  padding: 8px 20px;
  font-weight: 500;
  transition: var(--transition-fast);
}

.capsule-btn:hover {
  transform: scale(1.03);
}

.capsule-btn:active {
  transform: scale(0.97);
}

.capsule-btn-primary {
  background: var(--brand-primary);
  border-color: var(--brand-primary);
}

.capsule-btn-primary:hover {
  background: var(--brand-deep);
  border-color: var(--brand-deep);
}

.capsule-btn-light {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(255, 255, 255, 0.4);
  color: #fff;
}

.capsule-btn-light:hover {
  background: rgba(255, 255, 255, 0.3);
  border-color: rgba(255, 255, 255, 0.5);
  color: #fff;
}

.btn-sm {
  padding: 5px 14px;
  font-size: 12px;
  border-radius: 16px !important;
}

.capsule-tag {
  border-radius: 12px;
  padding: 2px 10px;
  font-weight: 500;
}

.full-width {
  width: 100%;
}

/* ===== File Upload ===== */
.file-upload-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.file-input {
  width: 100%;
  padding: 8px 0;
  font-size: 13px;
  color: var(--text-primary);
}

.file-name {
  font-size: 12px;
  color: var(--text-secondary);
  word-break: break-all;
  padding: 4px 12px;
  background: var(--brand-lighter);
  display: inline-block;
}

/* ===== Table ===== */
.table-wrapper {
  overflow-x: auto;
  border-radius: var(--radius-md);
}

.manuals-table {
  width: 100%;
  border-radius: var(--radius-md);
  overflow: hidden;
}

.manuals-table :deep(.el-table__header-wrapper) {
  background: var(--brand-lighter);
}

.manuals-table :deep(.el-table__header th) {
  background: var(--brand-lighter);
  color: var(--text-primary);
  font-weight: 600;
  font-size: 13px;
}

.manuals-table :deep(.el-table__row:hover td) {
  background: var(--brand-lighter);
}

.mono-text {
  font-family: monospace;
  color: var(--text-secondary);
  font-size: 12px;
}

/* ===== RAG Answer ===== */
.rag-card {
  margin-bottom: 16px;
}

.answer-box {
  margin-top: 16px;
}

.glass-alert {
  border-radius: var(--radius-sm);
}

.answer-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--brand-deep);
  margin: 0 0 8px;
}

.answer-text {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.8;
  margin: 0 0 16px;
  padding: 14px 18px;
  background: var(--brand-light);
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--brand-primary);
}

.sources {
  display: grid;
  gap: 10px;
}

.sources-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0 0 8px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.glass-item {
  padding: 14px 16px;
  border: 1px solid rgba(30, 50, 90, 0.06);
  border-radius: var(--radius-md);
  background: var(--brand-lighter);
  transition: var(--transition-fast);
}

.glass-item:hover {
  background: var(--brand-light);
}

.source-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  color: var(--text-secondary);
  font-size: 11px;
  margin-bottom: 8px;
}

.source-text {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.7;
  margin: 0;
}

/* ===== Responsive ===== */
@media (max-width: 768px) {
  .manuals-page {
    padding: 8px;
  }

  .hero-card {
    align-items: stretch;
    flex-direction: column;
    padding: 20px;
  }

  .hero-card h2 {
    font-size: 22px;
  }

  .hero-card p {
    max-width: 100%;
  }

  .glass-card {
    border-radius: var(--radius-md);
  }

  .glass-card :deep(.el-card__header),
  .glass-card :deep(.el-card__body) {
    padding: 16px;
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
