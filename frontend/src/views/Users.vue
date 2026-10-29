<template>
  <div class="users-page">
    <el-card>
      <div class="toolbar">
        <el-form
          :inline="true"
          :model="queryParams"
          class="filter-form"
        >
          <el-form-item label="角色">
            <el-select
              v-model="queryParams.role_id"
              placeholder="全部"
              clearable
              filterable
            >
              <el-option
                v-for="r in roles"
                :key="r.id"
                :label="r.role_name"
                :value="r.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="状态">
            <el-select
              v-model="queryParams.status"
              placeholder="全部"
              clearable
            >
              <el-option
                label="启用"
                value="active"
              />
              <el-option
                label="禁用"
                value="inactive"
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
        <div>
          <el-button
            v-if="hasPermission(authStore.permissions, 'user:create')"
            type="primary"
            @click="showCreate = true"
          >
            新增用户
          </el-button>
        </div>
      </div>

      <div class="table-responsive">
        <el-table
          v-loading="loading"
          :data="users"
          border
          stripe
        >
          <!-- 排版层级用 class-name（不是 class）：class 会落到 hidden-columns 的隐藏占位 div 上，规则不生效 -->
          <el-table-column
            prop="username"
            label="用户名"
            class-name="cell-strong"
          />
          <el-table-column
            prop="email"
            label="邮箱"
            class-name="cell-soft"
          />
          <el-table-column
            prop="phone"
            label="手机"
            class-name="cell-num cell-soft"
          />
          <el-table-column label="角色">
            <template #default="{ row }">
              {{ getRoleName(row.role_id) }}
            </template>
          </el-table-column>
          <el-table-column
            prop="status"
            label="状态"
          >
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'danger'">
                {{ row.status === 'active' ? '启用' : '禁用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="last_login_time"
            label="最后登录"
            class-name="cell-meta"
            width="170"
          >
            <template #default="{ row }">
              {{ row.last_login_time ? formatTime(row.last_login_time) : '从未' }}
            </template>
          </el-table-column>
          <el-table-column
            prop="create_time"
            label="创建时间"
            class-name="cell-meta"
            width="170"
          >
            <template #default="{ row }">
              {{ formatTime(row.create_time) }}
            </template>
          </el-table-column>
          <el-table-column
            label="操作"
            width="300"
          >
            <template #default="{ row }">
              <el-button
                v-if="hasPermission(authStore.permissions, 'user:edit')"
                size="small"
                @click="handleEdit(row)"
              >
                编辑
              </el-button>
              <el-button
                v-if="authStore.roleCode === 'admin'"
                size="small"
                type="warning"
                @click="handleResetPassword(row)"
              >
                重设密码
              </el-button>
              <el-button
                v-if="hasPermission(authStore.permissions, 'user:delete')"
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

      <el-pagination
        v-model:current-page="queryParams.page"
        v-model:page-size="queryParams.size"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        class="pagination"
        @current-change="fetchUsers"
        @size-change="fetchUsers"
      />
    </el-card>

    <!-- Create Dialog -->
    <el-dialog
      v-model="showCreate"
      title="新增用户"
      width="500px"
      append-to-body
      lock-scroll
      @close="resetCreateForm"
    >
      <el-form
        ref="createFormRef"
        :model="createForm"
        :rules="createRules"
        label-width="80px"
      >
        <el-form-item
          label="用户名"
          prop="username"
        >
          <el-input
            v-model="createForm.username"
            placeholder="请输入用户名"
          />
        </el-form-item>
        <el-form-item
          label="密码"
          prop="password"
        >
          <el-input
            v-model="createForm.password"
            type="password"
            placeholder="请输入密码"
            show-password
          />
        </el-form-item>
        <el-form-item
          label="邮箱"
          prop="email"
        >
          <el-input
            v-model="createForm.email"
            placeholder="请输入邮箱"
          />
        </el-form-item>
        <el-form-item
          label="手机"
          prop="phone"
        >
          <el-input
            v-model="createForm.phone"
            placeholder="请输入手机号"
          />
        </el-form-item>
        <el-form-item
          label="角色"
          prop="role_id"
        >
          <el-select
            v-model="createForm.role_id"
            placeholder="请选择角色"
            style="width:100%"
          >
            <el-option
              v-for="r in roles"
              :key="r.id"
              :label="r.role_name"
              :value="r.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="submitting"
          @click="submitCreate"
        >
          确定
        </el-button>
      </template>
    </el-dialog>

    <!-- Edit Dialog -->
    <el-dialog
      v-model="showEdit"
      title="编辑用户"
      width="500px"
      append-to-body
      lock-scroll
      @close="resetEditForm"
    >
      <el-form
        ref="editFormRef"
        :model="editForm"
        :rules="editRules"
        label-width="80px"
      >
        <el-form-item label="用户名">
          <el-input
            :value="editForm.username"
            disabled
          />
        </el-form-item>
        <el-form-item
          label="邮箱"
          prop="email"
        >
          <el-input
            v-model="editForm.email"
            placeholder="请输入邮箱"
          />
        </el-form-item>
        <el-form-item
          label="手机"
          prop="phone"
        >
          <el-input
            v-model="editForm.phone"
            placeholder="请输入手机号"
          />
        </el-form-item>
        <el-form-item
          label="角色"
          prop="role_id"
        >
          <el-select
            v-model="editForm.role_id"
            placeholder="请选择角色"
            style="width:100%"
          >
            <el-option
              v-for="r in roles"
              :key="r.id"
              :label="r.role_name"
              :value="r.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item
          label="状态"
          prop="status"
        >
          <el-select
            v-model="editForm.status"
            placeholder="请选择状态"
            style="width:100%"
          >
            <el-option
              label="启用"
              value="active"
            />
            <el-option
              label="禁用"
              value="inactive"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEdit = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="submitting"
          @click="submitEdit"
        >
          保存
        </el-button>
      </template>
    </el-dialog>

    <!-- Reset Password Dialog -->
    <el-dialog
      v-model="showReset"
      title="重设密码"
      width="460px"
      append-to-body
      lock-scroll
      @close="resetResetForm"
    >
      <el-form
        ref="resetFormRef"
        :model="resetForm"
        :rules="resetRules"
        label-width="90px"
      >
        <el-form-item label="用户">
          <el-input
            :value="resetForm.username"
            disabled
          />
        </el-form-item>
        <el-form-item
          label="新密码"
          prop="new_password"
        >
          <el-input
            v-model="resetForm.new_password"
            type="password"
            placeholder="8-72 位新密码"
            show-password
          />
        </el-form-item>
        <el-form-item
          label="确认密码"
          prop="confirm_password"
        >
          <el-input
            v-model="resetForm.confirm_password"
            type="password"
            placeholder="请再次输入新密码"
            show-password
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showReset = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="resetting"
          @click="submitReset"
        >
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { userApi, roleApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'
import { buildResetPasswordRules } from '@/utils/passwordRules'

const authStore = useAuthStore()

const loading = ref(false)
const submitting = ref(false)
const resetting = ref(false)
const users = ref<any[]>([])
const roles = ref<any[]>([])
const total = ref(0)
const showCreate = ref(false)
const showEdit = ref(false)
const showReset = ref(false)
const createFormRef = ref<FormInstance>()
const editFormRef = ref<FormInstance>()
const resetFormRef = ref<FormInstance>()

const queryParams = reactive({
  role_id: '' as string | undefined,
  status: '' as string | undefined,
  page: 1,
  size: 20,
})

const createForm = reactive({
  username: '',
  password: '',
  email: '',
  phone: '',
  role_id: '' as string | undefined,
})

const editForm = reactive({
  id: '',
  username: '',
  email: '',
  phone: '',
  role_id: '' as string | undefined,
  status: '',
})

const resetForm = reactive({
  id: '',
  username: '',
  new_password: '',
  confirm_password: '',
})

const createRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  role_id: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

const editRules: FormRules = {
  role_id: [{ required: true, message: '请选择角色', trigger: 'change' }],
  status: [{ required: true, message: '请选择状态', trigger: 'change' }],
}

const resetRules: FormRules = buildResetPasswordRules(() => resetForm.new_password)

// 接口失败只弹一次：调用方统一 suppressErrorMessage，由这里取后端中文提示。
function apiErrorMessage(e: any, fallback: string): string {
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (detail && typeof detail === 'object') {
    if (!Array.isArray(detail) && typeof detail.msg === 'string' && detail.msg) return detail.msg
    const first = Array.isArray(detail) ? detail[0] : null
    if (first && typeof first.msg === 'string' && first.msg) return first.msg
  }
  if (!e?.response) return '网络连接失败，请稍后重试'
  return fallback
}

function getRoleName(roleId: string): string {
  const role = roles.value.find((r) => r.id === roleId)
  return role ? role.role_name : roleId
}

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return ts
  }
}

async function fetchUsers() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      page: queryParams.page,
      size: queryParams.size,
    }
    if (queryParams.role_id) params.role_id = queryParams.role_id
    if (queryParams.status) params.status = queryParams.status
    const res: any = await userApi.list(params)
    users.value = res.data?.list || []
    total.value = res.data?.total || 0
  } catch {
    ElMessage.error('加载用户列表失败')
  } finally {
    loading.value = false
  }
}

