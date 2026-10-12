<template>
  <div class="crm-page">
    <el-card class="crm-card">
      <template #header>
        <div class="crm-card__header">
          <span class="crm-card__title">项目管理</span>
          <div class="crm-card__actions">
            <el-button
              v-if="hasPerm('project:edit')"
              type="primary"
              class="crm-btn crm-btn--primary"
              @click="openCreate"
            >
              新增项目
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
            placeholder="项目名称"
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
              v-for="(label, value) in PROJECT_STAGE_MAP"
              :key="value"
              :label="label"
              :value="value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="query.status"
            class="crm-select crm-field"
            placeholder="全部"
            clearable
          >
            <el-option
              v-for="(label, value) in PROJECT_STATUS_MAP"
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
          :data="projects"
          class="crm-table"
          stripe
        >
          <el-table-column
            label="项目编号"
            width="140"
          >
            <template #default="{ row }">
              <span class="crm-mono">{{ row.code || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column
            label="项目名称"
            min-width="170"
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
            </template>
          </el-table-column>
          <el-table-column
            label="客户"
            min-width="140"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              {{ row.customer_brief?.name || customerName(row.customer_id) }}
            </template>
          </el-table-column>
          <el-table-column
            label="类型"
            width="100"
          >
            <template #default="{ row }">
              {{ labelOf(PROJECT_TYPE_MAP, row.project_type) }}
            </template>
          </el-table-column>
          <el-table-column
            label="阶段"
            width="110"
            align="center"
          >
            <template #default="{ row }">
              <el-tag
                :type="stageTagType(row.stage)"
                class="crm-tag"
              >
                {{ labelOf(PROJECT_STAGE_MAP, row.stage) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            label="状态"
            width="100"
            align="center"
          >
            <template #default="{ row }">
              {{ labelOf(PROJECT_STATUS_MAP, row.status) }}
            </template>
          </el-table-column>
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
                v-if="hasPerm('project:edit') && projectAllowedTransitions(row.stage).length"
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
                      v-for="to in projectAllowedTransitions(row.stage)"
                      :key="to"
                      :command="to"
                    >
                      转为「{{ labelOf(PROJECT_STAGE_MAP, to) }}」
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-button
                v-if="hasPerm('project:edit')"
                size="small"
                text
                class="crm-link"
                @click="openEdit(row)"
              >
                编辑
              </el-button>
              <el-button
                v-if="hasPerm('project:edit')"
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
      :title="editingId ? '编辑项目' : '新增项目'"
      width="620px"
      align-center
      :close-on-click-modal="false"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="96px"
      >
        <el-form-item
          label="所属客户"
          prop="customer_id"
        >
          <el-select
            v-model="form.customer_id"
            class="crm-select"
            filterable
            :disabled="!!editingId"
            placeholder="选择客户"
          >
            <el-option
              v-for="c in customerOptions"
              :key="c.id"
              :label="c.name"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item
          label="项目名称"
          prop="name"
        >
          <el-input
            v-model="form.name"
            class="crm-input"
            placeholder="请输入项目名称"
          />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="项目编号">
              <el-input
                v-model="form.code"
                class="crm-input"
                placeholder="可选"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="项目类型">
              <el-select
                v-model="form.project_type"
                class="crm-select"
              >
                <el-option
                  v-for="(label, value) in PROJECT_TYPE_MAP"
                  :key="value"
                  :label="label"
                  :value="value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="预算">
              <el-input-number
                v-model="form.budget"
                :min="0"
                :controls="false"
                class="full-width"
                placeholder="元"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="开始日期">
              <el-date-picker
                v-model="form.start_date"
                type="date"
                value-format="YYYY-MM-DD"
                class="full-width"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="结束日期">
              <el-date-picker
                v-model="form.end_date"
                type="date"
                value-format="YYYY-MM-DD"
                class="full-width"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注">
          <el-input
            v-model="form.remark"
            type="textarea"
            :rows="2"
            class="crm-input crm-input--area"
          />
        </el-form-item>
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
import { customerApi } from '@/api/customer'
import {
  projectApi,
  type ProjectCreateRequest,
  type ProjectItem,
} from '@/api/project'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'
import {
  PROJECT_STAGE_MAP,
  PROJECT_STATUS_MAP,
  PROJECT_TYPE_MAP,
  labelOf,
  projectAllowedTransitions,
  projectTransitionNeedsReason,
} from '@/constants/crm'
import { formatBeijingTime } from '@/utils/beijingTime'

const router = useRouter()
const authStore = useAuthStore()

function hasPerm(perm: string): boolean {
  return hasPermission(authStore.permissions, perm)
}

const loading = ref(false)
const saving = ref(false)
const projects = ref<ProjectItem[]>([])
const total = ref(0)

const query = reactive({
  q: '',
  stage: '',
  status: '',
  page: 1,
  size: 20,
})

const dialogVisible = ref(false)
const editingId = ref<string | null>(null)
const formRef = ref<FormInstance>()

const customerOptions = ref<Array<{ id: string; name: string }>>([])
const customerMap = ref<Record<string, string>>({})

const emptyForm = (): ProjectCreateRequest => ({
  customer_id: '',
  name: '',
  code: '',
  project_type: 'other',
  budget: null,
  start_date: null,
  end_date: null,
  remark: '',
})

const form = reactive<ProjectCreateRequest>(emptyForm())

const rules: FormRules = {
  customer_id: [{ required: true, message: '请选择客户', trigger: 'change' }],
  name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
}

function stageTagType(stage: string): 'success' | 'danger' | 'warning' | 'info' {
  if (stage === 'closed') return 'success'
  if (stage === 'cancelled') return 'danger'
  if (stage === 'producing' || stage === 'delivered') return 'warning'
  return 'info'
}

function customerName(id: string): string {
  return customerMap.value[id] || '—'
}

async function loadCustomers() {
  try {
    const res = await customerApi.list({ page: 1, size: 100 })
    customerOptions.value = res.data.list.map((c) => ({ id: c.id, name: c.name }))
    customerMap.value = Object.fromEntries(customerOptions.value.map((c) => [c.id, c.name]))
  } catch {
    // ignore
  }
}

async function load() {
  loading.value = true
  try {
    const res = await projectApi.list({
      q: query.q || undefined,
      stage: query.stage || undefined,
      status: query.status || undefined,
      page: query.page,
      size: query.size,
    })
    projects.value = res.data.list
    total.value = res.data.total
  } catch {
    // ignore
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
  query.status = ''
  query.page = 1
  load()
}

function goDetail(id: string) {
  router.push(`/projects/${id}`)
}

function openCreate() {
  editingId.value = null
  Object.assign(form, emptyForm())
  if (!customerOptions.value.length) loadCustomers()
  dialogVisible.value = true
}

function openEdit(row: ProjectItem) {
  editingId.value = row.id
  Object.assign(form, {
    customer_id: row.customer_id,
    name: row.name,
    code: row.code ?? '',
    project_type: row.project_type,
    budget: row.budget,
    start_date: row.start_date,
    end_date: row.end_date,
    remark: row.remark ?? '',
  })
  dialogVisible.value = true
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    saving.value = true
    try {
      if (editingId.value) {
        await projectApi.update(editingId.value, {
          name: form.name,
          code: form.code || null,
          project_type: form.project_type,
          budget: form.budget,
          start_date: form.start_date,
          end_date: form.end_date,
          remark: form.remark || null,
        })
        ElMessage.success('已保存')
      } else {
        await projectApi.create(form)
        ElMessage.success('已创建')
      }
      dialogVisible.value = false
      load()
    } catch {
      // ignore
    } finally {
      saving.value = false
    }
  })
}

async function handleTransition(row: ProjectItem, to: string) {
  let reason: string | undefined
  if (projectTransitionNeedsReason(row.stage, to)) {
    try {
      const { value } = await ElMessageBox.prompt(
        to === 'cancelled' ? '取消项目需要填写原因' : '回退阶段需要填写原因',
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
        `确定将项目「${row.name}」转为「${labelOf(PROJECT_STAGE_MAP, to)}」吗？`,
        '阶段变更',
        { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return
    }
  }
  try {
    await projectApi.transitionStage(row.id, to, reason)
    ElMessage.success('阶段已更新')
    load()
  } catch {
    // ignore
  }
}

async function handleDelete(row: ProjectItem) {
  try {
    await ElMessageBox.confirm(`确定删除项目「${row.name}」吗？`, '删除项目', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await projectApi.remove(row.id)
    ElMessage.success('已删除')
    load()
  } catch {
    // ignore
  }
}

onMounted(() => {
  load()
  loadCustomers()
})
</script>

<style scoped>
.full-width {
  width: 100%;
}
</style>
