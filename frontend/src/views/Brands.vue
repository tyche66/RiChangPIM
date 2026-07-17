<template>
  <div class="brands-page">
    <el-card>
      <div class="toolbar">
        <h2>品牌管理</h2>
        <el-button
          v-if="canCreate"
          type="primary"
          @click="showCreateDialog = true"
        >
          新增品牌
        </el-button>
      </div>

      <div class="table-responsive">
        <el-table
          v-loading="loading"
          :data="brands"
          border
          stripe
        >
          <el-table-column
            prop="brandName"
            label="品牌名称"
            min-width="180"
          />
          <el-table-column
            prop="logoUrl"
            label="Logo"
            min-width="200"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <a
                v-if="row.logoUrl"
                :href="row.logoUrl"
                target="_blank"
                class="link"
              >{{ row.logoUrl }}</a>
              <span
                v-else
                class="text-muted"
              >-</span>
            </template>
          </el-table-column>
          <el-table-column
            prop="description"
            label="描述"
            min-width="200"
            show-overflow-tooltip
          />
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
        v-if="!loading && brands.length === 0"
        class="empty-state"
      >
        <el-empty description="暂无品牌" />
      </div>
    </el-card>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="showCreateDialog"
      :title="editingItem ? '编辑品牌' : '新增品牌'"
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
          label="品牌名称"
          prop="brandName"
        >
          <el-input
            v-model="form.brandName"
            placeholder="请输入品牌名称"
          />
        </el-form-item>
        <el-form-item label="Logo URL">
          <el-input
            v-model="form.logoUrl"
            placeholder="可选，Logo 图片链接"
          />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            placeholder="可选"
          />
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
import { brandApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'

const authStore = useAuthStore()
const userPermissions = computed(() => authStore.userPermissions)
const canCreate = computed(() => hasPermission(userPermissions.value, 'brand:create'))
const canEdit = computed(() => hasPermission(userPermissions.value, 'brand:edit'))
const canDelete = computed(() => hasPermission(userPermissions.value, 'brand:delete'))

const loading = ref(false)
const brands = ref<any[]>([])
const showCreateDialog = ref(false)
const editingItem = ref<any>(null)
const submitting = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  brandName: '',
  logoUrl: '',
  description: '',
})

const rules: FormRules = {
  brandName: [{ required: true, message: '请输入品牌名称', trigger: 'blur' }],
}

const fetchBrands = async () => {
  loading.value = true
  try {
    const res = await brandApi.list()
    brands.value = res.data?.list || []
  } catch {
    ElMessage.error('加载品牌列表失败')
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  form.brandName = ''
  form.logoUrl = ''
  form.description = ''
}

const handleEdit = (row: any) => {
  editingItem.value = row
  form.brandName = row.brandName
  form.logoUrl = row.logoUrl || ''
  form.description = row.description || ''
  showCreateDialog.value = true
}

const handleSubmit = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      const payload = {
        brand_name: form.brandName,
        logo_url: form.logoUrl || null,
        description: form.description || null,
      }
      if (editingItem.value) {
        await brandApi.update(editingItem.value.id, payload)
        ElMessage.success('更新成功')
      } else {
        await brandApi.create(payload)
        ElMessage.success('创建成功')
      }
      showCreateDialog.value = false
      resetForm()
      await fetchBrands()
    } catch {
      // handled by interceptor
    } finally {
      submitting.value = false
    }
  })
}

const handleDelete = async (row: any) => {
  try {
    await ElMessageBox.confirm(`确定删除品牌 "${row.brandName}"？`, '确认删除', { type: 'warning' })
    await brandApi.delete(row.id)
    ElMessage.success('删除成功')
    await fetchBrands()
  } catch (e: any) {
    if (e !== 'cancel') {
      // handled by interceptor
    }
  }
}

onMounted(fetchBrands)
</script>

<style scoped>
.brands-page {
  min-height: 100vh;
  background: #f0f0f0;
  padding: 24px;
  box-sizing: border-box;
}

.brands-page :deep(.el-card) {
  background: rgba(255, 255, 255, 0.68);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-radius: 28px;
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow: 0 4px 32px rgba(30, 50, 90, 0.06);
}

.brands-page :deep(.el-card__body) {
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
  min-width: 600px;
}

.table-responsive :deep(.el-table) {
  border-radius: 12px;
  overflow: hidden;
}

.empty-state {
  display: flex;
  justify-content: center;
  padding: 48px 0;
}

.link {
  color: rgb(30, 50, 90);
  text-decoration: none;
  font-weight: 500;
}

.link:hover {
  text-decoration: underline;
}

.text-muted {
  color: #909399;
}

:global(.el-dialog) {
  border-radius: 24px;
  overflow: hidden;
}

@media (max-width: 768px) {
  .brands-page {
    padding: 12px;
  }
  .brands-page :deep(.el-card__body) {
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
