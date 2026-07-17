<template>
  <div class="proposal-detail">
    <el-card
      v-loading="loading"
      class="glass-card"
    >
      <template #header>
        <div class="card-header">
          <span class="page-title">方案详情</span>
          <div class="header-actions">
            <el-button
              v-if="hasPerm('proposal:edit')"
              class="capsule-btn"
              @click="handleEdit"
            >
              编辑
            </el-button>
            <el-button
              v-if="hasPerm('quotation:create') && proposal?.status !== 'confirmed'"
              type="success"
              class="capsule-btn capsule-btn-primary"
              @click="handleCreateQuotation"
            >
              生成报价单
            </el-button>
            <el-button
              v-if="hasPerm('ai:use')"
              type="warning"
              :loading="polishLoading"
              class="capsule-btn capsule-btn-warn"
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
        class="glass-descriptions"
      >
        <el-descriptions-item label="方案编号">
          <span class="mono-text">{{ proposal.proposal_no }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="方案名称">
          {{ proposal.proposal_name }}
        </el-descriptions-item>
        <el-descriptions-item label="客户名称">
          {{ proposal.customer_name || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag
            :type="proposal.status === 'confirmed' ? 'success' : 'info'"
            class="capsule-tag"
          >
            {{ proposal.status }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="AI 润色">
          <el-tag
            :type="polishFailed ? 'danger' : proposal.ai_polished ? 'success' : 'info'"
            class="capsule-tag"
          >
            {{ polishFailed ? '润色失败' : proposal.ai_polished ? '已润色' : '未润色' }}
          </el-tag>
          <span
            v-if="proposal.ai_polish_model"
            class="model-tag"
          >{{ proposal.ai_polish_model }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">
          <span class="mono-text">{{ formatDate(proposal.create_time) }}</span>
        </el-descriptions-item>
        <el-descriptions-item
          v-if="proposal.ai_polish_at"
          label="润色时间"
        >
          <span class="mono-text">{{ formatDate(proposal.ai_polish_at) }}</span>
        </el-descriptions-item>
      </el-descriptions>

      <el-divider
        content-position="left"
        class="glass-divider"
      >
        方案商品明细
      </el-divider>

      <div class="table-wrapper">
        <el-table
          v-loading="itemsLoading"
          :data="items"
          border
          stripe
          class="items-table"
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
            align="center"
          />
          <el-table-column
            prop="remark"
            label="备注"
          />
        </el-table>
      </div>

      <!-- Structured polish results -->
      <div
        v-if="showPolishSection"
        class="polish-section-wrap"
      >
        <el-divider
          content-position="left"
          class="glass-divider"
        >
          AI 润色内容
        </el-divider>

        <!-- Failure state -->
        <el-alert
          v-if="polishFailed"
          type="error"
          :closable="false"
          show-icon
          class="glass-alert"
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
            class="glass-alert polish-hint"
          >
            以下为 AI 生成的润色建议，仅供参考
          </el-alert>

          <!-- Summary -->
          <div
            v-if="polishParsed.summary"
            class="polish-block"
          >
            <h4 class="polish-block-title">
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
            class="polish-block"
          >
            <h4 class="polish-block-title">
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
                <el-card
                  shadow="hover"
                  class="timeline-card"
                >
                  {{ reason }}
                </el-card>
              </el-timeline-item>
            </el-timeline>
          </div>

          <!-- Industry phrases -->
          <div
            v-if="polishParsed.industry_phrases?.length"
            class="polish-block"
          >
            <h4 class="polish-block-title">
              <el-icon><ChatDotRound /></el-icon>
              行业话术
            </h4>
            <div class="industry-phrases">
              <el-tag
                v-for="(phrase, idx) in polishParsed.industry_phrases"
                :key="idx"
                type="primary"
                effect="plain"
                class="capsule-tag phrase-tag"
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
              class="capsule-btn btn-text"
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
      class="glass-dialog"
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
          <el-input
            v-model="editForm.proposal_name"
            class="capsule-input"
          />
        </el-form-item>
        <el-form-item
          label="客户名称"
          prop="customer_name"
        >
          <el-input
            v-model="editForm.customer_name"
            class="capsule-input"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button
          class="capsule-btn"
          @click="showEditDialog = false"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="editLoading"
          class="capsule-btn capsule-btn-primary"
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
/* ===== CSS Variables ===== */
.proposal-detail {
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
  flex-wrap: wrap;
  gap: 12px;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--brand-deep);
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* ===== Capsule Buttons ===== */
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

.capsule-btn-warn {
  background: rgba(230, 162, 60, 0.85);
  border-color: rgba(230, 162, 60, 0.85);
}

.btn-text {
  padding: 4px 12px;
  font-size: 13px;
}

/* ===== Capsule Tags ===== */
.capsule-tag {
  border-radius: 12px;
  padding: 2px 10px;
  font-weight: 500;
}

.model-tag {
  font-size: 12px;
  color: var(--text-secondary);
  margin-left: 8px;
}

.mono-text {
  font-family: monospace;
  color: var(--text-secondary);
  font-size: 12px;
}

/* ===== Descriptions ===== */
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

/* ===== Divider ===== */
.glass-divider {
  border-color: rgba(30, 50, 90, 0.1);
  margin: 24px 0 16px;
}

.glass-divider :deep(.el-divider__text) {
  color: var(--brand-deep);
  font-weight: 600;
  font-size: 14px;
}

/* ===== Table ===== */
.table-wrapper {
  overflow-x: auto;
  border-radius: var(--radius-sm);
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

/* ===== Polish Section ===== */
.polish-section-wrap {
  margin-top: 20px;
}

.glass-alert {
  border-radius: var(--radius-sm);
  margin-bottom: 12px;
}

.polish-hint {
  margin-bottom: 16px;
}

.polish-block {
  margin-top: 20px;
}

.polish-block-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--brand-deep);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.polish-summary {
  background: var(--brand-light);
  padding: 14px 18px;
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--brand-primary);
  line-height: 1.8;
  font-size: 14px;
  color: var(--text-primary);
  margin: 0;
}

.timeline-card {
  border-radius: var(--radius-sm);
  background: var(--brand-lighter);
  border: 1px solid rgba(30, 50, 90, 0.06);
}

.industry-phrases {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.phrase-tag {
  padding: 4px 14px;
}

.polish-raw-toggle {
  margin-top: 16px;
}

.polish-failure-hint {
  margin-top: 8px;
}

.polish-failure-hint pre {
  background: rgba(245, 108, 108, 0.06);
  padding: 10px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--text-primary);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.polish-raw {
  background: var(--brand-lighter);
  padding: 12px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--text-primary);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin-top: 8px;
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

.capsule-input :deep(.el-input__wrapper) {
  border-radius: 20px;
  box-shadow: 0 0 0 1px rgba(30, 50, 90, 0.1) inset;
  padding: 4px 16px;
}

/* ===== Responsive ===== */
@media (max-width: 768px) {
  .proposal-detail {
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
  }

  .header-actions {
    width: 100%;
  }

  .header-actions .capsule-btn {
    flex: 1;
    min-width: 0;
    text-align: center;
  }

  .glass-descriptions :deep(.el-descriptions__label),
  .glass-descriptions :deep(.el-descriptions__content) {
    font-size: 12px;
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