async function fetchRoles() {
  try {
    const res: any = await roleApi.list()
    roles.value = res.data?.list || []
  } catch {
    // non-fatal
  }
}

function handleSearch() {
  queryParams.page = 1
  fetchUsers()
}

function handleReset() {
  queryParams.role_id = undefined
  queryParams.status = undefined
  queryParams.page = 1
  fetchUsers()
}

function handleEdit(row: any) {
  editForm.id = row.id
  editForm.username = row.username
  editForm.email = row.email || ''
  editForm.phone = row.phone || ''
  editForm.role_id = row.role_id
  editForm.status = row.status
  showEdit.value = true
}

async function handleDelete(row: any) {
  try {
    await ElMessageBox.confirm(`确定删除用户 "${row.username}"？`, '确认删除')
  } catch {
    return
  }
  try {
    await userApi.delete(row.id, { suppressErrorMessage: true })
    ElMessage.success('删除成功')
    fetchUsers()
  } catch (e: any) {
    ElMessage.error(apiErrorMessage(e, '删除失败'))
  }
}

function handleResetPassword(row: any) {
  resetForm.id = row.id
  resetForm.username = row.username
  resetForm.new_password = ''
  resetForm.confirm_password = ''
  resetFormRef.value?.clearValidate()
  showReset.value = true
}

