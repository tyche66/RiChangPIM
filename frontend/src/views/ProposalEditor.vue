<template>
  <div class="proposal-editor">
    <el-card
      v-loading="pageLoading"
      class="glass-card"
    >
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span class="page-title">{{ isEdit ? '编辑方案' : '新增方案' }}</span>
            <template v-if="isEdit && proposal">
              <span class="cell-code">{{ proposal.proposal_no }}</span>
              <el-tag
                :type="proposal.status === 'confirmed' ? 'success' : 'info'"
                class="capsule-tag"
              >
                {{ proposalStatusMap[proposal.status] || proposal.status }}
              </el-tag>
            </template>
          </div>
          <div class="header-actions">
            <el-button
              class="capsule-btn"
              @click="handleCancel"
            >
              {{ isEdit ? '取消' : '返回' }}
            </el-button>
            <el-button
              type="primary"
              :loading="saving"
              :disabled="confirmedLock"
              class="capsule-btn capsule-btn-primary"
              @click="handleSave"
            >
              保存
            </el-button>
          </div>
        </div>
      </template>

      <!-- 已确认方案从 URL 直达编辑页时：后端会拒绝更新，前台提前给出说明 -->
      <el-alert
        v-if="confirmedLock"
        type="warning"
        :closable="false"
        show-icon
        class="glass-alert"
        title="该方案已确认，需先在详情页撤销确认后才能编辑。"
      />

      <el-divider
        content-position="left"
        class="glass-divider"
      >
        基础信息
      </el-divider>

      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-position="top"
        class="base-form"
      >
        <el-row :gutter="16">
          <el-col
            :xs="24"
            :md="12"
          >
            <el-form-item
              label="方案名称"
              prop="proposal_name"
            >
              <el-input
                v-model="form.proposal_name"
                placeholder="请输入方案名称"
                class="capsule-input"
              />
            </el-form-item>
          </el-col>
          <el-col
            :xs="24"
            :md="12"
          >
            <el-form-item
              label="客户名称"
              prop="customer_name"
            >
              <el-input
                v-model="form.customer_name"
                placeholder="请输入客户名称"
                class="capsule-input"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <!-- 创建模式：关联客户/项目可编辑；编辑模式只读，避免改项目后明细中的空间绑定失效 -->
        <el-row
          v-if="!isEdit"
          :gutter="16"
        >
          <el-col
            :xs="24"
            :md="12"
          >
            <el-form-item label="关联客户">
              <el-select
                v-model="form.customer_id"
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
          <el-col
            :xs="24"
            :md="12"
          >
            <el-form-item label="关联项目">
              <el-select
                v-model="form.project_id"
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
        <el-row
          v-else
          :gutter="16"
        >
          <el-col
            :xs="24"
            :md="12"
          >
            <el-form-item label="关联客户（只读）">
              <el-input
                :model-value="boundCustomerName"
                disabled
                class="capsule-input"
              />
            </el-form-item>
          </el-col>
          <el-col
            :xs="24"
            :md="12"
          >
            <el-form-item label="关联项目（只读）">
              <el-input
                :model-value="boundProjectName"
                disabled
                class="capsule-input"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <!-- 编辑模式：只读平面图卡（FR-2），位于商品明细区上方；管理动作统一回详情页 -->
      <template v-if="isEdit">
        <el-divider
          content-position="left"
          class="glass-divider"
        >
          方案平面图
        </el-divider>
        <div
          v-loading="floorPlansLoading"
          class="readonly-floor-plans"
        >
          <div class="rfp-toolbar">
            <span class="rfp-hint">只读展示，共 {{ readonlyPlans.length }} 张</span>
            <el-button
              link
              type="primary"
              class="rfp-manage-link"
              @click="goManageFloorPlans"
            >
              在详情页管理平面图
            </el-button>
          </div>

          <div
            v-if="!readonlyPlans.length"
            class="rfp-empty"
          >
            暂无平面图，可在详情页添加
          </div>
          <div
            v-else
            class="rfp-grid"
          >
            <div
              v-for="(plan, index) in visiblePlans"
              :key="plan.id"
              class="rfp-card"
            >
              <button
                type="button"
                class="rfp-thumb"
                :disabled="!plan.image_url"
                :title="plan.image_url ? `预览：${plan.name}` : '无预览'"
                @click="openPlanViewer(index)"
              >
                <img
                  v-if="plan.image_url"
                  :src="plan.image_url"
                  :alt="plan.name"
                  loading="lazy"
                >
                <span
                  v-else
                  class="rfp-thumb-placeholder"
                >无预览</span>
                <span
                  v-if="overflowCount > 0 && index === visiblePlans.length - 1"
                  class="rfp-overflow"
                >+{{ overflowCount }}</span>
              </button>
              <div class="rfp-meta">
                <span
                  class="rfp-name"
                  :title="plan.name"
                >{{ plan.name }}</span>
                <span
                  v-if="plan.floor_label || plan.space_label"
                  class="rfp-location"
                >
                  {{ [plan.floor_label, plan.space_label].filter(Boolean).join(' / ') }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </template>
      <el-divider
        content-position="left"
        class="glass-divider"
      >
        商品明细
      </el-divider>

      <ProposalItemEditor
        v-model="form.items"
        page
        @pick-from-list="handlePickFromList"
      />

      <!-- 效果图：优先服务方案本身，编辑时可上传并存媒体库；可绑定产品或空间 -->
      <el-divider
        content-position="left"
        class="glass-divider"
      >
        方案效果图
      </el-divider>
      <template v-if="isEdit">
        <ProposalEffectImageManager
          :proposal-id="proposalId"
          :items="form.items"
        />
      </template>
      <template v-else>
        <!-- 创建模式：先暂存，方案创建成功后一次性 batchCreate 绑定 -->
        <ProposalEffectImageManager
          v-model="effectImages"
          :items="form.items"
        />
      </template>

      <!-- 创建模式：平面图先暂存在页面里，方案创建成功后一次性 batchCreate 绑定 -->
      <template v-if="!isEdit">
        <el-divider
          content-position="left"
          class="glass-divider"
        >
          方案平面图
        </el-divider>
        <ProposalFloorPlanManager v-model="floorPlans" />
      </template>
    </el-card>

    <ImageViewer
      :images="viewerImages"
      :start-index="viewerIndex"
      @close="viewerImages = null"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { proposalApi } from '@/api'
import { proposalEffectImageApi } from '@/api/proposalEffectImages'
import { proposalFloorPlanApi } from '@/api/proposalFloorPlans'
import { customerApi } from '@/api/customer'
import { projectApi } from '@/api/project'
import { useAuthStore } from '@/stores/auth'
import type {
  EffectImageDraft,
  FloorPlanDraft,
  Proposal,
  ProposalFloorPlan,
  ProposalItem,
  ProposalToken,
} from '@/types/sales'
import type { ImageViewerImage } from '@/components/ImageViewer.vue'
import ImageViewer from '@/components/ImageViewer.vue'
import ProposalItemEditor from '@/components/ProposalItemEditor.vue'
import ProposalEffectImageManager from '@/components/ProposalEffectImageManager.vue'
import ProposalFloorPlanManager from '@/components/ProposalFloorPlanManager.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const proposalStatusMap: Record<string, string> = { draft: '草稿', confirmed: '已确认' }

const isEdit = computed(() => route.name === 'ProposalEdit')
const proposalId = computed(() => (isEdit.value ? (route.params.id as string) : ''))

const pageLoading = ref(false)
const saving = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  proposal_name: '',
  customer_name: '',
  customer_id: null as string | null,
  project_id: null as string | null,
  items: [] as ProposalItem[],
})

