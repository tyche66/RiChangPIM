<template>
  <div class="roles-page">
    <el-card>
      <div class="toolbar">
        <div>
          <el-button
            v-if="hasPermission(authStore.permissions, 'role:create')"
            type="primary"
            @click="editMode = 'create'; showForm = true"
          >
            新增角色
          </el-button>
        </div>
      </div>

      <div class="table-responsive">
        <el-table
          v-loading="loading"
          :data="roles"
          border
          stripe
        >
          <el-table-column
            prop="role_name"
            label="角色名称"
          />
          <el-table-column
            prop="role_code"
            label="角色编码"
          />
          <el-table-column
            prop="description"
            label="描述"
            show-overflow-tooltip
          />
          <el-table-column
            prop="create_time"
            label="创建时间"
            width="170"
          >
            <template #default="{ row }">
              {{ formatTime(row.create_time) }}
            </template>
          </el-table-column>
          <el-table-column
            label="操作"
            width="240"
          >
            <template #default="{ row }">
              <el-button
                v-if="hasPermission(authStore.permissions, 'role:edit')"
                size="small"
                @click="handleEdit(row)"
              >
                编辑
              </el-button>
              <el-button
                v-if="hasPermission(authStore.permissions, 'role:assign')"
                size="small"
                type="warning"
                @click="handleAssign(row)"
              >
                权限
              </el-button>
              <el-button
                v-if="hasPermission(authStore.permissions, 'role:delete')"
                size="small"
                type="danger"
                @click="handleDelete(row)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- Create / Edit Dialog (shared structure) -->
    <el-dialog
      v-model="showForm"
      :title="editMode === 'create' ? '新增角色' : editMode === 'edit' ? '编辑角色' : '分配权限'"
      width="600px"
      append-to-body
      lock-scroll
      @close="resetForm"
    >
      <el-form
        v-if="editMode !== 'assign'"
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="100px"
      >
        <el-form-item
          label="角色名称"
          prop="role_name"
        >
          <el-input
            v-model="form.role_name"
            placeholder="请输入角色名称"
          />
        </el-form-item>
        <el-form-item
          label="角色编码"
          prop="role_code"
        >
          <el-input
            v-model="form.role_code"
            placeholder="请输入角色编码（英文）"
            :disabled="editMode === 'edit'"
          />
        </el-form-item>
        <el-form-item
          label="描述"
          prop="description"
        >
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="2"
            placeholder="请输入描述"
          />
        </el-form-item>
      </el-form>

      <!-- Permission assignment (shown for create, edit, and assign) -->
      <div class="perm-section">
        <div class="perm-header">
          <span class="perm-title">权限分配</span>
          <el-checkbox
            :model-value="allSelected"
            :indeterminate="isIndeterminate"
            @change="toggleAll"
          >
            全选 / 全不选
          </el-checkbox>
        </div>
        <div
          v-for="(perms, resource) in groupedPermissions"
          :key="resource"
          class="perm-group"
        >
          <div class="perm-group-title">
            <el-checkbox
              :model-value="isResourceSelected(resource)"
              @change="toggleResource(resource)"
            >
              {{ resource }}
            </el-checkbox>
          </div>
          <div class="perm-group-items">
            <el-checkbox
              v-for="p in perms"
              :key="p"
              :model-value="form.permission_ids.includes(p)"
              @change="togglePerm(p)"
            >
              {{ PERMISSION_NAMES[p as keyof typeof PERMISSION_NAMES] || p }}
            </el-checkbox>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="showForm = false">
          取消
        </el-button>
        <el-button
          v-if="editMode !== 'assign'"
          type="primary"
          :loading="submitting"
          @click="submitForm"
        >
          保存
        </el-button>
        <el-button
          v-else
          type="primary"
          :loading="submitting"
          @click="submitAssign"
        >
          保存权限
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { roleApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { hasPermission, RESOURCE_PERMISSIONS, PERMISSION_NAMES } from '@/types/permissions'

const authStore = useAuthStore()

const loading = ref(false)
const submitting = ref(false)
const roles = ref<any[]>([])
const showForm = ref(false)
const editMode = ref<'create' | 'edit' | 'assign'>('create')
const formRef = ref<FormInstance>()
const checkAll = ref(false)
const isIndeterminate = ref(false)

const form = reactive({
  id: '',
  role_name: '',
  role_code: '',
  description: '',
  permission_ids: [] as string[],
})

const rules: FormRules = {
  role_name: [{ required: true, message: '请输入角色名称', trigger: 'blur' }],
  role_code: [{ required: true, message: '请输入角色编码', trigger: 'blur' }],
}

const groupedPermissions: Record<string, string[]> = RESOURCE_PERMISSIONS as Record<string, string[]>

const allSelected = computed(() => form.permission_ids.length === 49)

function isResourceSelected(resource: string): boolean {
  const perms = groupedPermissions[resource] || []
  return perms.length > 0 && perms.every((p) => form.permission_ids.includes(p))
}

function toggleAll(val: boolean) {
  checkAll.value = val
  isIndeterminate.value = false
  form.permission_ids = val ? getAllPerms() : []
}

function toggleResource(resource: string) {
  const perms = groupedPermissions[resource] || []
  const allInResourceSelected = perms.every((p) => form.permission_ids.includes(p))
  if (allInResourceSelected) {
    form.permission_ids = form.permission_ids.filter((p) => !perms.includes(p))
  } else {
    const existing = new Set(form.permission_ids)
    perms.forEach((p) => existing.add(p))
    form.permission_ids = [...existing]
  }
}

function togglePerm(perm: string) {
  const idx = form.permission_ids.indexOf(perm)
  if (idx > -1) {
    form.permission_ids.splice(idx, 1)
  } else {
    form.permission_ids.push(perm)
  }
  updateCheckAllState()
}

function updateCheckAllState() {
  const selected = form.permission_ids.length
  checkAll.value = selected === 49
  isIndeterminate.value = selected > 0 && !checkAll.value
}

function getAllPerms(): string[] {
  return Object.values(groupedPermissions).flat()
}

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return ts
  }
}

