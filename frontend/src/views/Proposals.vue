<template>
  <div class="proposals-page">
    <el-card class="glass-card">
      <template #header>
        <div class="card-header">
          <span class="page-title">方案管理</span>
          <el-button
            v-if="hasPerm('proposal:create')"
            type="primary"
            class="capsule-btn capsule-btn-primary"
            @click="showCreateDialog = true"
          >
            新增方案
          </el-button>
        </div>
      </template>

      <el-form
        :inline="true"
        :model="queryParams"
        class="search-form"
      >
        <el-form-item label="关键词">
          <el-input
            v-model="queryParams.keyword"
            placeholder="方案名称/客户名称"
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
          :data="proposals"
          border
          stripe
          class="proposal-table"
        >
          <el-table-column
            prop="proposal_no"
            label="方案编号"
            width="160"
          />
          <el-table-column
            prop="proposal_name"
            label="方案名称"
            min-width="180"
            show-overflow-tooltip
          />
          <el-table-column
            prop="customer_name"
            label="客户名称"
            min-width="140"
            show-overflow-tooltip
          />
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
            width="260"
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
                v-if="hasPerm('quotation:create') && row.status !== 'confirmed'"
                size="small"
                type="success"
                class="capsule-btn btn-sm"
                @click="handleCreateQuotation(row)"
              >
                生成报价
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
                v-if="hasPerm('proposal:delete')"
                size="small"
                type="danger"
                class="capsule-btn btn-sm"
                @click="handleDelete(row)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- Create Proposal Dialog -->
    <el-dialog
      v-model="showCreateDialog"
      title="新增方案"
      class="glass-dialog"
      :close-on-click-modal="false"
    >
      <el-form
        ref="createFormRef"
        :model="createForm"
        :rules="createFormRules"
        label-width="100px"
      >
        <el-form-item
          label="方案名称"
          prop="proposal_name"
        >
          <el-input
            v-model="createForm.proposal_name"
            placeholder="请输入方案名称"
            class="capsule-input"
          />
        </el-form-item>
        <el-form-item
          label="客户名称"
          prop="customer_name"
        >
          <el-input
            v-model="createForm.customer_name"
            placeholder="请输入客户名称"
            class="capsule-input"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button
          class="capsule-btn"
          @click="showCreateDialog = false"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="createLoading"
          class="capsule-btn capsule-btn-primary"
          @click="handleCreateSubmit"
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
              label="方案"
              value="proposal"
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

    <!-- Share Result Dialog -->
    <el-dialog
      v-model="showShareResult"
      title="分享链接已生成"
      class="glass-dialog"
      :close-on-click-modal="false"
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
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { proposalApi, shareApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'

const router = useRouter()
const authStore = useAuthStore()

function hasPerm(perm: string): boolean {
  return hasPermission(authStore.permissions, perm)
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

const loading = ref(false)
const proposals = ref<any[]>([])
const showCreateDialog = ref(false)
const createLoading = ref(false)
const createFormRef = ref<FormInstance>()

const queryParams = reactive({
  keyword: '',
  status: '',
})

const createForm = reactive({
  proposal_name: '',
  customer_name: '',
})

const createFormRules: FormRules = {
  proposal_name: [{ required: true, message: '请输入方案名称', trigger: 'blur' }],
}

const showShareDialog = ref(false)
const showShareResult = ref(false)
const shareLoading = ref(false)
const shareForm = reactive({
  share_type: 'proposal',
  target_id: '',
  creator_id: '',
  password: '',
  expire_hours: 24,
  max_access_count: 100,
})
const shareResultUrl = ref('')

const fetchProposals = async () => {
  loading.value = true
  try {
    const res = await proposalApi.list(queryParams)
    proposals.value = res.data?.list || []
  } catch {
    ElMessage.error('加载方案列表失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  fetchProposals()
}

const handleReset = () => {
  queryParams.keyword = ''
  queryParams.status = ''
  fetchProposals()
}

const handleView = (row: any) => {
  router.push(`/proposals/${row.id}`)
}

const handleCreateQuotation = (row: any) => {
  router.push(`/quotations?proposal_id=${row.id}`)
}

const handleShare = (row: any) => {
  shareForm.target_id = row.id
  shareForm.creator_id = authStore.user?.id || ''
  showShareDialog.value = true
}

const handleCreateSubmit = async () => {
  if (!createFormRef.value) return
  await createFormRef.value.validate(async (valid) => {
    if (!valid) return
    createLoading.value = true
    try {
      const creatorId = authStore.user?.id
      await proposalApi.create({
        proposal_name: createForm.proposal_name,
        customer_name: createForm.customer_name,
        creator_id: creatorId,
        items: [],
      })
      ElMessage.success('创建成功')
      showCreateDialog.value = false
      createForm.proposal_name = ''
      createForm.customer_name = ''
      fetchProposals()
    } catch {
      // error handled by interceptor
    } finally {
      createLoading.value = false
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

const handleDelete = async (row: any) => {
  try {
    await ElMessageBox.confirm(`确定删除方案 "${row.proposal_name}"？`, '确认删除')
    await proposalApi.delete(row.id)
    ElMessage.success('删除成功')
    fetchProposals()
  } catch (e: any) {
    if (e !== 'cancel') {
      // error handled by interceptor
    }
  }
}

onMounted(fetchProposals)
</script>

<style scoped>
/* ===== CSS Variables ===== */
.proposals-page {
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

.proposal-table {
  width: 100%;
  border-radius: var(--radius-md);
  overflow: hidden;
}

.proposal-table :deep(.el-table__header-wrapper) {
  background: var(--brand-lighter);
}

.proposal-table :deep(.el-table__header th) {
  background: var(--brand-lighter);
  color: var(--text-primary);
  font-weight: 600;
  font-size: 13px;
  padding: 14px 0;
}

.proposal-table :deep(.el-table__row td) {
  padding: 12px 0;
}

.proposal-table :deep(.el-table__row:hover td) {
  background: var(--brand-lighter);
}

.mono-text {
  font-family: monospace;
  color: var(--text-secondary);
  font-size: 12px;
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
  .proposals-page {
    padding: 8px;
  }

  .glass-card {
    border-radius: var(--radius-md);
  }

  .glass-card :deep(.el-card__header),
  .glass-card :deep(.el-card__body) {
    padding: 16px;
  }

  .card-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
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
}
</style>