// Track D：新增时先暂存平面图，方案创建成功后再一次性绑定
const floorPlans = ref<FloorPlanDraft[]>([])
// 方案效果图：新增时先暂存，创建成功后再一次性绑定
const effectImages = ref<EffectImageDraft[]>([])

const formRules: FormRules = {
  proposal_name: [{ required: true, message: '请输入方案名称', trigger: 'blur' }],
}

// ---------------------------------------------------------------------------
// 客户/项目选项（创建模式）。方案明细的楼层/空间名称由业务员直接输入；
// ProjectSpace API 仍保留给后台空间维护，不作为方案通用选项来源。
// ---------------------------------------------------------------------------

const customerOptions = ref<Array<{ id: string; name: string }>>([])
const projectOptions = ref<Array<{ id: string; name: string }>>([])
const customerLoading = ref(false)

async function searchCustomers() {
  customerLoading.value = true
  try {
    const res = await customerApi.list({ page: 1, size: 20 })
    customerOptions.value = (res.data?.list || []).map((c) => ({ id: c.id, name: c.name }))
  } catch {
    customerOptions.value = []
  } finally {
    customerLoading.value = false
  }
}

async function loadProjects() {
  try {
    const res = await projectApi.list({ page: 1, size: 100 })
    projectOptions.value = (res.data?.list || []).map((p) => ({ id: p.id, name: p.name }))
  } catch {
    projectOptions.value = []
  }
}

