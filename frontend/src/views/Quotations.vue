<template>
  <div class="quotations-page">
    <el-card class="glass-card">
      <template #header>
        <div class="card-header">
          <span class="page-title">报价管理</span>
        </div>
      </template>

      <el-form
        :inline="true"
        :model="queryParams"
        class="search-form"
      >
        <el-form-item label="方案ID">
          <el-input
            v-model="queryParams.proposal_id"
            placeholder="关联方案ID"
            clearable
            class="capsule-input search-input"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="queryParams.status"
            placeholder="全部"
            clearable
            class="capsule-select"
          >
            <el-option
              label="草稿"
              value="draft"
            />
            <el-option
              label="已确认"
              value="confirmed"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            class="capsule-btn capsule-btn-primary"
            @click="handleSearch"
          >
            查询
          </el-button>
          <el-button
            class="capsule-btn"
            @click="handleReset"
          >
            重置
          </el-button>
        </el-form-item>
      </el-form>

      <div class="table-wrapper">
        <el-table
          v-loading="loading"
          :data="quotations"
          border
          stripe
          class="quotation-table"
        >
          <el-table-column
            prop="quotation_no"
            label="报价单号"
            width="180"
          />
          <el-table-column
            prop="proposal_id"
            label="方案ID"
            width="240"
          />
          <el-table-column
            prop="total_amount"
            label="总金额"
            width="120"
            align="right"
          >
            <template #default="{ row }">
              <span class="price-text">¥{{ row.total_amount?.toFixed(2) }}</span>
            </template>
          </el-table-column>
          <el-table-column
            prop="status"
            label="状态"
            width="100"
            align="center"
          >
            <template #default="{ row }">
              <el-tag
                :type="row.status === 'confirmed' ? 'success' : 'info'"
                class="capsule-tag"
              >
                {{ row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="create_time"
            label="创建时间"
            width="170"
          >
            <template #default="{ row }">
              <span class="mono-text">{{ formatDate(row.create_time) }}</span>
            </template>
          </el-table-column>
          <el-table-column
            label="操作"
            width="220"
            fixed="right"
            align="center"
          >
            <template #default="{ row }">
              <el-button
                size="small"
                class="capsule-btn btn-sm"
                @click="handleView(row)"
              >
                查看
              </el-button>
              <el-button
                v-if="hasPerm('quotation:edit') && row.status !== 'confirmed'"
                size="small"
                class="capsule-btn btn-sm"
                @click="handleEdit(row)"
              >
                编辑
              </el-button>
              <el-button
                v-if="hasPerm('share:create')"
                size="small"
                type="warning"
                class="capsule-btn btn-sm"
                @click="handleShare(row)"
              >
                分享
              </el-button>
              <el-button
                size="small"
                type="info"
                class="capsule-btn btn-sm"
                @click="handleExportPdf(row)"
              >
                导出PDF
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-pagination
        v-model:current-page="queryParams.page"
        v-model:page-size="queryParams.size"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next, jumper"
        class="pagination-wrap"
        @current-change="fetchQuotations"
        @size-change="fetchQuotations"
      />
    </el-card>

    <!-- Create/Edit Quotation Dialog -->
    <el-dialog
      v-model="showQuotationDialog"
      :title="quotationMode === 'create' ? '创建报价单' : '编辑报价单'"
      class="glass-dialog"
      :close-on-click-modal="false"
    >
      <el-form
        ref="quotationFormRef"
        :model="quotationForm"
        :rules="quotationFormRules"
        label-width="120px"
      >
        <el-form-item
          label="关联方案ID"
          prop="proposal_id"
        >
          <el-input
            v-model="quotationForm.proposal_id"
            :disabled="quotationMode === 'edit'"
            class="capsule-input"
          />
        </el-form-item>
        <el-form-item
          label="税率"
          prop="tax_rate"
        >
          <el-input-number
            v-model="quotationForm.tax_rate"
            :min="0"
            :max="1"
            :step="0.01"
            :precision="2"
            class="capsule-number full-width"
          />
        </el-form-item>
        <el-form-item
          label="折扣率"
          prop="discount"
        >
          <el-input-number
            v-model="quotationForm.discount"
            :min="0"
            :max="1"
            :step="0.01"
            :precision="2"
            class="capsule-number full-width"
          />
        </el-form-item>
        <el-form-item label="有效期至">
          <el-date-picker
            v-model="quotationForm.valid_until"
            type="datetime"
            placeholder="选择有效期"
            class="capsule-date full-width"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button
          class="capsule-btn"
          @click="showQuotationDialog = false"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="quotationLoading"
          class="capsule-btn capsule-btn-primary"
          @click="handleQuotationSubmit"
        >
          确定
        </el-button>
      </template>
    </el-dialog>

    <!-- Share Dialog -->
    <el-dialog
      v-model="showShareDialog"
      title="创建分享链接"
      class="glass-dialog"
      :close-on-click-modal="false"
    >
      <el-form label-width="120px">
        <el-form-item label="分享类型">
          <el-select
            v-model="shareForm.share_type"
            disabled
            class="capsule-select full-width"
          >
            <el-option
              label="报价单"
              value="quotation"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="访问密码">
          <el-input
            v-model="shareForm.password"
            placeholder="留空则无需密码"
            class="capsule-input"
          />
        </el-form-item>
        <el-form-item label="有效期(小时)">
          <el-input-number
            v-model="shareForm.expire_hours"
            :min="1"
            :max="720"
            class="capsule-number full-width"
          />
        </el-form-item>
        <el-form-item label="最大访问次数">
          <el-input-number
            v-model="shareForm.max_access_count"
            :min="1"
            :max="1000"
            class="capsule-number full-width"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button
          class="capsule-btn"
          @click="showShareDialog = false"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="shareLoading"
          class="capsule-btn capsule-btn-primary"
          @click="handleShareSubmit"
        >
          生成链接
        </el-button>
      </template>
    </el-dialog>

    <!-- Share Result -->
    <el-dialog
      v-model="showShareResult"
      title="分享链接已生成"
      class="glass-dialog"
    >
      <el-alert
        type="success"
        :closable="false"
        class="share-alert"
      >
        请将以下链接发送给客户
      </el-alert>
      <el-input
        :model-value="shareResultUrl"
        readonly
        class="capsule-input share-url-input"
      >
        <template #append>
          <el-button
            class="capsule-btn capsule-btn-primary"
            @click="copyShareUrl"
          >
            复制
          </el-button>
        </template>
      </el-input>
      <div
        v-if="shareResultUrl"
        class="share-actions"
      >
        <el-button
          type="primary"
          class="capsule-btn capsule-btn-primary"
          @click="openShareUrl"
        >
          在新窗口打开
        </el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { quotationApi, shareApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'

const route = useRoute()
const authStore = useAuthStore()

function hasPerm(perm: string): boolean {
  return hasPermission(authStore.permissions, perm)
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

const loading = ref(false)
const quotations = ref<any[]>([])
const total = ref(0)
const showQuotationDialog = ref(false)
const quotationMode = ref<'create' | 'edit'>('create')
const quotationLoading = ref(false)
const quotationFormRef = ref<FormInstance>()
const showShareDialog = ref(false)
const showShareResult = ref(false)
const shareLoading = ref(false)
const shareResultUrl = ref('')

const queryParams = reactive({
  proposal_id: '',
  status: '',
  page: 1,
  size: 20,
})

const quotationForm = reactive({
  proposal_id: '',
  tax_rate: 0.13,
  discount: 1.0,
  valid_until: null as Date | null,
})

const quotationFormRules: FormRules = {
  proposal_id: [{ required: true, message: '请输入方案ID', trigger: 'blur' }],
}

const shareForm = reactive({
  share_type: 'quotation',
  target_id: '',
  creator_id: '',
  password: '',
  expire_hours: 24,
  max_access_count: 100,
})

const fetchQuotations = async () => {
  loading.value = true
  try {
    const params: Record<string, unknown> = { ...queryParams }
    if (!params.proposal_id) delete params.proposal_id
    if (!params.status) delete params.status
    const res = await quotationApi.list(params)
    quotations.value = res.data?.list || []
    total.value = res.data?.total || 0
  } catch {
    ElMessage.error('加载报价列表失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  queryParams.page = 1
  fetchQuotations()
}

const handleReset = () => {
  queryParams.proposal_id = ''
  queryParams.status = ''
  queryParams.page = 1
  fetchQuotations()
}

const handleView = (row: any) => {
  ElMessage.info(`查看报价单: ${row.quotation_no}`)
}

const handleEdit = (row: any) => {
  quotationMode.value = 'edit'
  quotationForm.proposal_id = row.proposal_id
  quotationForm.tax_rate = row.tax_rate
  quotationForm.discount = row.discount
  quotationForm.valid_until = row.valid_until ? new Date(row.valid_until) : null
  showQuotationDialog.value = true
}

const handleShare = (row: any) => {
  shareForm.target_id = row.id
  shareForm.creator_id = authStore.user?.id || ''
  showShareDialog.value = true
}

const handleQuotationSubmit = async () => {
  if (!quotationFormRef.value) return
  await quotationFormRef.value.validate(async (valid) => {
    if (!valid) return
    quotationLoading.value = true
    try {
      const payload: Record<string, unknown> = {
        proposal_id: quotationForm.proposal_id,
        tax_rate: quotationForm.tax_rate,
        discount: quotationForm.discount,
        items: [],
      }
      if (quotationForm.valid_until) {
        payload.valid_until = quotationForm.valid_until.toISOString()
      }
      await quotationApi.create(payload)
      ElMessage.success('操作成功')
      showQuotationDialog.value = false
      fetchQuotations()
    } catch {
      // error handled by interceptor
    } finally {
      quotationLoading.value = false
    }
  })
}

const handleShareSubmit = async () => {
  shareLoading.value = true
  try {
    const payload: Record<string, unknown> = {
      share_type: shareForm.share_type,
      target_id: shareForm.target_id,
      creator_id: shareForm.creator_id,
    }
    if (shareForm.password) payload.password = shareForm.password
    if (shareForm.expire_hours) payload.expire_hours = shareForm.expire_hours
    if (shareForm.max_access_count) payload.max_access_count = shareForm.max_access_count

    const res = await shareApi.create(payload)
    const data = res.data
    shareResultUrl.value = window.location.origin + data.share_url
    showShareDialog.value = false
    showShareResult.value = true
  } catch {
    // error handled by interceptor
  } finally {
    shareLoading.value = false
  }
}

const handleExportPdf = async (row: any) => {
  try {
    const pdf = await quotationApi.exportPdf(row.id)
    const url = URL.createObjectURL(new Blob([pdf], { type: 'application/pdf' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `${row.quotation_no || row.id}.pdf`
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('PDF 导出成功')
  } catch {
    ElMessage.error('PDF 导出失败')
  }
}

const copyShareUrl = () => {
  navigator.clipboard.writeText(shareResultUrl.value).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

const openShareUrl = () => {
  window.open(shareResultUrl.value, '_blank')
}

const prefillProposalId = computed(() => route.query.proposal_id as string | undefined)

onMounted(() => {
  if (prefillProposalId.value) {
    queryParams.proposal_id = prefillProposalId.value
    quotationForm.proposal_id = prefillProposalId.value
    quotationMode.value = 'create'
    showQuotationDialog.value = true
  }
  fetchQuotations()
})
</script>

<style scoped>
/* ===== CSS Variables ===== */
.quotations-page {
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
  padding: 20px 24px;
}

.glass-card :deep(.el-card__body) {
  padding: 20px 24px;
}

/* ===== Card Header ===== */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--brand-deep);
}

/* ===== Search Form ===== */
.search-form {
  margin-bottom: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.search-form :deep(.el-form-item) {
  margin-bottom: 8px;
}

.search-form :deep(.el-form-item__label) {
  color: var(--text-primary);
  font-weight: 500;
  font-size: 13px;
}

.search-input {
  width: 220px;
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

.capsule-number :deep(.el-input__wrapper) {
  border-radius: 20px;
}

.capsule-number :deep(.el-input-number__decrease),
.capsule-number :deep(.el-input-number__increase) {
  border-radius: 0;
}

.capsule-date :deep(.el-input__wrapper) {
  border-radius: 20px;
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

/* ===== Table ===== */
.table-wrapper {
  overflow-x: auto;
  border-radius: var(--radius-md);
}

.quotation-table {
  width: 100%;
  border-radius: var(--radius-md);
  overflow: hidden;
}

.quotation-table :deep(.el-table__header-wrapper) {
  background: var(--brand-lighter);
}

.quotation-table :deep(.el-table__header th) {
  background: var(--brand-lighter);
  color: var(--text-primary);
  font-weight: 600;
  font-size: 13px;
  padding: 14px 0;
}

.quotation-table :deep(.el-table__row td) {
  padding: 12px 0;
}

.quotation-table :deep(.el-table__row:hover td) {
  background: var(--brand-lighter);
}

.price-text {
  color: var(--brand-deep);
  font-weight: 600;
  font-family: monospace;
}

.mono-text {
  font-family: monospace;
  color: var(--text-secondary);
  font-size: 12px;
}

/* ===== Pagination ===== */
.pagination-wrap {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.pagination-wrap :deep(.el-pager li),
.pagination-wrap :deep(.el-pagination .btn-prev),
.pagination-wrap :deep(.el-pagination .btn-next) {
  border-radius: 50%;
  min-width: 32px;
  height: 32px;
  line-height: 32px;
  transition: var(--transition-fast);
}

.pagination-wrap :deep(.el-pager li.active),
.pagination-wrap :deep(.el-pager li.active:hover) {
  background: var(--brand-primary);
  color: #fff;
}

.pagination-wrap :deep(.el-pager li:hover:not(.active)),
.pagination-wrap :deep(.el-pagination .btn-prev:hover),
.pagination-wrap :deep(.el-pagination .btn-next:hover) {
  background: var(--brand-light);
}

/* ===== Glass Dialog ===== */
.glass-dialog :deep(.el-dialog) {
  border-radius: var(--radius-lg) !important;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(30, 50, 90, 0.15);
}

.glass-dialog :deep(.el-dialog__header) {
  background: linear-gradient(135deg, rgba(30, 50, 90, 0.06), rgba(30, 50, 90, 0.02));
  padding: 20px 24px 16px;
  margin-right: 0;
  border-bottom: 1px solid rgba(30, 50, 90, 0.06);
}

.glass-dialog :deep(.el-dialog__title) {
  color: var(--text-primary);
  font-weight: 700;
  font-size: 18px;
}

.glass-dialog :deep(.el-dialog__body) {
  padding: 24px;
}

.glass-dialog :deep(.el-dialog__footer) {
  padding: 16px 24px;
}

.full-width {
  width: 100%;
}

/* ===== Share ===== */
.share-alert {
  border-radius: var(--radius-sm);
  margin-bottom: 16px;
}

.share-url-input :deep(.el-input__wrapper) {
  border-radius: 20px;
}

.share-url-input :deep(.el-input-group__append) {
  border-radius: 0 20px 20px 0;
}

.share-actions {
  margin-top: 16px;
  display: flex;
  gap: 8px;
}

/* ===== Responsive ===== */
@media (max-width: 768px) {
  .quotations-page {
    padding: 8px;
  }

  .glass-card {
    border-radius: var(--radius-md);
  }

  .glass-card :deep(.el-card__header),
  .glass-card :deep(.el-card__body) {
    padding: 16px;
  }

  .search-form {
    flex-direction: column;
  }

  .search-form :deep(.el-form-item) {
    width: 100%;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
  }

  .search-form :deep(.el-form-item__content) {
    width: 100% !important;
    margin-left: 0 !important;
  }

  .search-input {
    width: 100%;
  }

  .search-form :deep(.el-form-item:last-child) {
    display: flex;
    flex-direction: row;
    gap: 8px;
    width: 100%;
  }

  .search-form :deep(.el-form-item:last-child .el-form-item__content) {
    display: flex;
    gap: 8px;
  }

  .search-form :deep(.el-form-item:last-child .capsule-btn) {
    flex: 1;
  }

  .glass-dialog :deep(.el-dialog) {
    width: 95vw !important;
    max-width: 95vw;
    margin: 8px auto;
  }

  .glass-dialog :deep(.el-dialog__body) {
    padding: 16px;
  }

  .pagination-wrap {
    justify-content: center;
  }
}
</style>