function resetCreateForm() {
  createForm.username = ''
  createForm.password = ''
  createForm.email = ''
  createForm.phone = ''
  createForm.role_id = undefined
  createFormRef.value?.resetFields()
}

function resetEditForm() {
  editForm.id = ''
  editForm.username = ''
  editForm.email = ''
  editForm.phone = ''
  editForm.role_id = undefined
  editForm.status = ''
  editFormRef.value?.resetFields()
}

function resetResetForm() {
  resetForm.id = ''
  resetForm.username = ''
  resetForm.new_password = ''
  resetForm.confirm_password = ''
  resetFormRef.value?.resetFields()
}

async function submitCreate() {
  if (!createFormRef.value) return
  await createFormRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      await userApi.create(
        {
          username: createForm.username,
          password: createForm.password,
          email: createForm.email || undefined,
          phone: createForm.phone || undefined,
          role_id: createForm.role_id,
        },
        { suppressErrorMessage: true }
      )
      ElMessage.success('创建成功')
      showCreate.value = false
      fetchUsers()
    } catch (e: any) {
      ElMessage.error(apiErrorMessage(e, '创建失败'))
    } finally {
      submitting.value = false
    }
  })
}

async function submitEdit() {
  if (!editFormRef.value) return
  await editFormRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      await userApi.update(
        editForm.id,
        {
          email: editForm.email || undefined,
          phone: editForm.phone || undefined,
          role_id: editForm.role_id,
          status: editForm.status,
        },
        { suppressErrorMessage: true }
      )
      ElMessage.success('保存成功')
      showEdit.value = false
      fetchUsers()
    } catch (e: any) {
      ElMessage.error(apiErrorMessage(e, '保存失败'))
    } finally {
      submitting.value = false
    }
  })
}

async function submitReset() {
  if (!resetFormRef.value) return
  await resetFormRef.value.validate(async (valid) => {
    if (!valid) return
    resetting.value = true
    try {
      await userApi.resetPassword(
        resetForm.id,
        { new_password: resetForm.new_password },
        { suppressErrorMessage: true }
      )
      ElMessage.success('密码已重设，该用户需重新登录')
      showReset.value = false
    } catch (e: any) {
      ElMessage.error(apiErrorMessage(e, '重设密码失败'))
    } finally {
      resetting.value = false
    }
  })
}

onMounted(() => {
  fetchUsers()
  fetchRoles()
})
</script>

<style scoped>
.users-page {
  min-height: 100vh;
  background: var(--pim-page);
  padding: 24px;
  box-sizing: border-box;
}

.users-page :deep(.el-card) {
  background: var(--pim-glass);
  border-radius: 28px;
  border: 1px solid var(--pim-surface-border);
  box-shadow: 0 4px 32px rgba(var(--pim-brand), 0.06);
}

.users-page :deep(.el-card__body) {
  padding: 24px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}

.filter-form {
  flex-wrap: wrap;
  gap: 4px;
}

.filter-form :deep(.el-form-item) {
  margin-bottom: 8px;
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
  min-width: 800px;
  border-radius: 12px;
  overflow: hidden;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.pagination :deep(.el-pagination) {
  flex-wrap: wrap;
  justify-content: flex-end;
}

:global(.el-dialog) {
  border-radius: 24px;
  overflow: hidden;
}

@media (max-width: 768px) {
  .users-page {
    padding: 12px;
  }
  .users-page :deep(.el-card__body) {
    padding: 16px;
  }
  .toolbar {
    flex-direction: column;
    align-items: flex-start;
  }
  .filter-form {
    width: 100%;
  }
  .filter-form :deep(.el-form-item) {
    margin-right: 8px !important;
  }
  .pagination {
    justify-content: center;
  }
  :global(.el-dialog) {
    width: 95vw !important;
    max-width: 95vw !important;
  }
}
</style>