// ---------------------------------------------------------------------------
// 编辑模式：方案 + 只读平面图 + 关联客户/项目名称解析
// ---------------------------------------------------------------------------

const proposal = ref<Proposal | null>(null)
const readonlyPlans = ref<ProposalFloorPlan[]>([])
const floorPlansLoading = ref(false)
const boundCustomerName = ref('-')
const boundProjectName = ref('-')

const confirmedLock = computed(() => Boolean(isEdit.value && proposal.value?.status === 'confirmed'))

/** 缩略图最多展示 4 张；超出部分叠在第 4 张上以「+N」提示。 */
const MAX_VISIBLE_PLANS = 4
const visiblePlans = computed(() => readonlyPlans.value.slice(0, MAX_VISIBLE_PLANS))
const overflowCount = computed(() =>
  readonlyPlans.value.length > MAX_VISIBLE_PLANS
    ? readonlyPlans.value.length - MAX_VISIBLE_PLANS
    : 0,
)

async function loadProposal() {
  pageLoading.value = true
  try {
    const res = await proposalApi.get(proposalId.value)
    proposal.value = res.data
    form.proposal_name = res.data.proposal_name || ''
    form.customer_name = res.data.customer_name || ''
    form.customer_id = res.data.customer_id || null
    form.project_id = res.data.project_id || null
    form.items = res.data.items || []
    await markPristine()
  } catch {
    ElMessage.error('加载方案详情失败')
  } finally {
    pageLoading.value = false
  }
}

async function loadFloorPlans() {
  floorPlansLoading.value = true
  try {
    const res = await proposalFloorPlanApi.list(proposalId.value)
    readonlyPlans.value = res.data?.list || []
  } catch {
    // 接口失败时留空，不用旧数据冒充当前方案（拦截器已提示）
    readonlyPlans.value = []
  } finally {
    floorPlansLoading.value = false
  }
}

/** 编辑模式把关联客户/项目解析成名称只读展示；解析失败时退回可用信息。 */
async function resolveBindingNames() {
  boundCustomerName.value = proposal.value?.customer_name?.trim() || '-'
  boundProjectName.value = '-'
  const customerId = proposal.value?.customer_id
  const projectId = proposal.value?.project_id
  const requests: Promise<void>[] = []
  if (customerId) {
    requests.push(
      customerApi
        .get(customerId)
        .then((res) => {
          boundCustomerName.value = res.data?.name || boundCustomerName.value
        })
        .catch(() => {
          // 保留 customer_name 兜底
        }),
    )
  }
  if (projectId) {
    requests.push(
      projectApi
        .get(projectId)
        .then((res) => {
          boundProjectName.value = res.data?.name || '-'
        })
        .catch(() => {
          // 展示层兜底即可，不阻塞编辑
        }),
    )
  }
  await Promise.all(requests)
}

