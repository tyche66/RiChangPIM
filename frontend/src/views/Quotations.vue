<template>
  <div class="quotations-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>报价管理</span>
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
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="queryParams.status"
            placeholder="全部"
            clearable
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
            @click="handleSearch"
          >
            查询
          </el-button>
          <el-button @click="handleReset">
            重置
          </el-button>
        </el-form-item>
      </el-form>

      <el-table
        v-loading="loading"
        :data="quotations"
        border
        stripe
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
        >
          <template #default="{ row }">
            ¥{{ row.total_amount?.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="status"
          label="状态"
          width="100"
        >
          <template #default="{ row }">
            <el-tag :type="row.status === 'confirmed' ? 'success' : 'info'">
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
            {{ formatDate(row.create_time) }}
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
          width="220"
          fixed="right"
        >
          <template #default="{ row }">
            <el-button
              size="small"
              @click="handleView(row)"
            >
              查看
            </el-button>
            <el-button
              v-if="hasPerm('quotation:edit') && row.status !== 'confirmed'"
              size="small"
              @click="handleEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              v-if="hasPerm('share:create')"
              size="small"
              type="warning"
              @click="handleShare(row)"
            >
              分享
            </el-button>
            <el-button
              size="small"
              type="info"
              @click="handleExportPdf(row)"
            >
              导出PDF
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="queryParams.page"
        v-model:page-size="queryParams.size"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next, jumper"
        style="margin-top: 20px; justify-content: flex-end;"
        @current-change="fetchQuotations"
        @size-change="fetchQuotations"
      />
    </el-card>

    <!-- Create/Edit Quotation Dialog -->
    <el-dialog
      v-model="showQuotationDialog"
      :title="quotationMode === 'create' ? '创建报价单' : '编辑报价单'"
      width="700px"
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
          />
        </el-form-item>
        <el-form-item label="有效期至">
          <el-date-picker
            v-model="quotationForm.valid_until"
            type="datetime"
            placeholder="选择有效期"
            style="width: 100%;"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showQuotationDialog = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="quotationLoading"
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
      width="500px"
      :close-on-click-modal="false"
    >
      <el-form label-width="120px">
        <el-form-item label="分享类型">
          <el-select
            v-model="shareForm.share_type"
            disabled
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
          />
        </el-form-item>
        <el-form-item label="有效期(小时)">
          <el-input-number
            v-model="shareForm.expire_hours"
            :min="1"
            :max="720"
          />
        </el-form-item>
        <el-form-item label="最大访问次数">
          <el-input-number
            v-model="shareForm.max_access_count"
            :min="1"
            :max="1000"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showShareDialog = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="shareLoading"
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
      width="500px"
    >
      <el-alert
        type="success"
        :closable="false"
        style="margin-bottom: 16px;"
      >
        请将以下链接发送给客户
      </el-alert>
      <el-input
        :model-value="shareResultUrl"
        readonly
      >
        <template #append>
          <el-button @click="copyShareUrl">
            复制
          </el-button>
        </template>
      </el-input>
      <div
        v-if="shareResultUrl"
        style="margin-top: 12px;"
      >
        <el-button
          type="primary"
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
  // Navigate to quotation detail - for now just show info
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

// Check for proposal_id query param on mount
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
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.search-form {
  margin-bottom: 16px;
}
</style>
