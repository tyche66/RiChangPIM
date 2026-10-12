<template>
  <div class="crm-page">
    <el-card
      v-loading="loading"
      class="crm-card"
    >
      <template #header>
        <div class="crm-card__header">
          <div class="crm-detail-head">
            <el-button
              text
              class="crm-link"
              @click="router.back()"
            >
              ← 返回
            </el-button>
            <span class="crm-detail-head__title">{{ detail?.name || '客户详情' }}</span>
            <el-tag
              v-if="detail"
              :type="stageTagType(detail.stage)"
              class="crm-tag"
            >
              {{ labelOf(STAGE_MAP, detail.stage) }}
            </el-tag>
            <span
              v-if="detail?.customer_no"
              class="crm-mono"
            >{{ detail.customer_no }}</span>
          </div>
          <div class="crm-card__actions">
            <el-button
              v-if="hasPerm('customer:pii') && detail?.has_phone"
              class="crm-btn"
              @click="openPii"
            >
              查看明文
            </el-button>
            <el-button
              v-if="hasPerm('customer:transfer')"
              class="crm-btn"
              @click="openTransfer"
            >
              移交
            </el-button>
            <el-dropdown
              v-if="hasPerm('customer:edit') && detail && allowedTransitions(detail.stage).length"
              trigger="click"
              @command="(to: string) => handleTransition(to)"
            >
              <el-button class="crm-btn crm-btn--primary">
                变更阶段
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-for="to in allowedTransitions(detail.stage)"
                    :key="to"
                    :command="to"
                  >
                    转为「{{ labelOf(STAGE_MAP, to) }}」
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </template>

      <el-tabs v-model="activeTab">
        <!-- 概览 -->
        <el-tab-pane
          label="概览"
          name="overview"
        >
          <div class="summary-row">
            <div class="crm-kpi">
              <div class="crm-kpi__label">
                项目数
              </div>
              <div class="crm-kpi__value">
                {{ summary?.project_count ?? '—' }}
              </div>
            </div>
            <div class="crm-kpi">
              <div class="crm-kpi__label">
                方案数
              </div>
              <div class="crm-kpi__value">
                {{ summary?.proposal_count ?? '—' }}
              </div>
            </div>
            <div class="crm-kpi">
              <div class="crm-kpi__label">
                已确认金额
              </div>
              <div class="crm-kpi__value">
                <EmptyMetric
                  :value="summary && summary.confirmed_amount_visible ? summary.confirmed_amount : null"
                  :reason="summary && !summary.confirmed_amount_visible ? 'no_permission' : 'no_data'"
                  currency
                />
              </div>
            </div>
          </div>

          <el-steps
            :active="stageIndex"
            align-center
            finish-status="success"
            class="stage-steps"
          >
            <el-step
              v-for="stage in CUSTOMER_STAGE_ORDER"
              :key="stage"
              :title="labelOf(STAGE_MAP, stage)"
            />
          </el-steps>

          <el-descriptions
            :column="2"
            border
            class="crm-section"
          >
            <el-descriptions-item label="来源">
              {{ labelOf(CUSTOMER_SOURCE_MAP, detail?.source) }}
            </el-descriptions-item>
            <el-descriptions-item label="等级">
              {{ detail?.level || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="销售">
              {{ detail?.owner_sales_name || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="预算">
              {{ budgetText }}
            </el-descriptions-item>
            <el-descriptions-item label="手机号">
              {{ detail?.phone_masked || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="微信">
              {{ detail?.wechat_masked || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="地址">
              {{ detail?.address_masked || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="风格偏好">
              {{ detail?.style_preference || '—' }}
            </el-descriptions-item>
            <el-descriptions-item
              label="最近活跃"
              :span="2"
            >
              {{ formatBeijingTime(detail?.last_activity_at) || '—' }}
            </el-descriptions-item>
            <el-descriptions-item
              label="备注"
              :span="2"
            >
              {{ detail?.remark || '—' }}
            </el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>

        <!-- 对话 -->
        <el-tab-pane
          label="对话"
          name="dialogues"
        >
          <div
            v-if="hasPerm('customer:edit')"
            class="inline-form"
          >
            <el-select
              v-model="dialogueForm.channel"
              class="crm-select channel-select"
            >
              <el-option
                v-for="(label, value) in DIALOGUE_CHANNEL_MAP"
                :key="value"
                :label="label"
                :value="value"
              />
            </el-select>
            <el-select
              v-model="dialogueForm.direction"
              class="crm-select channel-select"
            >
              <el-option
                v-for="(label, value) in DIALOGUE_DIRECTION_MAP"
                :key="value"
                :label="label"
                :value="value"
              />
            </el-select>
            <el-input
              v-model="dialogueForm.content"
              class="crm-input"
              placeholder="记录一条对话"
            />
            <el-button
              type="primary"
              class="crm-btn crm-btn--primary"
              :loading="adding"
              @click="addDialogue"
            >
              添加
            </el-button>
          </div>
          <p
            v-if="!dialogues.length"
            class="crm-empty"
          >
            暂无对话记录
          </p>
          <ul
            v-else
            class="crm-list"
          >
            <li
              v-for="d in dialogues"
              :key="d.id"
              class="crm-list-item"
            >
              <div class="crm-list-item__meta">
                <el-tag
                  size="small"
                  class="crm-tag"
                >
                  {{ labelOf(DIALOGUE_CHANNEL_MAP, d.channel) }}
                </el-tag>
                <span>{{ labelOf(DIALOGUE_DIRECTION_MAP, d.direction) }}</span>
                <span>{{ formatBeijingTime(d.occurred_at) }}</span>
              </div>
              <div class="crm-list-item__body">
                {{ d.content }}
              </div>
            </li>
          </ul>
        </el-tab-pane>

        <!-- 需求 -->
        <el-tab-pane
          label="需求"
          name="requirements"
        >
          <div
            v-if="hasPerm('customer:edit')"
            class="inline-form"
          >
            <el-input
              v-model="requirementContent"
              class="crm-input"
              placeholder="记录一条需求"
            />
            <el-button
              type="primary"
              class="crm-btn crm-btn--primary"
              :loading="adding"
              @click="addRequirement"
            >
              添加
            </el-button>
          </div>
          <p
            v-if="!requirements.length"
            class="crm-empty"
          >
            暂无需求记录
          </p>
          <ul
            v-else
            class="crm-list"
          >
            <li
              v-for="r in requirements"
              :key="r.id"
              class="crm-list-item"
            >
              <div class="crm-list-item__meta">
                <el-tag
                  size="small"
                  :type="r.confirmed ? 'success' : 'info'"
                  class="crm-tag"
                >
                  {{ r.confirmed ? '已确认' : '待确认' }}
                </el-tag>
                <span>{{ r.source }}</span>
                <span>{{ formatBeijingTime(r.create_time) }}</span>
              </div>
              <div class="crm-list-item__body">
                {{ r.content }}
              </div>
            </li>
          </ul>
        </el-tab-pane>

        <!-- 跟进 -->
        <el-tab-pane
          label="跟进"
          name="followups"
        >
          <div
            v-if="hasPerm('customer:edit')"
            class="inline-form inline-form--wrap"
          >
            <el-select
              v-model="followForm.method"
              class="crm-select channel-select"
            >
              <el-option
                v-for="(label, value) in FOLLOW_UP_METHOD_MAP"
                :key="value"
                :label="label"
                :value="value"
              />
            </el-select>
            <el-input
              v-model="followForm.content"
              class="crm-input"
              placeholder="跟进内容"
            />
            <el-date-picker
              v-model="followForm.next_follow_at"
              type="datetime"
              class="crm-input date-field"
              placeholder="下次跟进时间"
            />
            <el-button
              type="primary"
              class="crm-btn crm-btn--primary"
              :loading="adding"
              @click="addFollowUp"
            >
              添加
            </el-button>
          </div>
          <p
            v-if="!followUps.length"
            class="crm-empty"
          >
            暂无跟进记录
          </p>
          <ul
            v-else
            class="crm-list"
          >
            <li
              v-for="f in followUps"
              :key="f.id"
              class="crm-list-item"
            >
              <div class="crm-list-item__meta">
                <el-tag
                  size="small"
                  class="crm-tag"
                >
                  {{ labelOf(FOLLOW_UP_METHOD_MAP, f.method) }}
                </el-tag>
                <span>下次：{{ formatBeijingTime(f.next_follow_at) || '—' }}</span>
                <span>{{ f.done_at ? '已完成' : '进行中' }}</span>
              </div>
              <div class="crm-list-item__body">
                {{ f.content }}
              </div>
            </li>
          </ul>
        </el-tab-pane>

        <!-- 方案 -->
        <el-tab-pane
          label="方案"
          name="proposals"
        >
          <div
            v-if="hasPerm('customer:edit')"
            class="inline-form"
          >
            <el-input
              v-model="newProposalName"
              class="crm-input"
              placeholder="新建方案名称"
            />
            <el-button
              type="primary"
              class="crm-btn crm-btn--primary"
              :loading="adding"
              @click="addProposal"
            >
              新建
            </el-button>
          </div>
          <p
            v-if="!proposals.length"
            class="crm-empty"
          >
            暂无关联方案
          </p>
          <ul
            v-else
            class="crm-list"
          >
            <li
              v-for="p in proposals"
              :key="p.id"
              class="crm-list-item proposal-item"
            >
              <div>
                <el-button
                  text
                  class="crm-link"
                  @click="router.push(`/proposals/${p.id}`)"
                >
                  {{ p.proposal_name }}
                </el-button>
                <span class="crm-mono">{{ p.proposal_no }}</span>
              </div>
              <div class="crm-list-item__meta">
                <el-tag
                  size="small"
                  :type="p.status === 'confirmed' ? 'success' : 'info'"
                  class="crm-tag"
                >
                  {{ p.status === 'confirmed' ? '已确认' : '草稿' }}
                </el-tag>
                <span>{{ formatBeijingTime(p.create_time) }}</span>
              </div>
            </li>
          </ul>
        </el-tab-pane>

        <!-- 时间线 -->
        <el-tab-pane
          label="时间线"
          name="timeline"
        >
          <p
            v-if="!timeline.length"
            class="crm-empty"
          >
            暂无活动记录
          </p>
          <el-timeline v-else>
            <el-timeline-item
              v-for="item in timeline"
              :key="item.id"
              :timestamp="formatBeijingTime(item.created_at)"
              placement="top"
            >
              <el-tag
                size="small"
                class="crm-tag"
              >
                {{ labelOf(TIMELINE_TYPE_MAP, item.type) }}
              </el-tag>
              <div class="crm-list-item__body">
                {{ item.content }}
              </div>
            </el-timeline-item>
          </el-timeline>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- PII 明文弹窗 -->
    <el-dialog
      v-model="piiVisible"
      title="客户明文信息"
      width="420px"
      align-center
    >
      <el-alert
        type="warning"
        :closable="false"
        title="此操作将被记录"
        description="查看明文会写入审计日志，并按用户限速。"
        class="pii-alert"
      />
      <el-descriptions
        :column="1"
        border
      >
        <el-descriptions-item label="手机号">
          {{ pii?.phone || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="微信">
          {{ pii?.wechat || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="地址">
          {{ pii?.address || '—' }}
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <!-- 移交弹窗 -->
    <el-dialog
      v-model="transferVisible"
      title="移交客户"
      width="420px"
      align-center
    >
      <el-select
        v-model="newOwnerId"
        class="crm-select full-width"
        placeholder="选择新的销售"
      >
        <el-option
          v-for="u in users"
          :key="u.id"
          :label="u.username"
          :value="u.id"
        />
      </el-select>
      <template #footer>
        <el-button
          class="crm-btn"
          @click="transferVisible = false"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          class="crm-btn crm-btn--primary"
          :loading="adding"
          @click="doTransfer"
        >
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { userApi } from '@/api'
import {
  customerApi,
  type CustomerDetail,
  type CustomerDialogue,
  type CustomerFollowUp,
  type CustomerPII,
  type CustomerProposalItem,
  type CustomerRequirement,
  type CustomerSummary,
  type CustomerTimelineItem,
} from '@/api/customer'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'
import EmptyMetric from '@/components/EmptyMetric.vue'
import {
  CUSTOMER_SOURCE_MAP,
  CUSTOMER_STAGE_ORDER,
  CUSTOMER_STAGE_TRANSITIONS,
  DIALOGUE_CHANNEL_MAP,
  DIALOGUE_DIRECTION_MAP,
  FOLLOW_UP_METHOD_MAP,
  STAGE_MAP,
  customerTransitionNeedsReason,
  labelOf,
} from '@/constants/crm'
import { formatBeijingTime } from '@/utils/beijingTime'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const TIMELINE_TYPE_MAP: Record<string, string> = {
  dialogue: '对话',
  follow_up: '跟进',
  requirement: '需求',
  stage_change: '阶段变更',
}

const customerId = computed(() => String(route.params.id))

function hasPerm(perm: string): boolean {
  return hasPermission(authStore.permissions, perm)
}

const loading = ref(false)
const adding = ref(false)
const detail = ref<CustomerDetail | null>(null)
const summary = ref<CustomerSummary | null>(null)
const activeTab = ref('overview')

const dialogues = ref<CustomerDialogue[]>([])
const requirements = ref<CustomerRequirement[]>([])
const followUps = ref<CustomerFollowUp[]>([])
const proposals = ref<CustomerProposalItem[]>([])
const timeline = ref<CustomerTimelineItem[]>([])

const piiVisible = ref(false)
const pii = ref<CustomerPII | null>(null)

const transferVisible = ref(false)
const newOwnerId = ref('')
const users = ref<Array<{ id: string; username: string }>>([])

const dialogueForm = reactive({ channel: 'wechat', direction: 'in', content: '' })
const requirementContent = ref('')
const followForm = reactive<{ method: string; content: string; next_follow_at: Date | null }>({
  method: 'wechat',
  content: '',
  next_follow_at: null,
})
const newProposalName = ref('')

const stageIndex = computed(() => {
  const idx = CUSTOMER_STAGE_ORDER.indexOf(detail.value?.stage ?? '')
  return idx < 0 ? 0 : idx
})

const budgetText = computed(() => {
  const d = detail.value
  if (!d) return '—'
  const min = d.budget_min
  const max = d.budget_max
  if (min == null && max == null) return '—'
  return `${min ?? '?'} ~ ${max ?? '?'}`
})

function stageTagType(stage: string): 'success' | 'danger' | 'warning' | 'info' {
  if (stage === 'won') return 'success'
  if (stage === 'lost') return 'danger'
  if (stage === 'quoted') return 'warning'
  return 'info'
}

function allowedTransitions(stage: string): string[] {
  return CUSTOMER_STAGE_TRANSITIONS[stage] ?? []
}

async function loadDetail() {
  loading.value = true
  try {
    const res = await customerApi.get(customerId.value)
    detail.value = res.data
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

async function loadSummary() {
  try {
    summary.value = (await customerApi.summary(customerId.value)).data
  } catch {
    // ignore
  }
}

async function loadDialogues() {
  try {
    dialogues.value = (await customerApi.dialogues(customerId.value, { size: 50 })).data.list
  } catch {
    // ignore
  }
}

async function loadRequirements() {
  try {
    requirements.value = (await customerApi.requirements(customerId.value, { size: 50 })).data.list
  } catch {
    // ignore
  }
}

async function loadFollowUps() {
  try {
    followUps.value = (await customerApi.followUps(customerId.value, { size: 50 })).data.list
  } catch {
    // ignore
  }
}

async function loadProposals() {
  try {
    proposals.value = (await customerApi.proposals(customerId.value, { size: 50 })).data.list
  } catch {
    // ignore
  }
}

async function loadTimeline() {
  try {
    timeline.value = (await customerApi.timeline(customerId.value, { size: 50 })).data.list
  } catch {
    // ignore
  }
}

async function openPii() {
  try {
    pii.value = (await customerApi.getPii(customerId.value)).data
    piiVisible.value = true
  } catch {
    // 拦截器已提示（含限速 429）
  }
}

async function openTransfer() {
  transferVisible.value = true
  if (users.value.length) return
  try {
    const res = (await userApi.list({ page: 1, size: 100 })) as {
      data?: { list?: Array<{ id: string; username: string }> } | Array<{ id: string; username: string }>
    }
    const raw = res.data
    users.value = Array.isArray(raw) ? raw : (raw?.list ?? [])
  } catch {
    // ignore
  }
}

async function doTransfer() {
  if (!newOwnerId.value) {
    ElMessage.warning('请选择新的销售')
    return
  }
  adding.value = true
  try {
    await customerApi.transferOwner(customerId.value, newOwnerId.value)
    ElMessage.success('已移交')
    transferVisible.value = false
    loadDetail()
  } catch {
    // ignore
  } finally {
    adding.value = false
  }
}

async function handleTransition(to: string) {
  if (!detail.value) return
  let reason: string | undefined
  if (customerTransitionNeedsReason(detail.value.stage, to)) {
    try {
      const { value } = await ElMessageBox.prompt('回退/重开需要填写原因', '阶段变更', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPlaceholder: '请输入原因',
      })
      reason = value
    } catch {
      return
    }
  }
  try {
    detail.value = (await customerApi.transitionStage(customerId.value, to, reason)).data
    ElMessage.success('阶段已更新')
    loadTimeline()
  } catch {
    // ignore
  }
}

async function addDialogue() {
  if (!dialogueForm.content.trim()) {
    ElMessage.warning('请输入对话内容')
    return
  }
  adding.value = true
  try {
    await customerApi.createDialogue(customerId.value, { ...dialogueForm })
    dialogueForm.content = ''
    ElMessage.success('已添加')
    loadDialogues()
    loadTimeline()
  } catch {
    // ignore
  } finally {
    adding.value = false
  }
}

async function addRequirement() {
  if (!requirementContent.value.trim()) {
    ElMessage.warning('请输入需求内容')
    return
  }
  adding.value = true
  try {
    await customerApi.createRequirement(customerId.value, { content: requirementContent.value })
    requirementContent.value = ''
    ElMessage.success('已添加')
    loadRequirements()
    loadTimeline()
  } catch {
    // ignore
  } finally {
    adding.value = false
  }
}

async function addFollowUp() {
  if (!followForm.content.trim()) {
    ElMessage.warning('请输入跟进内容')
    return
  }
  adding.value = true
  try {
    await customerApi.createFollowUp(customerId.value, {
      method: followForm.method,
      content: followForm.content,
      next_follow_at: followForm.next_follow_at ? followForm.next_follow_at.toISOString() : null,
    })
    followForm.content = ''
    followForm.next_follow_at = null
    ElMessage.success('已添加')
    loadFollowUps()
    loadTimeline()
  } catch {
    // ignore
  } finally {
    adding.value = false
  }
}

async function addProposal() {
  if (!newProposalName.value.trim()) {
    ElMessage.warning('请输入方案名称')
    return
  }
  adding.value = true
  try {
    await customerApi.createProposal(customerId.value, newProposalName.value)
    newProposalName.value = ''
    ElMessage.success('已创建')
    loadProposals()
  } catch {
    // ignore
  } finally {
    adding.value = false
  }
}

onMounted(() => {
  loadDetail()
  loadSummary()
  loadDialogues()
  loadRequirements()
  loadFollowUps()
  loadProposals()
  loadTimeline()
})
</script>

<style scoped>
.summary-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.stage-steps {
  margin: 8px 0 8px;
}

.inline-form {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.inline-form--wrap {
  flex-wrap: wrap;
}

.channel-select {
  width: 130px;
  flex: 0 0 auto;
}

.date-field {
  width: 200px;
  flex: 0 0 auto;
}

.proposal-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.full-width {
  width: 100%;
}

.pii-alert {
  margin-bottom: 16px;
}
</style>