function goManageFloorPlans() {
  router.push({ path: `/proposals/${proposalId.value}`, hash: '#floor-plans' })
}

// ---------------------------------------------------------------------------
// 只读平面图预览（复用 FR-1 的 ImageViewer）
// ---------------------------------------------------------------------------

const viewerImages = ref<ImageViewerImage[] | null>(null)
const viewerIndex = ref(0)

const planImages = computed<ImageViewerImage[]>(() =>
  readonlyPlans.value.map((plan) => ({
    url: plan.image_url || '',
    title: plan.name,
    subtitle: [plan.floor_label, plan.space_label].filter(Boolean).join(' / ') || null,
  })),
)

function openPlanViewer(planIndex: number) {
  const target = planImages.value[planIndex]
  if (!target?.url) return
  // viewer 会过滤掉无地址的项，把点击位置换算成过滤后的下标
  const usableIndex = planImages.value
    .slice(0, planIndex + 1)
    .filter((image) => Boolean(image.url)).length - 1
  viewerIndex.value = Math.max(0, usableIndex)
  viewerImages.value = planImages.value
}

// ---------------------------------------------------------------------------
// selection_token：从产品列表选品进入。token 只消费一次，读取后立即删除；
// 重复进入（刷新/历史记录）给出明确提示并回方案列表。
// ---------------------------------------------------------------------------

async function consumeSelectionToken() {
  const selectionToken = route.query.selection_token
  if (typeof selectionToken !== 'string' || !selectionToken) return
  const storageKey = `proposal_token_${selectionToken}`
  const raw = sessionStorage.getItem(storageKey)
  if (raw) sessionStorage.removeItem(storageKey)
  // 消费完立刻清理地址栏：刷新停留在页面，而不是被过期 token 踢回列表
  router.replace({ query: {} })

  if (!raw) {
    ElMessage.warning('未找到选中的商品数据，请重新从产品列表选择')
    return
  }

  let token: ProposalToken
  try {
    token = JSON.parse(raw) as ProposalToken
  } catch {
    ElMessage.warning('未找到选中的商品数据，请重新从产品列表选择')
    return
  }

  if (!token?.options?.length) {
    ElMessage.warning('选中的商品数据已使用，请重新从产品列表选择')
    return
  }

  const picked = token.options.map((opt) => ({
    _key: `picked-${opt.id}-${Date.now()}`,
    product_id: opt.id,
    quantity: 1,
    product_name: opt.product_name,
    product_no: opt.product_no,
    face_price: opt.face_price,
    stock_status: opt.stock_status,
    cover_image_url: opt.cover_image_url,
  }))

  if (isEdit.value) {
    // 已保存方案：追加并去重（已存在的产品不重复加入）
    const existing = new Set(
      form.items.filter((i) => !i.is_custom && i.product_id).map((i) => i.product_id),
    )
    form.items = [...form.items, ...picked.filter((p) => p.product_id && !existing.has(p.product_id))]
    ElMessage.success(`已从产品列表追加 ${picked.length} 个商品（去重后）`)
    return
  }
  form.items = picked
}

/** 「从产品列表选择」：跳到产品列表页，选完点「完成」带 selection_token 回来。 */
function handlePickFromList() {
  const returnTo = isEdit.value ? `/proposals/${proposalId.value}/edit` : '/proposals/create'
  router.push({
    path: '/products',
    query: { proposal_pick: '1', return_to: returnTo },
  })
}

// ---------------------------------------------------------------------------
// 未保存离开拦截：路由离开提示 + beforeunload；保存成功后的跳转不提示
// ---------------------------------------------------------------------------

