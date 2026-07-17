<template>
  <div class="proposals-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>方案管理</span>
          <el-button
            v-if="hasPerm('proposal:create')"
            type="primary"
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
        :data="proposals"
        border
        stripe
      >
        <el-table-column
          prop="proposal_no"
          label="方案编号"
          width="160"
        />
        <el-table-column
          prop="proposal_name"
          label="方案名称"
        />
        <el-table-column
          prop="customer_name"
          label="客户名称"
        />
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
          width="260"
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
              v-if="hasPerm('quotation:create') && row.status !== 'confirmed'"
              size="small"
              type="success"
              @click="handleCreateQuotation(row)"
            >
              生成报价
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
              v-if="hasPerm('proposal:delete')"
              size="small"
              type="danger"
              @click="handleDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Create Proposal Dialog -->
    <el-dialog
      v-model="showCreateDialog"
      title="新增方案"
      width="600px"
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
          />
        </el-form-item>
        <el-form-item
          label="客户名称"
          prop="customer_name"
        >
          <el-input
            v-model="createForm.customer_name"
            placeholder="请输入客户名称"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="createLoading"
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
              label="方案"
              value="proposal"
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

    <!-- Share Result Dialog -->
    <el-dialog
      v-model="showShareResult"
      title="分享链接已生成"
      width="500px"
      :close-on-click-modal="false"
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
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.search-form {
  margin-bottom: 16px;
}
</style>
