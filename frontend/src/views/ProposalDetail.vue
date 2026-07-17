<template>
  <div class="proposal-detail">
    <el-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <span>方案详情</span>
          <div>
            <el-button
              v-if="hasPerm('proposal:edit')"
              @click="handleEdit"
            >
              编辑
            </el-button>
            <el-button
              v-if="hasPerm('quotation:create') && proposal?.status !== 'confirmed'"
              type="success"
              @click="handleCreateQuotation"
            >
              生成报价单
            </el-button>
            <el-button
              v-if="hasPerm('ai:use')"
              type="warning"
              :loading="polishLoading"
              @click="handlePolish"
            >
              {{ polishFailed ? '重新润色' : 'AI 润色' }}
            </el-button>
          </div>
        </div>
      </template>

      <el-descriptions
        v-if="proposal"
        :column="2"
        border
      >
        <el-descriptions-item label="方案编号">
          {{ proposal.proposal_no }}
        </el-descriptions-item>
        <el-descriptions-item label="方案名称">
          {{ proposal.proposal_name }}
        </el-descriptions-item>
        <el-descriptions-item label="客户名称">
          {{ proposal.customer_name || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="proposal.status === 'confirmed' ? 'success' : 'info'">
            {{ proposal.status }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="AI 润色">
          <el-tag :type="polishFailed ? 'danger' : proposal.ai_polished ? 'success' : 'info'">
            {{ polishFailed ? '润色失败' : proposal.ai_polished ? '已润色' : '未润色' }}
          </el-tag>
          <span
            v-if="proposal.ai_polish_model"
            class="model-tag"
          >{{ proposal.ai_polish_model }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">
          {{ formatDate(proposal.create_time) }}
        </el-descriptions-item>
        <el-descriptions-item
          v-if="proposal.ai_polish_at"
          label="润色时间"
        >
          {{ formatDate(proposal.ai_polish_at) }}
        </el-descriptions-item>
      </el-descriptions>

      <el-divider content-position="left">
        方案商品明细
      </el-divider>

      <el-table
        v-loading="itemsLoading"
        :data="items"
        border
        stripe
      >
        <el-table-column
          prop="product_id"
          label="商品ID"
          width="240"
        />
        <el-table-column
          prop="quantity"
          label="数量"
          width="100"
        />
        <el-table-column
          prop="remark"
          label="备注"
        />
      </el-table>

      <!-- Structured polish results -->
      <div
        v-if="showPolishSection"
        style="margin-top: 20px;"
      >
        <el-divider content-position="left">
          AI 润色内容
        </el-divider>

        <!-- Failure state -->
        <el-alert
          v-if="polishFailed"
          type="error"
          :closable="false"
          show-icon
        >
          <template #title>
            AI 润色未能生成有效内容，可能是 AI 服务不可用或返回了无法解析的结果。
          </template>
          <template #default>
            <div class="polish-failure-hint">
              原始数据:
              <pre>{{ proposal?.ai_polish_content || '(空)' }}</pre>
            </div>
          </template>
        </el-alert>

        <!-- Structured content -->
        <template v-else-if="polishParsed">
          <el-alert
            type="info"
            :closable="false"
            style="margin-bottom: 12px;"
          >
            以下为 AI 生成的润色建议，仅供参考
          </el-alert>

          <!-- Summary -->
          <div
            v-if="polishParsed.summary"
            class="polish-section"
          >
            <h4 class="polish-section-title">
              <el-icon><DocumentChecked /></el-icon>
              整体亮点
            </h4>
            <p class="polish-summary">
              {{ polishParsed.summary }}
            </p>
          </div>

          <!-- Item reasons -->
          <div
            v-if="polishParsed.item_reasons?.length"
            class="polish-section"
          >
            <h4 class="polish-section-title">
              <el-icon><List /></el-icon>
              单品推荐理由
            </h4>
            <el-timeline>
              <el-timeline-item
                v-for="(reason, idx) in polishParsed.item_reasons"
                :key="idx"
                :timestamp="`产品 ${idx + 1}`"
                placement="top"
              >
                <el-card shadow="hover">
                  {{ reason }}
                </el-card>
              </el-timeline-item>
            </el-timeline>
          </div>

          <!-- Industry phrases -->
          <div
            v-if="polishParsed.industry_phrases?.length"
            class="polish-section"
          >
            <h4 class="polish-section-title">
              <el-icon><ChatDotRound /></el-icon>
              行业话术
            </h4>
            <div class="industry-phrases">
              <el-tag
                v-for="(phrase, idx) in polishParsed.industry_phrases"
                :key="idx"
                type="primary"
                effect="plain"
                style="margin: 4px;"
              >
                {{ phrase }}
              </el-tag>
            </div>
          </div>

          <!-- Raw content toggle -->
          <div class="polish-raw-toggle">
            <el-button
              text
              type="primary"
              @click="showRaw = !showRaw"
            >
              {{ showRaw ? '隐藏原始 JSON' : '查看原始 JSON' }}
            </el-button>
            <pre
              v-if="showRaw"
              class="polish-raw"
            >{{ proposal?.ai_polish_content }}</pre>
          </div>
        </template>

        <!-- Not yet polished -->
        <el-empty
          v-else-if="!polishLoading && proposal?.ai_polished"
          description="润色内容暂不可用"
        />
      </div>
    </el-card>

    <!-- Edit Dialog -->
    <el-dialog
      v-model="showEditDialog"
      title="编辑方案"
      width="500px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="editFormRef"
        :model="editForm"
        :rules="editFormRules"
        label-width="100px"
      >
        <el-form-item
          label="方案名称"
          prop="proposal_name"
        >
          <el-input v-model="editForm.proposal_name" />
        </el-form-item>
        <el-form-item
          label="客户名称"
          prop="customer_name"
        >
          <el-input v-model="editForm.customer_name" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="editLoading"
          @click="handleEditSubmit"
        >
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { DocumentChecked, List, ChatDotRound } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { proposalApi, aiApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'
import type { PolishContent } from '@/types/ai'
import { tryParseJson, isPolishFailed } from '@/types/ai'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

function hasPerm(perm: string): boolean {
  return hasPermission(authStore.permissions, perm)
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

const proposalId = computed(() => route.params.id as string)
const loading = ref(false)
const itemsLoading = ref(false)
const proposal = ref<any>(null)
const items = ref<any[]>([])
const showEditDialog = ref(false)
const editLoading = ref(false)
const polishLoading = ref(false)
const showRaw = ref(false)
const editFormRef = ref<FormInstance>()

const editForm = reactive({
  proposal_name: '',
  customer_name: '',
})

const editFormRules: FormRules = {
  proposal_name: [{ required: true, message: '请输入方案名称', trigger: 'blur' }],
}

const polishParsed = computed<PolishContent | null>(() => {
  const content = proposal.value?.ai_polish_content
  if (!content) return null
  return tryParseJson<PolishContent>(content)
})

const polishFailed = computed<boolean>(() => {
  if (!proposal.value?.ai_polished) return false
  return isPolishFailed(proposal.value?.ai_polish_content)
})

const showPolishSection = computed<boolean>(() => {
  return proposal.value?.ai_polished || polishLoading.value
})

const fetchProposal = async () => {
  loading.value = true
  try {
    const res = await proposalApi.get(proposalId.value) as any
    proposal.value = res
    items.value = res.items || []
  } catch {
    ElMessage.error('加载方案详情失败')
  } finally {
    loading.value = false
  }
}

const handleEdit = () => {
  editForm.proposal_name = proposal.value?.proposal_name || ''
  editForm.customer_name = proposal.value?.customer_name || ''
  showEditDialog.value = true
}

const handleEditSubmit = async () => {
  if (!editFormRef.value) return
  await editFormRef.value.validate(async (valid) => {
    if (!valid) return
    editLoading.value = true
    try {
      await proposalApi.update(proposalId.value, {
        proposal_name: editForm.proposal_name,
        customer_name: editForm.customer_name,
      })
      ElMessage.success('更新成功')
      showEditDialog.value = false
      fetchProposal()
    } catch {
      // error handled by interceptor
    } finally {
      editLoading.value = false
    }
  })
}

const handleCreateQuotation = () => {
  router.push(`/quotations?proposal_id=${proposalId.value}`)
}

const handlePolish = async () => {
  polishLoading.value = true
  try {
    await aiApi.polishProposal(proposalId.value)
    ElMessage.success('AI 润色完成')
    await fetchProposal()
  } catch {
    // error handled by interceptor
  } finally {
    polishLoading.value = false
  }
}

// Reset showRaw when proposal changes
watch(proposalId, () => {
  showRaw.value = false
})

onMounted(fetchProposal)
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.model-tag {
  font-size: 12px;
  color: #909399;
  margin-left: 8px;
}

.polish-failure-hint {
  margin-top: 8px;
}

.polish-failure-hint pre {
  background: #fef0f0;
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.polish-section {
  margin-top: 16px;
}

.polish-section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.polish-summary {
  background: #f0f7ff;
  padding: 12px 16px;
  border-radius: 4px;
  border-left: 3px solid #409eff;
  line-height: 1.8;
  font-size: 14px;
  color: #606266;
  margin: 0;
}

.industry-phrases {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.polish-raw-toggle {
  margin-top: 12px;
}

.polish-raw {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin-top: 8px;
}
</style>