const dirty = ref(false)
/** 表单灌入初始数据期间为 false，避免程序赋值被当成用户修改。 */
const hydrating = ref(false)
const allowLeave = ref(false)

watch(
  () => [form.proposal_name, form.customer_name, form.customer_id, form.project_id, form.items],
  () => {
    if (!hydrating.value) dirty.value = true
  },
  { deep: true },
)

async function markPristine() {
  hydrating.value = true
  await nextTick()
  dirty.value = false
  hydrating.value = false
}

function hasUnsavedChanges(): boolean {
  if (allowLeave.value) return false
  if (isEdit.value) return dirty.value
  // 创建模式按「是否已有内容」判断：选品带入、手工填写都算未保存内容
  return (
    form.proposal_name.trim() !== '' ||
    form.customer_name.trim() !== '' ||
    form.customer_id != null ||
    form.project_id != null ||
    form.items.length > 0 ||
    floorPlans.value.length > 0
  )
}

function confirmLeave(): Promise<boolean> {
  return ElMessageBox.confirm(
    '方案尚未保存，离开将丢失未保存的修改。确定离开吗？',
    '未保存的修改',
    {
      type: 'warning',
      confirmButtonText: '离开',
      cancelButtonText: '继续编辑',
    },
  )
    .then(() => true)
    .catch(() => false)
}

onBeforeRouteLeave(async () => {
  if (!hasUnsavedChanges()) return true
  return confirmLeave()
})

function onBeforeUnload(event: BeforeUnloadEvent) {
  if (!hasUnsavedChanges()) return
  event.preventDefault()
  event.returnValue = ''
}

// ---------------------------------------------------------------------------
// 保存 / 取消
// ---------------------------------------------------------------------------