async function fetchRoles() {
  loading.value = true
  try {
    const res: any = await roleApi.list()
    roles.value = res.data?.list || []
  } catch {
    ElMessage.error('加载角色列表失败')
  } finally {
    loading.value = false
  }
}

function handleEdit(row: any) {
  editMode.value = 'edit'
  form.id = row.id
  form.role_name = row.role_name
  form.role_code = row.role_code
  form.description = row.description || ''
  form.permission_ids = []
  showForm.value = true
}

function handleAssign(row: any) {
  editMode.value = 'assign'
  form.id = row.id
  form.role_name = row.role_name
  form.role_code = row.role_code
  form.description = row.description || ''
  // 预填角色已有的权限，便于查看当前拥有哪些权限并保持可编辑
  form.permission_ids = Array.isArray(row.permission_ids) ? [...row.permission_ids] : []
  updateCheckAllState()
  showForm.value = true
}

function resetForm() {
  form.id = ''
  form.role_name = ''
  form.role_code = ''
  form.description = ''
  form.permission_ids = []
  editMode.value = 'create'
  checkAll.value = false
  isIndeterminate.value = false
  formRef.value?.resetFields()
}

async function submitForm() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      const payload = {
        role_name: form.role_name,
        role_code: form.role_code,
        description: form.description || undefined,
        permission_ids: form.permission_ids,
      }
      if (editMode.value === 'create') {
        await roleApi.create(payload)
        ElMessage.success('创建成功')
      } else if (editMode.value === 'edit') {
        await roleApi.update(form.id, payload)
        ElMessage.success('保存成功')
      }
      showForm.value = false
      fetchRoles()
    } catch {
      ElMessage.error(editMode.value === 'create' ? '创建失败' : '保存失败')
    } finally {
      submitting.value = false
    }
  })
}

async function submitAssign() {
  submitting.value = true
  try {
    await roleApi.update(form.id, {
      role_name: form.role_name,
      role_code: form.role_code,
      description: form.description || undefined,
      permission_ids: form.permission_ids,
    })
    ElMessage.success('权限分配成功')
    showForm.value = false
    fetchRoles()
  } catch {
    ElMessage.error('权限分配失败')
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row: any) {
  try {
    await ElMessageBox.confirm(`确定删除角色 "${row.role_name}"？`, '确认删除')
    await roleApi.delete(row.id)
    ElMessage.success('删除成功')
    fetchRoles()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

onMounted(fetchRoles)
</script>

<style scoped>
.roles-page {
  min-height: 100vh;
  background: #f0f0f0;
  padding: 24px;
  box-sizing: border-box;
}

.roles-page :deep(.el-card) {
  background: rgba(255, 255, 255, 0.68);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-radius: 28px;
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow: 0 4px 32px rgba(30, 50, 90, 0.06);
}

.roles-page :deep(.el-card__body) {
  padding: 24px;
}

.toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 8px;
}

.toolbar :deep(.el-button) {
  border-radius: 20px;
}

.table-responsive {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  border-radius: 12px;
}

.table-responsive :deep(.el-table) {
  min-width: 700px;
  border-radius: 12px;
  overflow: hidden;
}

.perm-section {
  margin-top: 16px;
  background: rgba(255, 255, 255, 0.5);
  border-radius: 16px;
  padding: 20px;
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid rgba(30, 50, 90, 0.06);
}

.perm-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(30, 50, 90, 0.08);
}

.perm-title {
  font-weight: 600;
  font-size: 14px;
  color: rgb(30, 50, 90);
}

.perm-group {
  margin-bottom: 12px;
}

.perm-group-title {
  font-weight: 600;
  margin-bottom: 6px;
  text-transform: capitalize;
  color: #5E6470;
}

.perm-group-items {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  padding-left: 24px;
}

.perm-group-items :deep(.el-checkbox) {
  width: calc(33.333% - 10px);
  min-width: 140px;
}

:global(.el-dialog) {
  border-radius: 24px;
  overflow: hidden;
}

@media (max-width: 768px) {
  .roles-page {
    padding: 12px;
  }
  .roles-page :deep(.el-card__body) {
    padding: 16px;
  }
  .toolbar {
    justify-content: flex-start;
  }
  :global(.el-dialog) {
    width: 95vw !important;
    max-width: 95vw !important;
  }
  .perm-group-items :deep(.el-checkbox) {
    width: calc(50% - 10px);
  }
}
</style>
