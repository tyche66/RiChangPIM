<template>
  <div class="suppliers-page">
    <el-card>
      <div class="toolbar">
        <h2>供应商管理</h2>
        <el-button
          v-if="canCreate"
          type="primary"
          @click="showCreateDialog = true"
        >
          新增供应商
        </el-button>
      </div>

      <div class="table-responsive">
        <el-table
          v-loading="loading"
          :data="suppliers"
          border
          stripe
        >
          <el-table-column
            prop="supplierName"
            label="供应商名称"
            min-width="200"
          />
          <el-table-column
            prop="contact"
            label="联系人"
            width="120"
          />
          <el-table-column
            prop="phone"
            label="联系电话"
            width="140"
          />
          <el-table-column
            prop="cooperationStatus"
            label="合作状态"
            width="100"
            align="center"
          >
            <template #default="{ row }">
              <el-tag
                :type="row.cooperationStatus === 'active' ? 'success' : row.cooperationStatus === 'suspended' ? 'warning' : 'danger'"
                size="small"
              >
                {{ cooperationStatusMap[row.cooperationStatus] || row.cooperationStatus }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="createTime"
            label="创建时间"
            width="160"
          >
            <template #default="{ row }">
              {{ formatDate(row.createTime) }}
            </template>
          </el-table-column>
          <el-table-column
            label="操作"
            width="160"
            align="center"
          >
            <template #default="{ row }">
              <el-button
                v-if="canEdit"
                size="small"
                @click="handleEdit(row)"
              >
                编辑
              </el-button>
              <el-button
                v-if="canDelete"
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

      <div
        v-if="!loading && suppliers.length === 0"
        class="empty-state"
      >
        <el-empty description="暂无供应商" />
      </div>
    </el-card>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="showCreateDialog"
      :title="editingItem ? '编辑供应商' : '新增供应商'"
      width="520px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="90px"
      >
        <el-form-item
          label="供应商名称"
          prop="supplierName"
        >
          <el-input
            v-model="form.supplierName"
            placeholder="请输入供应商名称"
          />
        </el-form-item>
        <el-form-item label="联系人">
          <el-input
            v-model="form.contact"
            placeholder="可选"
          />
        </el-form-item>
        <el-form-item label="联系电话">
          <el-input
            v-model="form.phone"
            placeholder="可选"
          />
        </el-form-item>
        <el-form-item
          label="合作状态"
          prop="cooperationStatus"
        >
          <el-select
            v-model="form.cooperationStatus"
            style="width: 100%"
          >
            <el-option
              label="合作中"
              value="active"
            />
            <el-option
              label="暂停合作"
              value="suspended"
            />
            <el-option
              label="终止合作"
              value="terminated"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="submitting"
          @click="handleSubmit"
        >
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { supplierApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'

const authStore = useAuthStore()
const userPermissions = computed(() => authStore.userPermissions)
const canCreate = computed(() => hasPermission(userPermissions.value, 'supplier:create'))
const canEdit = computed(() => hasPermission(userPermissions.value, 'supplier:edit'))
const canDelete = computed(() => hasPermission(userPermissions.value, 'supplier:delete'))

const cooperationStatusMap: Record<string, string> = { active: '合作中', suspended: '暂停', terminated: '已终止' }

const loading = ref(false)
const suppliers = ref<any[]>([])
const showCreateDialog = ref(false)
const editingItem = ref<any>(null)
const submitting = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  supplierName: '',
  contact: '',
  phone: '',
  cooperationStatus: 'active',
})

const rules: FormRules = {
  supplierName: [{ required: true, message: '请输入供应商名称', trigger: 'blur' }],
  cooperationStatus: [{ required: true, message: '请选择合作状态', trigger: 'change' }],
}

const fetchSuppliers = async () => {
  loading.value = true
  try {
    const res = await supplierApi.list()
    suppliers.value = res.data?.list || []
  } catch {
    ElMessage.error('加载供应商列表失败')
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  form.supplierName = ''
  form.contact = ''
  form.phone = ''
  form.cooperationStatus = 'active'
}

const handleEdit = (row: any) => {
  editingItem.value = row
  form.supplierName = row.supplierName
  form.contact = row.contact || ''
  form.phone = row.phone || ''
  form.cooperationStatus = row.cooperationStatus
  showCreateDialog.value = true
}

const handleSubmit = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      const payload = {
        supplier_name: form.supplierName,
        contact: form.contact || null,
        phone: form.phone || null,
        cooperation_status: form.cooperationStatus,
      }
      if (editingItem.value) {
        await supplierApi.update(editingItem.value.id, payload)
        ElMessage.success('更新成功')
      } else {
        await supplierApi.create(payload)
        ElMessage.success('创建成功')
      }
      showCreateDialog.value = false
      resetForm()
      await fetchSuppliers()
    } catch {
      // handled by interceptor
    } finally {
      submitting.value = false
    }
  })
}

const handleDelete = async (row: any) => {
  try {
    await ElMessageBox.confirm(`确定删除供应商 "${row.supplierName}"？`, '确认删除', { type: 'warning' })
    await supplierApi.delete(row.id)
    ElMessage.success('删除成功')
    await fetchSuppliers()
  } catch (e: any) {
    if (e !== 'cancel') {
      // handled by interceptor
    }
  }
}

const formatDate = (d: string | null | undefined) => {
  if (!d) return '-'
  return new Date(d).toLocaleString('zh-CN')
}

onMounted(fetchSuppliers)
</script>

<style scoped>
.suppliers-page {
  min-height: 100vh;
  background: #f0f0f0;
  padding: 24px;
  box-sizing: border-box;
}

.suppliers-page :deep(.el-card) {
  background: rgba(255, 255, 255, 0.68);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-radius: 28px;
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow: 0 4px 32px rgba(30, 50, 90, 0.06);
}

.suppliers-page :deep(.el-card__body) {
  padding: 24px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}

.toolbar h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: rgb(30, 50, 90);
  letter-spacing: 0.3px;
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

.empty-state {
  display: flex;
  justify-content: center;
  padding: 48px 0;
}

:global(.el-dialog) {
  border-radius: 24px;
  overflow: hidden;
}

@media (max-width: 768px) {
  .suppliers-page {
    padding: 12px;
  }
  .suppliers-page :deep(.el-card__body) {
    padding: 16px;
  }
  .toolbar {
    flex-direction: column;
    align-items: flex-start;
  }
  .toolbar h2 {
    font-size: 18px;
  }
  :global(.el-dialog) {
    width: 95vw !important;
    max-width: 95vw !important;
  }
}
</style>