function validateItems(): string | null {
  if (form.items.length === 0) return '请至少添加一项商品'
  for (const item of form.items) {
    if (item.is_custom) {
      const name = item.custom_product?.name?.trim()
      if (!name) return '自定义产品缺少名称'
      continue
    }
    if (typeof item.product_id !== 'string' || !item.product_id.trim()) {
      return '商品信息缺少有效产品 ID，请重新选择商品'
    }
    if (!Number.isInteger(item.quantity) || item.quantity < 1) {
      return `商品 "${item.product_name || item.product_id}" 的数量必须为正整数`
    }
  }
  return null
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

const handleSave = async () => {
  if (saving.value || confirmedLock.value) return
  const validationResult = validateItems()
  // 保存期间用户可能经「未保存拦截」确认离开：身份变了就不再提示/跳转
  const identityAtStart = pageIdentity.value

  saving.value = true
  try {
    if (formRef.value) {
      const valid = await formRef.value.validate().catch(() => false)
      if (!valid) {
        ElMessage.warning('请填写方案名称等必填信息')
        return
      }
    }
    if (!form.proposal_name.trim()) {
      ElMessage.warning('请输入方案名称')
      return
    }
    if (validationResult) {
      ElMessage.warning(validationResult)
      return
    }

    const itemsPayload = form.items.map((item) => ({
      product_id: item.is_custom ? null : item.product_id?.trim(),
      quantity: item.quantity,
      remark: item.remark?.trim() || undefined,
      project_space_id: item.project_space_id || undefined,
      floor_label: item.floor_label?.trim() || undefined,
      space_label: item.space_label?.trim() || undefined,
      material_desc: item.material_desc?.trim() || undefined,
      display_name: item.is_custom ? undefined : item.display_name?.trim() || null,
      is_custom: Boolean(item.is_custom),
      custom_product: item.is_custom
        ? {
            name: (item.custom_product?.name || '').trim(),
            face_price: item.custom_product?.face_price ?? null,
            material: item.custom_product?.material?.trim() || null,
            colors: item.custom_product?.colors?.trim() || null,
            specification: item.custom_product?.specification?.trim() || null,
            material_description: item.custom_product?.material_description?.trim() || null,
            attachment_id: item.custom_product?.attachment_id || null,
          }
        : null,
    }))

    if (isEdit.value) {
      // 编辑模式不回传 customer_id / project_id：关联关系只读，避免空间绑定失效
      await proposalApi.update(proposalId.value, {
        proposal_name: form.proposal_name.trim(),
        customer_name: form.customer_name.trim() || null,
        items: itemsPayload,
      })
      if (pageIdentity.value !== identityAtStart) return
      ElMessage.success('更新成功')
      allowLeave.value = true
      await router.push(`/proposals/${proposalId.value}`)
      return
    }

    await authStore.ensureUser()
    const creatorId = authStore.userId
    if (!creatorId) {
      ElMessage.warning('用户信息尚未加载，请稍后重试')
      return
    }

    const created = await proposalApi.create(
      {
        proposal_name: form.proposal_name.trim(),
        customer_name: form.customer_name.trim() || null,
        customer_id: form.customer_id || undefined,
        project_id: form.project_id || undefined,
        creator_id: creatorId,
        items: itemsPayload,
      },
      { suppressErrorMessage: true },
    )

    // 平面图/效果图是附加物料：绑定失败不回滚已创建的方案，但要明确告知去哪里补
    if (floorPlans.value.length && created?.data?.id) {
      try {
        await proposalFloorPlanApi.batchCreate(
          created.data.id,
          floorPlans.value.map((plan, index) => ({
            attachment_id: plan.attachment_id,
            name: plan.name,
            sort: index,
          })),
        )
      } catch {
        ElMessage.warning('方案已创建，但平面图绑定失败，请到方案详情页重新添加')
      }
    }
    if (effectImages.value.length && created?.data?.id) {
      try {
        await proposalEffectImageApi.batchCreate(
          created.data.id,
          effectImages.value.map((img, index) => ({
            attachment_id: img.attachment_id,
            name: img.name,
            sort: index,
            product_id: img.product_id || null,
            project_space_id: img.project_space_id || null,
            floor_label: img.floor_label || null,
            space_label: img.space_label || null,
          })),
        )
      } catch {
        ElMessage.warning('方案已创建，但效果图绑定失败，请到方案详情页重新添加')
      }
    }

    if (pageIdentity.value !== identityAtStart) return
    ElMessage.success('创建成功')
    allowLeave.value = true
    await router.push(`/proposals/${created.data.id}`)
  } catch (error) {
    // 编辑接口未关闭拦截器提示（保持与原详情页编辑弹窗一致），这里不再重复报错；
    // 创建接口带 suppressErrorMessage，由本页解析并给出具体失败原因
    if (!isEdit.value) {
      ElMessage.error(proposalCreateErrorMessage(error))
    }
  } finally {
    saving.value = false
  }
}

const handleCancel = async () => {
  if (hasUnsavedChanges()) {
    const confirmed = await confirmLeave()
    if (!confirmed) return
  }
  allowLeave.value = true
  if (isEdit.value) {
    await router.push(`/proposals/${proposalId.value}`)
  } else {
    await router.push('/proposals')
  }
}

// ---------------------------------------------------------------------------
// 初始化。两条路由（创建/编辑）共用本组件且 MainLayout 的 router-view 无 key，
// 同组件跨 route record 导航时实例会被复用：以页面身份（路由名+方案id）为准重建。
// ---------------------------------------------------------------------------

const pageIdentity = computed(() => `${String(route.name || '')}:${proposalId.value}`)

async function initPage() {
  proposal.value = null
  readonlyPlans.value = []
  boundCustomerName.value = '-'
  boundProjectName.value = '-'
  allowLeave.value = false
  form.proposal_name = ''
  form.customer_name = ''
  form.customer_id = null
  form.project_id = null
  form.items = []
  floorPlans.value = []
  effectImages.value = []
  viewerImages.value = null

  if (isEdit.value) {
    await loadProposal()
    resolveBindingNames()
    loadFloorPlans()
    // 已保存方案也可从产品列表选品追加（带 selection_token 返回）
    await consumeSelectionToken()
    return
  }

  await markPristine()
  // 选品入口的 token 消费（只能在创建态；读取后立即删除，只能使用一次）
  await consumeSelectionToken()
  searchCustomers()
  loadProjects()
}

watch(pageIdentity, () => {
  initPage()
})

onMounted(() => {
  window.addEventListener('beforeunload', onBeforeUnload)
  initPage()
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
})
</script>

<style scoped>
/* ===== CSS Variables ===== */
.proposal-editor {
  /* 以下别名全部指向 design-system.css 的全局语义 Token：
     浅色保持原值，深色随 .dark-mode 自动切换 */
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
  flex-wrap: wrap;
  gap: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  flex-wrap: wrap;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--brand-deep);
}

