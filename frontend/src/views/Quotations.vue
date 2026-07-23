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
            label="方案编号/名称"
            min-width="220"
          >
            <template #default="{ row }">
              <span class="proposal-no">{{ row.proposal_no || '-' }}</span>
              <span class="proposal-name">{{ row.proposal_name || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column
            label="总金额"
            width="130"
            align="right"
          >
            <template #default="{ row }">
              <span class="price-text">¥{{ row.total_amount?.toFixed(2) ?? '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column
            label="税率"
            width="80"
            align="center"
          >
            <template #default="{ row }">
              {{ (row.tax_rate * 100).toFixed(0) }}%
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
                {{ quotationStatusMap[row.status] || row.status }}
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
            width="300"
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
                v-if="hasPerm('quotation:confirm') && row.status !== 'confirmed'"
                size="small"
                type="success"
                class="capsule-btn btn-sm"
                @click="handleConfirm(row)"
              >
                确认
              </el-button>
              <el-button
                v-if="hasPerm('share:create') && row.status === 'confirmed'"
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
      append-to-body
      lock-scroll
      :close-on-click-modal="false"
      width="760px"
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
          label="整单税率"
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

        <!-- Quotation items -->
        <el-divider content-position="left">商品明细</el-divider>
        <div class="quote-items-header">
          <span class="quote-col-product">商品</span>
          <span class="quote-col-qty">数量</span>
          <span class="quote-col-price">单价</span>
          <span class="quote-col-tax">税率</span>
          <span class="quote-col-subtotal">未税小计</span>
          <span class="quote-col-total">含税小计</span>
        </div>
        <div
          v-for="(item, idx) in quotationForm.items"
          :key="idx"
          class="quote-item-row"
        >
          <div class="quote-col-product quote-item-name">
            <span class="product-cover">
              <img
                v-if="item.cover_image_url"
                :src="item.cover_image_url"
                class="product-thumb-img"
                @error="onCoverError"
              />
            </span>
            <div>
              <span class="quote-product-name">{{ item.product_name || '-' }}</span>
              <span class="quote-product-no">{{ item.product_no || '-' }}</span>
              <span class="quote-face-price">面价 ¥{{ item.face_price?.toFixed(2) ?? '-' }}</span>
            </div>
          </div>
          <div class="quote-col-qty">
            <el-input-number
              :model-value="item.quantity"
              :min="1"
              :precision="0"
              controls-position="right"
              class="capsule-number"
              @update:model-value="setQuantity(idx, $event)"
            />
          </div>
          <div class="quote-col-price">
            <el-input-number
              :model-value="item.unit_price"
              :min="0"
              :precision="2"
              :step="1"
              controls-position="right"
              class="capsule-number"
              @update:model-value="setUnitPrice(idx, $event)"
            />
          </div>
          <div class="quote-col-tax">
            <el-input-number
              :model-value="item.tax_rate"
              :min="0"
              :max="1"
              :step="0.01"
              :precision="2"
              controls-position="right"
              class="capsule-number"
              @update:model-value="setTaxRate(idx, $event)"
            />
          </div>
          <div class="quote-col-subtotal">
            <span class="subtotal-text">¥{{ (item.quantity * item.unit_price).toFixed(2) }}</span>
          </div>
          <div class="quote-col-total">
            <span class="subtotal-text">¥{{ (item.quantity * item.unit_price * (1 + item.tax_rate)).toFixed(2) }}</span>
          </div>
        </div>

        <div class="quote-totals">
          <div class="totals-row">
            <span class="totals-label">未税合计</span>
            <span class="totals-value">¥{{ subtotalTotal.toFixed(2) }}</span>
          </div>
          <div class="totals-row">
            <span class="totals-label">折扣后</span>
            <span class="totals-value">¥{{ (subtotalTotal * quotationForm.discount).toFixed(2) }}</span>
          </div>
          <div class="totals-row totals-final">
            <span class="totals-label">含税总额</span>
            <span class="totals-value">¥{{ totalAmount.toFixed(2) }}</span>
          </div>
        </div>
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

    <!-- View Quotation Dialog -->
    <el-dialog
      v-model="showViewDialog"
      title="报价详情"
      class="glass-dialog"
      append-to-body
      lock-scroll
      :close-on-click-modal="false"
      width="760px"
    >
      <el-descriptions :column="2" border class="glass-descriptions">
        <el-descriptions-item label="报价单号">
          <span class="mono-text">{{ viewQuotation?.quotation_no }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="viewQuotation?.status === 'confirmed' ? 'success' : 'info'" class="capsule-tag">
            {{ quotationStatusMap[viewQuotation?.status || ''] || viewQuotation?.status }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="方案编号">
          <span class="mono-text">{{ viewQuotation?.proposal_no || '-' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="方案名称">
          {{ viewQuotation?.proposal_name || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="税率">
          {{ viewQuotation?.tax_rate !== undefined ? (viewQuotation.tax_rate * 100).toFixed(0) + '%' : '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="折扣">
          {{ viewQuotation?.discount !== undefined ? (viewQuotation.discount * 100).toFixed(0) + '%' : '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="有效期">
          {{ viewQuotation?.valid_until ? formatDate(viewQuotation.valid_until) : '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="含税总额">
          <span class="price-text">¥{{ viewQuotation?.total_amount?.toFixed(2) ?? '-' }}</span>
        </el-descriptions-item>
      </el-descriptions>

      <el-divider content-position="left">商品明细</el-divider>
      <div class="table-wrapper">
        <el-table :data="viewQuotation?.items || []" border stripe class="items-table">
          <el-table-column label="商品信息" min-width="220">
            <template #default="{ row }">
              <div class="product-cell">
                <img
                  v-if="row.cover_image_url"
                  :src="row.cover_image_url"
                  class="product-thumb-img"
                  @error="onCoverError"
                />
                <div>
                  <span class="product-cell-name">{{ row.product_name || '-' }}</span>
                  <span class="product-cell-no">{{ row.product_no || '-' }}</span>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="quantity" label="数量" width="80" align="center" />
          <el-table-column label="单价" width="100" align="right">
            <template #default="{ row }">
              <span class="price-text">¥{{ row.unit_price?.toFixed(2) ?? '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="税率" width="80" align="center">
            <template #default="{ row }">
              {{ row.tax_rate !== undefined ? (row.tax_rate * 100).toFixed(0) + '%' : '-' }}
            </template>
          </el-table-column>
          <el-table-column label="未税小计" width="120" align="right">
            <template #default="{ row }">
              <span class="subtotal-text">¥{{ row.subtotal?.toFixed(2) ?? '-' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-dialog>

    <!-- Share Dialog -->
    <el-dialog
      v-model="showShareDialog"
      title="创建分享链接"
      class="glass-dialog"
      append-to-body
      lock-scroll
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
    <ShareResultDialog
      v-model="showShareResult"
      :share-url="shareResultUrl"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { quotationApi, proposalApi, shareApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'
import type {
  Quotation,
  QuotationCreateRequest,
  QuotationItem,
  QuotationUpdateRequest,
  ShareCreateRequest,
  ShareForm,
} from '@/types/sales'
import ShareResultDialog from '@/components/ShareResultDialog.vue'

const route = useRoute()
const authStore = useAuthStore()

function hasPerm(perm: string): boolean {
  return hasPermission(authStore.permissions, perm)
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

const quotationStatusMap: Record<string, string> = { draft: '草稿', confirmed: '已确认' }

const loading = ref(false)
const quotations = ref<Quotation[]>([])
const total = ref(0)
const showQuotationDialog = ref(false)
const quotationMode = ref<'create' | 'edit'>('create')
const quotationLoading = ref(false)
const quotationFormRef = ref<FormInstance>()
const quotationEditId = ref('')

const showShareDialog = ref(false)
const showShareResult = ref(false)
const shareLoading = ref(false)
const shareResultUrl = ref('')

const showViewDialog = ref(false)
const viewQuotation = ref<Quotation | null>(null)

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
  items: [] as QuotationItem[],
})

const quotationFormRules: FormRules = {
  proposal_id: [{ required: true, message: '请输入方案ID', trigger: 'blur' }],
}

const shareForm = reactive<ShareForm>({
  share_type: 'quotation',
  target_id: '',
  creator_id: '',
  password: '',
  expire_hours: 24,
  max_access_count: 100,
})

// Computed totals
const subtotalTotal = computed(() =>
  quotationForm.items.reduce((sum, item) => sum + item.quantity * item.unit_price, 0)
)
const totalAmount = computed(() =>
  quotationForm.items.reduce(
    (sum, item) => sum + item.quantity * item.unit_price * (1 + item.tax_rate),
    0,
  ) * quotationForm.discount
)

const setItemField = (idx: number, field: keyof QuotationItem, value: unknown) => {
  quotationForm.items = quotationForm.items.map((item, i) => {
    if (i !== idx) return item
    return { ...item, [field]: value }
  })
}

const setQuantity = (idx: number, val: number | null) =>
  setItemField(idx, 'quantity', Math.max(1, Math.round(val ?? 1)))

const setUnitPrice = (idx: number, val: number | null) =>
  setItemField(idx, 'unit_price', Math.max(0, val ?? 0))

const setTaxRate = (idx: number, val: number | null) =>
  setItemField(idx, 'tax_rate', Math.max(0, Math.min(1, val ?? 0)))

const onCoverError = (e: Event) => {
  const img = e.target as HTMLImageElement
  if (img) img.style.display = 'none'
}

const fetchQuotations = async () => {
  loading.value = true
  try {
    const res = await quotationApi.list({
      proposal_id: queryParams.proposal_id || undefined,
      status: queryParams.status || undefined,
      page: queryParams.page,
      size: queryParams.size,
    })
    quotations.value = res.data.list
    total.value = res.data.total
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

const handleView = async (row: Quotation) => {
  try {
    const res = await quotationApi.get(row.id)
    viewQuotation.value = res.data
    showViewDialog.value = true
  } catch {
    ElMessage.error('加载报价详情失败')
  }
}

const handleEdit = async (row: Quotation) => {
  quotationMode.value = 'edit'
  quotationEditId.value = row.id
  try {
    // Always GET the current quotation before edit
    const res = await quotationApi.get(row.id)
    const q = res.data
    quotationForm.proposal_id = q.proposal_id
    quotationForm.tax_rate = q.tax_rate
    quotationForm.discount = q.discount
    quotationForm.valid_until = q.valid_until ? new Date(q.valid_until) : null
    quotationForm.items = q.items.map((item) => ({ ...item }))
    showQuotationDialog.value = true
  } catch {
    ElMessage.error('加载报价数据失败')
  }
}

const handleConfirm = async (row: Quotation) => {
  try {
    await quotationApi.confirm(row.id)
    ElMessage.success('报价已确认')
    fetchQuotations()
  } catch {
    // error handled by interceptor
  }
}

const handleShare = (row: Quotation) => {
  shareForm.target_id = row.id
  shareForm.creator_id = authStore.user?.id || ''
  showShareDialog.value = true
}

const handleQuotationSubmit = async () => {
  if (!quotationFormRef.value) return
  await quotationFormRef.value.validate(async (valid) => {
    if (!valid) return
    // Validate at least one item
    if (quotationForm.items.length === 0) {
      ElMessage.warning('请至少添加一项商品')
      return
    }
    // Validate items
    for (const item of quotationForm.items) {
      if (!item.product_id) {
        ElMessage.warning('商品 ID 不能为空')
        return
      }
      if (!Number.isInteger(item.quantity) || item.quantity < 1) {
        ElMessage.warning(`商品 "${item.product_name || item.product_id}" 的数量必须为正整数`)
        return
      }
      if (item.unit_price < 0) {
        ElMessage.warning(`商品 "${item.product_name || item.product_id}" 的单价不能为负`)
        return
      }
    }
    quotationLoading.value = true
    try {
      const itemPayload = quotationForm.items.map((item) => ({
        product_id: item.product_id,
        quantity: item.quantity,
        unit_price: item.unit_price,
        tax_rate: item.tax_rate,
      }))
      const commonPayload: QuotationUpdateRequest = {
        tax_rate: quotationForm.tax_rate,
        discount: quotationForm.discount,
        valid_until: quotationForm.valid_until?.toISOString() ?? null,
        items: itemPayload,
      }

      if (quotationMode.value === 'edit' && quotationEditId.value) {
        await quotationApi.update(quotationEditId.value, commonPayload)
      } else {
        const payload: QuotationCreateRequest = {
          ...commonPayload,
          proposal_id: quotationForm.proposal_id,
        }
        await quotationApi.create(payload)
      }
      ElMessage.success(quotationMode.value === 'edit' ? '更新成功' : '创建成功')
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
    const payload: ShareCreateRequest = {
      share_type: shareForm.share_type,
      target_id: shareForm.target_id,
    }
    if (shareForm.password) payload.password = shareForm.password
    if (shareForm.expire_hours) payload.expire_hours = shareForm.expire_hours
    if (shareForm.max_access_count) payload.max_access_count = shareForm.max_access_count

    const res = await shareApi.create(payload)
    shareResultUrl.value = res.data.share_url || '/'
    showShareDialog.value = false
    showShareResult.value = true
  } catch {
    // error handled by interceptor
  } finally {
    shareLoading.value = false
  }
}

const handleExportPdf = async (row: Quotation) => {
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

const prefillProposalId = computed(() => route.query.proposal_id as string | undefined)

onMounted(() => {
  const pid = prefillProposalId.value
  if (pid) {
    quotationForm.proposal_id = pid
    quotationMode.value = 'create'
    // Fetch proposal to prefill items
    Promise.resolve().then(async () => {
      try {
        const res = await proposalApi.get(pid)
        quotationForm.items = res.data.items.map((item) => ({
          product_id: item.product_id,
          quantity: item.quantity,
          unit_price: item.face_price ?? 0,
          tax_rate: quotationForm.tax_rate,
          subtotal: (item.face_price ?? 0) * item.quantity,
          product_name: item.product_name,
          product_no: item.product_no,
          face_price: item.face_price,
          cover_image_url: item.cover_image_url,
        }))
        showQuotationDialog.value = true
      } catch {
        ElMessage.warning('预填方案数据失败，请手动填写')
        showQuotationDialog.value = true
      }
    })
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

.proposal-no {
  font-family: monospace;
  font-size: 13px;
  color: var(--text-primary);
  margin-right: 6px;
}

.proposal-name {
  font-size: 13px;
  color: var(--text-secondary);
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

/* ===== Quotation items table ===== */
.quote-items-header,
.quote-item-row {
  display: grid;
  grid-template-columns: 2fr 0.6fr 0.8fr 0.7fr 0.9fr 0.9fr;
  gap: 8px;
  align-items: center;
}

.quote-items-header {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  padding-bottom: 6px;
  border-bottom: 1px solid rgba(30, 50, 90, 0.08);
  margin-bottom: 6px;
}

.quote-items-header .quote-col-product,
.quote-item-row .quote-col-product { padding-right: 8px; }
.quote-items-header .quote-col-qty,
.quote-item-row .quote-col-qty { text-align: center; }
.quote-items-header .quote-col-price,
.quote-item-row .quote-col-price { text-align: right; }
.quote-items-header .quote-col-tax,
.quote-item-row .quote-col-tax { text-align: center; }
.quote-items-header .quote-col-subtotal,
.quote-item-row .quote-col-subtotal { text-align: right; }
.quote-items-header .quote-col-total,
.quote-item-row .quote-col-total { text-align: right; }

.quote-item-row {
  padding: 8px 0;
  border-bottom: 1px solid rgba(30, 50, 90, 0.04);
}

.quote-item-name {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.product-cover {
  flex-shrink: 0;
}

.product-thumb-img {
  width: 36px;
  height: 36px;
  border-radius: 6px;
  object-fit: cover;
  background: var(--brand-lighter);
}

.quote-product-name {
  font-weight: 600;
  color: var(--brand-deep);
  font-size: 13px;
  display: block;
}

.quote-product-no {
  font-size: 11px;
  color: var(--text-secondary);
  font-family: monospace;
  display: block;
}

.quote-face-price {
  font-size: 11px;
  color: var(--text-secondary);
  display: block;
}

.subtotal-text {
  font-family: monospace;
  color: var(--brand-deep);
  font-weight: 600;
}

/* ===== Quotation totals ===== */
.quote-totals {
  margin-top: 12px;
  padding: 12px 16px;
  background: var(--brand-lighter);
  border-radius: var(--radius-sm);
}

.totals-row {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
}

.totals-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.totals-value {
  font-family: monospace;
  color: var(--text-primary);
  font-weight: 500;
}

.totals-final .totals-label {
  font-weight: 600;
  color: var(--brand-deep);
}

.totals-final .totals-value {
  font-weight: 700;
  color: var(--brand-deep);
  font-size: 16px;
}

/* ===== View dialog ===== */
.glass-descriptions {
  margin-top: 16px;
  border-radius: var(--radius-md);
  overflow: hidden;
}

.glass-descriptions :deep(.el-descriptions__label) {
  background: var(--brand-lighter);
  color: var(--text-primary);
  font-weight: 600;
}

.glass-descriptions :deep(.el-descriptions__content) {
  color: var(--text-primary);
}

.items-table {
  width: 100%;
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.items-table :deep(.el-table__header-wrapper) {
  background: var(--brand-lighter);
}

.items-table :deep(.el-table__header th) {
  background: var(--brand-lighter);
  color: var(--text-primary);
  font-weight: 600;
}

.items-table :deep(.el-table__row:hover td) {
  background: var(--brand-lighter);
}

.product-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.product-cell-name {
  font-weight: 600;
  color: var(--brand-deep);
  font-size: 13px;
  display: block;
}

.product-cell-no {
  font-size: 11px;
  color: var(--text-secondary);
  font-family: monospace;
  display: block;
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

  /* Mobile: stack quotation items */
  .quote-items-header,
  .quote-item-row {
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }

  .quote-items-header .quote-col-product,
  .quote-items-header .quote-col-qty {
    grid-column: span 2;
  }
}
</style>
