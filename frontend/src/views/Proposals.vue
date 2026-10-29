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
          <!-- 排版层级用 class-name（不是 class）：class 会落到 hidden-columns 的隐藏占位 div 上，规则不生效 -->
          <el-table-column
            prop="proposal_no"
            label="方案编号"
            class-name="cell-code"
            width="160"
          />
          <el-table-column
            prop="proposal_name"
            label="方案名称"
            class-name="cell-strong"
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
                {{ proposalStatusMap[row.status] || row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="create_time"
            label="创建时间"
            class-name="cell-meta"
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
                text
                class="action-link"
                @click="handleView(row)"
              >
                查看
              </el-button>
              <el-button
                v-if="hasPerm('share:create')"
                size="small"
                text
                class="action-link"
                @click="handleShare(row)"
              >
                分享
              </el-button>
              <el-dropdown trigger="click">
                <button
                  type="button"
                  class="more-trigger"
                  aria-label="更多操作"
                >
                  <el-icon><ArrowDown /></el-icon>
                </button>
                <template #dropdown>
                  <el-dropdown-menu class="flat-action-menu">
                    <el-dropdown-item
                      v-if="hasPerm('quotation:create')"
                      @click="handleCreateQuotation(row)"
                    >
                      生成报价
                    </el-dropdown-item>
                    <el-dropdown-item
                      v-if="hasPerm('proposal:confirm') && row.status !== 'confirmed'"
                      @click="handleConfirm(row)"
                    >
                      确认
                    </el-dropdown-item>
                    <el-dropdown-item
                      v-if="hasPerm('proposal:edit') && row.status === 'confirmed'"
                      @click="handleRevert(row)"
                    >
                      撤销确认
                    </el-dropdown-item>
                    <el-dropdown-item
                      v-if="hasPerm('proposal:delete')"
                      class="dropdown-item-danger"
                      @click="handleDelete(row)"
                    >
                      删除
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
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
        @current-change="fetchProposals"
        @size-change="fetchProposals"
      />
    </el-card>

    <!-- Create Proposal Dialog with items -->
    <el-dialog
      v-model="showCreateDialog"
      title="新增方案"
      class="glass-dialog proposal-form-dialog"
      append-to-body
      lock-scroll
      :close-on-click-modal="false"
      width="920px"
    >
      <el-form
        ref="createFormRef"
        :model="createForm"
        :rules="createFormRules"
        label-width="88px"
        label-position="top"
      >
        <el-row :gutter="16">
          <el-col :span="12">
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
          </el-col>
          <el-col :span="12">
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
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="关联客户">
              <el-select
                v-model="createForm.customer_id"
                filterable
                remote
                clearable
                reserve-keyword
                placeholder="可选：关联客户档案"
                :remote-method="searchCustomers"
                :loading="customerLoading"
                class="capsule-select full-width"
              >
                <el-option
                  v-for="c in customerOptions"
                  :key="c.id"
                  :label="c.name"
                  :value="c.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="关联项目">
              <el-select
                v-model="createForm.project_id"
                filterable
                clearable
                placeholder="可选：关联项目并绑定空间编号"
                class="capsule-select full-width"
              >
                <el-option
                  v-for="p in projectOptions"
                  :key="p.id"
                  :label="p.name"
                  :value="p.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item
          label="商品明细"
          class="items-form-item"
          label-width="0"
        >
          <ProposalItemEditor
            v-model="createForm.items"
            compact
          />
        </el-form-item>
        <el-form-item
          label="方案平面图"
          class="floor-plan-form-item"
          label-width="0"
        >
          <ProposalFloorPlanManager
            v-model="createForm.floor_plans"
            compact
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

    <!-- Share Result with QR code -->
    <ShareResultDialog
      v-model="showShareResult"
      :share-url="shareResultUrl"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { proposalApi, shareApi } from '@/api'
import { proposalFloorPlanApi } from '@/api/proposalFloorPlans'
import { customerApi } from '@/api/customer'
import { projectApi } from '@/api/project'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'
import type { Proposal, ProposalItem, FloorPlanDraft, ShareCreateRequest, ShareForm, ProposalToken } from '@/types/sales'
import ProposalItemEditor from '@/components/ProposalItemEditor.vue'
import ProposalFloorPlanManager from '@/components/ProposalFloorPlanManager.vue'
import ShareResultDialog from '@/components/ShareResultDialog.vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

function hasPerm(perm: string): boolean {
  return hasPermission(authStore.permissions, perm)
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

const proposalStatusMap: Record<string, string> = { draft: '草稿', confirmed: '已确认' }

const loading = ref(false)
const proposals = ref<Proposal[]>([])
const total = ref(0)
const showCreateDialog = ref(false)
const createLoading = ref(false)
const createFormRef = ref<FormInstance>()

const queryParams = reactive({
  keyword: '',
  status: '',
  page: 1,
  size: 20,
})

const createForm = reactive({
  proposal_name: '',
  customer_name: '',
  customer_id: null as string | null,
  project_id: null as string | null,
  items: [] as ProposalItem[],
  // Track D：新增时先暂存平面图，方案创建成功后再一次性绑定
  floor_plans: [] as FloorPlanDraft[],
})
// 客户/项目选项。方案明细的楼层/空间名称由业务员直接输入；
// ProjectSpace API 仍保留给后台空间维护，不作为方案通用选项来源。
const customerOptions = ref<Array<{ id: string; name: string }>>([])
const projectOptions = ref<Array<{ id: string; name: string }>>([])
const customerLoading = ref(false)

const createFormRules: FormRules = {
  proposal_name: [{ required: true, message: '请输入方案名称', trigger: 'blur' }],
}

// ---------------------------------------------------------------------------
// 客户/项目选项
// ---------------------------------------------------------------------------

async function searchCustomers() {
  customerLoading.value = true
  try {
    const res = await customerApi.list({ page: 1, size: 20 })
    customerOptions.value = (res.data?.list || []).map((c: { id: string; name: string }) => ({
      id: c.id,
      name: c.name,
    }))
  } catch {
    customerOptions.value = []
  } finally {
    customerLoading.value = false
  }
}

async function loadProjects() {
  try {
    const res = await projectApi.list({ page: 1, size: 100 })
    projectOptions.value = (res.data?.list || []).map((p: { id: string; name: string }) => ({
      id: p.id,
      name: p.name,
    }))
  } catch {
    projectOptions.value = []
  }
}

const showShareDialog = ref(false)
const showShareResult = ref(false)
const shareLoading = ref(false)
const shareForm = reactive<ShareForm>({
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
    const res = await proposalApi.list({
      keyword: queryParams.keyword || undefined,
      status: queryParams.status || undefined,
      page: queryParams.page,
      size: queryParams.size,
    })
    proposals.value = res.data.list
    total.value = res.data.total
  } catch {
    ElMessage.error('加载方案列表失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  queryParams.page = 1
  fetchProposals()
}

const handleReset = () => {
  queryParams.keyword = ''
  queryParams.status = ''
  queryParams.page = 1
  fetchProposals()
}

const handleView = (row: Proposal) => {
  router.push(`/proposals/${row.id}`)
}

const handleCreateQuotation = (row: Proposal) => {
  router.push(`/quotations?proposal_id=${row.id}`)
}

const handleShare = (row: Proposal) => {
  shareForm.target_id = row.id
  shareForm.creator_id = authStore.user?.id || ''
  showShareDialog.value = true
}

const handleConfirm = async (row: Proposal) => {
  try {
    await proposalApi.confirm(row.id)
    ElMessage.success('方案已确认')
    fetchProposals()
  } catch {
    // error handled by interceptor
  }
}

const handleRevert = async (row: Proposal) => {
  try {
    await ElMessageBox.confirm(
      `确定要撤销方案 "${row.proposal_name}" 的确认状态吗？撤销后可重新编辑。`,
      '撤销确认',
      {
        confirmButtonText: '撤销',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
    await proposalApi.revertConfirmation(row.id)
    ElMessage.success('已撤销确认')
    fetchProposals()
  } catch (e: unknown) {
    if (e !== 'cancel') {
      // error handled by interceptor
    }
  }
}

function proposalCreateErrorMessage(error: unknown): string {
  const responseData = (error as { response?: { data?: { detail?: unknown; msg?: unknown; message?: unknown } } })
    ?.response?.data
  const detail = responseData?.detail
  if (typeof detail === 'string' && detail.trim()) return `创建失败：${detail}`
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const message = (detail as { msg?: unknown }).msg
    if (typeof message === 'string' && message.trim()) return `创建失败：${message}`
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((entry) => {
        if (!entry || typeof entry !== 'object') return ''
        const validation = entry as { loc?: unknown[]; msg?: unknown }
        const field = Array.isArray(validation.loc) ? validation.loc.slice(1).join('.') : ''
        const message = typeof validation.msg === 'string' ? validation.msg : ''
        return [field, message].filter(Boolean).join('：')
      })
      .filter(Boolean)
    if (messages.length) return `创建失败：${messages.join('；')}`
  }
  for (const message of [responseData?.message, responseData?.msg]) {
    if (typeof message === 'string' && message.trim()) return `创建失败：${message}`
  }
  const networkMessage = (error as { message?: unknown })?.message
  if (!responseData && typeof networkMessage === 'string' && networkMessage.trim()) {
    return `创建失败：${networkMessage}`
  }
  return '创建方案失败，请检查填写内容后重试'
}

const handleCreateSubmit = async () => {
  if (createLoading.value) return
  const form = createFormRef.value
  if (!form) {
    ElMessage.warning('方案表单尚未准备好，请稍后重试')
    return
  }

  createLoading.value = true
  try {
    const valid = await form.validate().catch(() => false)
    if (!valid) {
      ElMessage.warning('请填写方案名称等必填信息')
      return
    }
    if (!createForm.proposal_name.trim()) {
      ElMessage.warning('请输入方案名称')
      return
    }
    if (createForm.items.length === 0) {
      ElMessage.warning('请至少添加一项商品')
      return
    }
    for (const item of createForm.items) {
      if (typeof item.product_id !== 'string' || !item.product_id.trim()) {
        ElMessage.warning('商品信息缺少有效产品 ID，请重新选择商品')
        return
      }
      if (!Number.isInteger(item.quantity) || item.quantity < 1) {
        ElMessage.warning(`商品 "${item.product_name || item.product_id}" 的数量必须为正整数`)
        return
      }
    }

    await authStore.ensureUser()
    const creatorId = authStore.userId
    if (!creatorId) {
      ElMessage.warning('用户信息尚未加载，请稍后重试')
      return
    }

    const created = await proposalApi.create({
      proposal_name: createForm.proposal_name.trim(),
      customer_name: createForm.customer_name.trim() || null,
      customer_id: createForm.customer_id || undefined,
      project_id: createForm.project_id || undefined,
      creator_id: creatorId,
      items: createForm.items.map((item) => ({
        product_id: item.product_id.trim(),
        quantity: item.quantity,
        remark: item.remark?.trim() || undefined,
        project_space_id: item.project_space_id || undefined,
        floor_label: item.floor_label?.trim() || undefined,
        space_label: item.space_label?.trim() || undefined,
        material_desc: item.material_desc?.trim() || undefined,
      })),
    }, { suppressErrorMessage: true })

    // 平面图是附加物料：绑定失败不回滚已创建的方案，但要明确告知去哪里补
    if (createForm.floor_plans.length && created?.data?.id) {
      try {
        await proposalFloorPlanApi.batchCreate(
          created.data.id,
          createForm.floor_plans.map((plan, index) => ({
            attachment_id: plan.attachment_id,
            name: plan.name,
            sort: index,
          })),
        )
      } catch {
        ElMessage.warning('方案已创建，但平面图绑定失败，请到方案详情页重新添加')
      }
    }

    ElMessage.success('创建成功')
    showCreateDialog.value = false
    createForm.proposal_name = ''
    createForm.customer_name = ''
    createForm.customer_id = null
    createForm.project_id = null
    createForm.items = []
    createForm.floor_plans = []
    queryParams.page = 1
    await fetchProposals()
  } catch (error) {
    ElMessage.error(proposalCreateErrorMessage(error))
  } finally {
    createLoading.value = false
  }
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

const handleDelete = async (row: Proposal) => {
  try {
    await ElMessageBox.confirm(`确定删除方案 "${row.proposal_name}"？`, '确认删除')
    await proposalApi.delete(row.id)
    ElMessage.success('删除成功')
    fetchProposals()
  } catch (e: unknown) {
    if (e !== 'cancel') {
      // error handled by interceptor
    }
  }
}

watch(
  () => route.query.selection_token,
  async (selectionToken) => {
    if (route.query.mode !== 'create' || typeof selectionToken !== 'string') return
    const storageKey = `proposal_token_${selectionToken}`
    const raw = sessionStorage.getItem(storageKey)
    if (!raw) {
      ElMessage.warning('未找到制作方案数据，请从产品列表重新选择')
      await router.replace('/proposals')
      return
    }

    sessionStorage.removeItem(storageKey)
    const token: ProposalToken = JSON.parse(raw)
    if (token.options.length === 0) {
      ElMessage.warning('方案数据已使用，请从产品列表重新选择')
      await router.replace('/proposals')
      return
    }

    createForm.proposal_name = ''
    createForm.customer_name = ''
    createForm.items = token.options.map((opt) => ({
      product_id: opt.id,
      quantity: 1,
      product_name: opt.product_name,
      product_no: opt.product_no,
      face_price: opt.face_price,
      stock_status: opt.stock_status,
      cover_image_url: opt.cover_image_url,
    }))
    showCreateDialog.value = true
    await router.replace('/proposals')
  },
  { immediate: true },
)

onMounted(() => {
  fetchProposals()
  loadProjects()
})
</script>

<style scoped>
/* ===== CSS Variables ===== */
.proposals-page {
  /* 以下别名全部指向 design-system.css 的全局语义 Token：
     浅色保持原值，深色随 .dark-mode 自动切换，本文件不再需要深色覆盖块 */
  --brand-deep: var(--pim-text-strong);
  --brand-primary: var(--pim-text-strong);
  --brand-light: rgba(var(--pim-brand), 0.08);
  --brand-lighter: rgba(var(--pim-brand), 0.04);
  --text-primary: var(--pim-text-primary);
  --text-secondary: var(--pim-text-secondary);
  --bg-mist: var(--pim-page);
  --glass-bg: var(--pim-surface);
  --glass-border: var(--pim-card-border);
  --radius-lg: var(--pim-radius);
  --radius-md: var(--pim-radius-sm);
  --radius-sm: 12px;
  --shadow-soft: 0 4px 24px rgba(var(--pim-brand), 0.06);
  --transition-fast: 200ms cubic-bezier(0.4, 0, 0.2, 1);
  padding: 16px;
  min-height: 100vh;
  background: var(--bg-mist);
}

/* ===== Glass Card ===== */
.glass-card {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-soft);
  overflow: hidden;
}

.glass-card :deep(.el-card__header) {
  background: transparent;
  border-bottom: 1px solid rgba(var(--pim-brand), 0.06);
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
  box-shadow: 0 0 0 1px rgba(var(--pim-brand), 0.1) inset;
  padding: 4px 16px;
  transition: var(--transition-fast);
}

.capsule-input :deep(.el-input__wrapper):hover {
  box-shadow: 0 0 0 1px rgba(var(--pim-brand), 0.25) inset;
}

.capsule-select :deep(.el-select__wrapper),
.capsule-select :deep(.el-input__wrapper) {
  border-radius: 20px;
  box-shadow: 0 0 0 1px rgba(var(--pim-brand), 0.1) inset;
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

.action-link {
  padding: 0;
  min-height: 0;
  border: 0;
  background: transparent;
  color: var(--text-primary);
  font-weight: 500;
}

.action-link:hover {
  background: transparent;
  color: var(--brand-deep);
}

.more-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  margin-left: 6px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: var(--transition-fast);
}

.more-trigger:hover {
  color: var(--brand-deep);
  background: rgba(var(--pim-brand), 0.06);
}

.flat-action-menu {
  padding: 6px;
}

.flat-action-menu :deep(.el-dropdown-menu__item) {
  border-radius: 10px;
  line-height: 1.1;
  padding: 9px 14px;
  color: var(--text-primary);
}

.flat-action-menu :deep(.el-dropdown-menu__item:hover) {
  background: rgba(var(--pim-brand), 0.06);
  color: var(--brand-deep);
}

.dropdown-item-danger {
  color: var(--pim-danger-bright);
}

.dropdown-item-danger:hover {
  background: var(--pim-danger-bg);
  color: var(--pim-danger-bright);
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

/*
 * 表头底色 / 字号 / 字重 / 单元格 padding / hover 底色都交给 design-system.css 的
 * 全局表格规则（12px + 字距的弱化表头、极细横线、11px 行距），这里原先的
 * .el-table__header th / .el-table__row td 覆盖跟它打架，会把层级压回「一个字重」。
 */
.mono-text {
  /* 走 --pim-font-mono（鸿蒙优先），裸 monospace 在 Windows 上会掉成 Courier New */
  font-family: var(--pim-font-mono);
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
  background: var(--pim-accent-solid);
  color: var(--pim-on-accent);
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
  box-shadow: 0 20px 60px rgba(var(--pim-brand), 0.15);
}

.glass-dialog :deep(.el-dialog__header) {
  background: linear-gradient(135deg, rgba(var(--pim-brand), 0.06), rgba(var(--pim-brand), 0.02));
  padding: 20px 24px 16px;
  margin-right: 0;
  border-bottom: 1px solid rgba(var(--pim-brand), 0.06);
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

/* 「新增方案」弹窗：两列栅格 + 明细块占满整行，避免字段互相挤压 */
.proposal-form-dialog :deep(.el-form-item) {
  margin-bottom: 14px;
}

.proposal-form-dialog :deep(.el-form-item__label) {
  padding-bottom: 4px;
  font-size: 13px;
  line-height: 1.4;
}

.proposal-form-dialog :deep(.items-form-item > .el-form-item__content) {
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

  .proposal-form-dialog :deep(.el-dialog__body) {
    max-height: 82vh;
    overflow-y: auto;
  }

  .glass-dialog :deep(.el-dialog__body) {
    padding: 16px;
  }

  .pagination-wrap {
    justify-content: center;
  }
}
</style>