.cell-code {
  /* 走 --pim-font-mono（鸿蒙优先），裸 monospace 在 Windows 上会掉成 Courier New */
  font-family: var(--pim-font-mono);
  color: var(--text-secondary);
  font-size: 13px;
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
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

.capsule-input :deep(.el-textarea__inner) {
  border-radius: 18px;
}

.capsule-select :deep(.el-select__wrapper),
.capsule-select :deep(.el-input__wrapper) {
  border-radius: 20px;
  box-shadow: 0 0 0 1px rgba(var(--pim-brand), 0.1) inset;
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

.capsule-tag {
  border-radius: 12px;
  padding: 2px 10px;
  font-weight: 500;
}

.full-width {
  width: 100%;
}

.base-form :deep(.el-form-item) {
  margin-bottom: 14px;
}

.base-form :deep(.el-form-item__label) {
  padding-bottom: 4px;
  font-size: 13px;
  line-height: 1.4;
}

/* ===== Divider ===== */
.glass-divider {
  border-color: rgba(var(--pim-brand), 0.1);
  margin: 24px 0 16px;
}

.glass-divider :deep(.el-divider__text) {
  color: var(--brand-deep);
  font-weight: 600;
  font-size: 14px;
}

/* ===== Alert ===== */
.glass-alert {
  border-radius: var(--radius-sm);
  margin-bottom: 16px;
}

/* ===== 只读平面图卡（编辑模式） ===== */
.readonly-floor-plans {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 64px;
}

.rfp-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.rfp-hint {
  color: var(--text-secondary);
  font-size: 12px;
}

.rfp-empty {
  padding: 16px;
  border: 1px dashed var(--pim-line-strong);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
  background: var(--pim-surface-soft);
}

.rfp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
  gap: 12px;
}

.rfp-card {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--pim-line-strong);
  border-radius: var(--radius-sm);
  background: var(--pim-surface-strong);
  overflow: hidden;
}

.rfp-thumb {
  position: relative;
  display: grid;
  place-items: center;
  width: 100%;
  aspect-ratio: 4 / 3;
  padding: 0;
  border: none;
  background: var(--pim-media-bg);
  cursor: zoom-in;
}

.rfp-thumb:disabled {
  cursor: default;
}

.rfp-thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.rfp-thumb-placeholder {
  color: var(--pim-text-faint);
  font-size: 12px;
}

.rfp-overflow {
  position: absolute;
  right: 0;
  bottom: 0;
  padding: 2px 10px;
  border-top-left-radius: 10px;
  background: var(--pim-accent-solid);
  color: var(--pim-on-accent);
  font-size: 12px;
  font-weight: 600;
}

.rfp-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px 10px;
}

.rfp-name {
  color: var(--brand-deep);
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rfp-location {
  color: var(--text-secondary);
  font-size: 12px;
}

/* ===== Responsive ===== */
@media (max-width: 768px) {
  .proposal-editor {
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
  }
}
</style>
