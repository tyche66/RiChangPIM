<template>
  <div class="crm-page">
    <el-card class="crm-card">
      <template #header>
        <div class="crm-card__header">
          <span class="crm-card__title">客户管理</span>
          <div class="crm-card__actions">
            <el-button
              v-if="hasPerm('customer:edit')"
              class="crm-btn crm-btn--primary"
              type="primary"
              @click="openCreate"
            >
              新增客户
            </el-button>
          </div>
        </div>
      </template>

      <el-form
        class="crm-toolbar"
        :inline="true"
        @submit.prevent
      >
        <el-form-item label="关键词">
          <el-input
            v-model="query.q"
            class="crm-input crm-field"
            placeholder="客户名称 / 手机号"
            clearable
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item label="阶段">
          <el-select
            v-model="query.stage"
            class="crm-select crm-field"
            placeholder="全部"
            clearable
          >
            <el-option
              v-for="(label, value) in STAGE_MAP"
              :key="value"
              :label="label"
              :value="value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="等级">
          <el-select
            v-model="query.level"
            class="crm-select crm-field"
            placeholder="全部"
            clearable
          >
            <el-option
              v-for="(label, value) in CUSTOMER_LEVEL_MAP"
              :key="value"
              :label="label"
              :value="value"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            class="crm-btn crm-btn--primary"
            @click="handleSearch"
          >
            查询
          </el-button>
          <el-button
            class="crm-btn"
            @click="handleReset"
          >
            重置
          </el-button>
        </el-form-item>
      </el-form>

      <div class="crm-table-wrap">
        <el-table
          v-loading="loading"
          :data="customers"
          class="crm-table"
          stripe
        >
          <el-table-column
            prop="customer_no"
            label="客户编号"
            width="150"
          >
            <template #default="{ row }">
              <span class="crm-mono">{{ row.customer_no || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column
            label="客户名称"
            min-width="160"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <el-button
                text
                class="crm-link"
                @click="goDetail(row.id)"
              >
                {{ row.name }}
              </el-button>
              <el-icon
                v-if="row.has_phone"
                class="phone-flag"
                title="已留存手机号"
              >
                <Phone />
              </el-icon>
            </template>
          </el-table-column>
          <el-table-column
            label="来源"
            width="110"
          >
            <template #default="{ row }">
              {{ labelOf(CUSTOMER_SOURCE_MAP, row.source) }}
            </template>
          </el-table-column>
          <el-table-column
            label="等级"
            width="90"
            align="center"
          >
            <template #default="{ row }">
              {{ row.level || '—' }}
            </template>
          </el-table-column>
          <el-table-column
            label="阶段"
            width="120"
            align="center"
          >
            <template #default="{ row }">
              <el-tag
                :type="stageTagType(row.stage)"
                class="crm-tag"
              >
                {{ labelOf(STAGE_MAP, row.stage) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="project_count"
            label="项目"
            width="80"
            align="center"
          />
          <el-table-column
            label="最近活跃"
            width="170"
          >
            <template #default="{ row }">
              <span class="crm-mono">{{ formatBeijingTime(row.last_activity_at) || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column
            label="操作"
            width="230"
            fixed="right"
            align="center"
          >
            <template #default="{ row }">
              <el-button
                size="small"
                text
                class="crm-link"
                @click="goDetail(row.id)"
              >
                查看
              </el-button>
              <el-dropdown
                v-if="hasPerm('customer:edit') && allowedTransitions(row.stage).length"
                trigger="click"
                @command="(to: string) => handleTransition(row, to)"
              >
                <el-button
                  size="small"
                  text
                  class="crm-link"
                >
                  阶段
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item
                      v-for="to in allowedTransitions(row.stage)"
                      :key="to"
                      :command="to"
                    >
                      转为「{{ labelOf(STAGE_MAP, to) }}」
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-button
                v-if="hasPerm('customer:edit')"
                size="small"
                text
                class="crm-link"
                @click="openEdit(row)"
              >
                编辑
              </el-button>
              <el-button
                v-if="hasPerm('customer:edit')"
                size="small"
                text
                class="crm-link crm-link--danger"
                @click="handleDelete(row)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-pagination
        v-model:current-page="query.page"
        v-model:page-size="query.size"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next, jumper"
        class="crm-pagination"
        @current-change="load"
        @size-change="load"
      />
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑客户' : '新增客户'"
      width="640px"
      align-center
      :close-on-click-modal="false"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="96px"
      >
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item
              label="客户名称"
              prop="name"
            >
              <el-input
                v-model="form.name"
                class="crm-input"
                placeholder="请输入客户名称"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="来源">
              <el-select
                v-model="form.source"
                class="crm-select"
                placeholder="请选择"
              >
                <el-option
                  v-for="(label, value) in CUSTOMER_SOURCE_MAP"
                  :key="value"
                  :label="label"
                  :value="value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="等级">
              <el-select
                v-model="form.level"
                class="crm-select"
                placeholder="未定级"
                clearable
              >
                <el-option
                  v-for="(label, value) in CUSTOMER_LEVEL_MAP"
                  :key="value"
                  :label="label"
                  :value="value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="手机号">
              <el-input
                v-model="form.phone"
                class="crm-input"
                :placeholder="editingId ? '留空表示不修改' : '请输入手机号'"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="微信">
              <el-input
                v-model="form.wechat"
                class="crm-input"
                :placeholder="editingId ? '留空表示不修改' : '请输入微信号'"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="预算下限">
              <el-input-number
                v-model="form.budget_min"
                :min="0"
                :controls="false"
                class="full-width"
                placeholder="元"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="预算上限">
              <el-input-number
                v-model="form.budget_max"
                :min="0"
                :controls="false"
                class="full-width"
                placeholder="元"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="风格偏好">
              <el-input
                v-model="form.style_preference"
                class="crm-input"
                placeholder="如：奶油风 / 极简"
              />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="地址">
              <el-input
                v-model="form.address"
                class="crm-input"
                :placeholder="editingId ? '留空表示不修改' : '请输入地址'"
              />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注">
              <el-input
                v-model="form.remark"
                type="textarea"
                :rows="2"
                class="crm-input crm-input--area"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <p
          v-if="editingId"
          class="edit-hint"
        >
          手机号 / 微信 / 地址留空即不修改；提交掩码串会被后端拒绝。
        </p>
      </el-form>
      <template #footer>
        <el-button
          class="crm-btn"
          @click="dialogVisible = false"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          class="crm-btn crm-btn--primary"
          :loading="saving"
          @click="handleSubmit"
        >
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Phone } from '@element-plus/icons-vue'
import {
  customerApi,
  type CustomerCreateRequest,
  type CustomerDetail,
  type CustomerListItem,
} from '@/api/customer'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'
import {
  CUSTOMER_LEVEL_MAP,
  CUSTOMER_SOURCE_MAP,
  CUSTOMER_STAGE_TRANSITIONS,
  STAGE_MAP,
  customerTransitionNeedsReason,
  labelOf,
} from '@/constants/crm'
import { formatBeijingTime } from '@/utils/beijingTime'

const router = useRouter()
const authStore = useAuthStore()

function hasPerm(perm: string): boolean {
  return hasPermission(authStore.permissions, perm)
}

const loading = ref(false)
const saving = ref(false)
const customers = ref<CustomerListItem[]>([])
const total = ref(0)

const query = reactive({
  q: '',
  stage: '',
  level: '',
  page: 1,
  size: 20,
})

const dialogVisible = ref(false)
const editingId = ref<string | null>(null)
const formRef = ref<FormInstance>()
const initialForm = ref<string>('')

const emptyForm = (): CustomerCreateRequest => ({
  name: '',
  source: 'other',
  level: null,
  phone: '',
  wechat: '',
  address: '',
  budget_min: null,
  budget_max: null,
  style_preference: '',
  remark: '',
})

const form = reactive<CustomerCreateRequest>(emptyForm())

const rules: FormRules = {
  name: [{ required: true, message: '请输入客户名称', trigger: 'blur' }],
}

function stageTagType(stage: string): 'success' | 'danger' | 'warning' | 'info' {
  if (stage === 'won') return 'success'
  if (stage === 'lost') return 'danger'
  if (stage === 'quoted') return 'warning'
  return 'info'
}

function allowedTransitions(stage: string): string[] {
  return CUSTOMER_STAGE_TRANSITIONS[stage] ?? []
}

async function load() {
  loading.value = true
  try {
    const res = await customerApi.list({
      q: query.q || undefined,
      stage: query.stage || undefined,
      level: query.level || undefined,
      page: query.page,
      size: query.size,
    })
    customers.value = res.data.list
    total.value = res.data.total
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  query.page = 1
  load()
}

function handleReset() {
  query.q = ''
  query.stage = ''
  query.level = ''
  query.page = 1
  load()
}

function goDetail(id: string) {
  router.push(`/customers/${id}`)
}

function openCreate() {
  editingId.value = null
  Object.assign(form, emptyForm())
  dialogVisible.value = true
}

async function openEdit(row: CustomerListItem) {
  editingId.value = row.id
  try {
    const res = await customerApi.get(row.id)
    const d: CustomerDetail = res.data
    Object.assign(form, {
      name: d.name,
      source: d.source,
      level: d.level,
      phone: '',
      wechat: '',
      address: '',
      budget_min: d.budget_min,
      budget_max: d.budget_max,
      style_preference: d.style_preference ?? '',
      remark: d.remark ?? '',
    })
    initialForm.value = JSON.stringify(form)
    dialogVisible.value = true
  } catch {
    // ignore
  }
}

function buildUpdatePayload(): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  const initial = initialForm.value ? JSON.parse(initialForm.value) : {}
  const keys: Array<keyof CustomerCreateRequest> = [
    'name',
    'source',
    'level',
    'phone',
    'wechat',
    'address',
    'budget_min',
    'budget_max',
    'style_preference',
    'remark',
  ]
  for (const key of keys) {
    const current = form[key]
    if (JSON.stringify(current) !== JSON.stringify(initial[key])) {
      // 空字符串的 PII 视为「不修改」，避免把明文空值写回
      if ((key === 'phone' || key === 'wechat' || key === 'address') && current === '') continue
      payload[key] = current === '' ? null : current
    }
  }
  return payload
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    saving.value = true
    try {
      if (editingId.value) {
        const payload = buildUpdatePayload()
        if (!Object.keys(payload).length) {
          ElMessage.info('没有需要保存的修改')
          dialogVisible.value = false
          return
        }
        await customerApi.update(editingId.value, payload)
        ElMessage.success('已保存')
      } else {
        await customerApi.create(form)
        ElMessage.success('已创建')
      }
      dialogVisible.value = false
      load()
    } catch {
      // 拦截器已提示
    } finally {
      saving.value = false
    }
  })
}

async function handleTransition(row: CustomerListItem, to: string) {
  let reason: string | undefined
  if (customerTransitionNeedsReason(row.stage, to)) {
    try {
      const { value } = await ElMessageBox.prompt(
        `从「${labelOf(STAGE_MAP, row.stage)}」回退/重开到「${labelOf(STAGE_MAP, to)}」需要填写原因`,
        '阶段变更',
        { confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '请输入原因' },
      )
      reason = value
    } catch {
      return
    }
  } else {
    try {
      await ElMessageBox.confirm(
        `确定将客户「${row.name}」转为「${labelOf(STAGE_MAP, to)}」吗？`,
        '阶段变更',
        { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return
    }
  }
  try {
    await customerApi.transitionStage(row.id, to, reason)
    ElMessage.success('阶段已更新')
    load()
  } catch {
    // ignore
  }
}

async function handleDelete(row: CustomerListItem) {
  try {
    await ElMessageBox.confirm(`确定删除客户「${row.name}」吗？`, '删除客户', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await customerApi.remove(row.id)
    ElMessage.success('已删除')
    load()
  } catch (err: unknown) {
    const detail = (err as { response?: { data?: { detail?: { code?: number } } } })?.response
      ?.data?.detail
    if (detail?.code === 40902 && ['admin', 'manager'].includes(authStore.roleCode ?? '')) {
      try {
        await ElMessageBox.confirm('该客户存在未处理子记录，是否级联删除全部子记录？', '级联删除', {
          confirmButtonText: '级联删除',
          cancelButtonText: '取消',
          type: 'warning',
        })
        await customerApi.remove(row.id, true)
        ElMessage.success('已级联删除')
        load()
      } catch {
        // ignore
      }
    }
  }
}

onMounted(load)
</script>

<style scoped>
.phone-flag {
  margin-left: 6px;
  color: var(--pim-accent-solid);
  vertical-align: middle;
}

.full-width {
  width: 100%;
}

.edit-hint {
  margin: 0;
  color: var(--pim-text-secondary);
  font-size: 12px;
  line-height: 1.6;
}
</style>
