<template>
  <div class="tags-page">
    <el-card>
      <div class="toolbar">
        <h2>标签管理</h2>
        <el-button
          v-if="canCreate"
          type="primary"
          @click="showCreateDialog = true"
        >
          新增标签
        </el-button>
      </div>

      <div class="table-responsive">
        <el-table
          v-loading="loading"
          :data="tags"
          border
          stripe
        >
          <el-table-column
            prop="tagName"
            label="标签名称"
            min-width="180"
          />
          <el-table-column
            prop="tagType"
            label="标签类型"
            width="140"
          >
            <template #default="{ row }">
              <el-tag
                v-if="row.tagType"
                type="info"
                size="small"
              >
                {{ row.tagType }}
              </el-tag>
              <span
                v-else
                class="text-muted"
              >-</span>
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
        v-if="!loading && tags.length === 0"
        class="empty-state"
      >
        <el-empty description="暂无标签" />
      </div>
    </el-card>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="showCreateDialog"
      :title="editingItem ? '编辑标签' : '新增标签'"
      width="480px"
      append-to-body
      lock-scroll
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
          label="标签名称"
          prop="tagName"
        >
          <el-input
            v-model="form.tagName"
            placeholder="请输入标签名称"
          />
        </el-form-item>
        <el-form-item label="标签类型">
          <el-input
            v-model="form.tagType"
            placeholder="可选，如：材质/风格/用途"
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
import { tagApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'

const authStore = useAuthStore()
const userPermissions = computed(() => authStore.userPermissions)
const canCreate = computed(() => hasPermission(userPermissions.value, 'tag:create'))
const canEdit = computed(() => hasPermission(userPermissions.value, 'tag:edit'))
const canDelete = computed(() => hasPermission(userPermissions.value, 'tag:delete'))

const loading = ref(false)
const tags = ref<any[]>([])
const showCreateDialog = ref(false)
const editingItem = ref<any>(null)
const submitting = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  tagName: '',
  tagType: '',
})

const rules: FormRules = {
  tagName: [{ required: true, message: '请输入标签名称', trigger: 'blur' }],
}

const normalizeTag = (item: any) => ({
  ...item,
  tagName: item.tag_name,
  tagType: item.tag_type,
  createTime: item.create_time,
})

const fetchTags = async () => {
  loading.value = true
  try {
    const res = await tagApi.list()
    tags.value = (res.data?.list || []).map(normalizeTag)
  } catch {
    ElMessage.error('加载标签列表失败')
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  form.tagName = ''
  form.tagType = ''
}

const handleEdit = (row: any) => {
  editingItem.value = row
  form.tagName = row.tagName
  form.tagType = row.tagType || ''
  showCreateDialog.value = true
}

const handleSubmit = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      const payload = {
        tag_name: form.tagName,
        tag_type: form.tagType || null,
      }
      if (editingItem.value) {
        await tagApi.update(editingItem.value.id, payload)
        ElMessage.success('更新成功')
      } else {
        await tagApi.create(payload)
        ElMessage.success('创建成功')
      }
      showCreateDialog.value = false
      resetForm()
      await fetchTags()
    } catch {
      // handled by interceptor
    } finally {
      submitting.value = false
    }
  })
}

const handleDelete = async (row: any) => {
  try {
    await ElMessageBox.confirm(`确定删除标签 "${row.tagName}"？`, '确认删除', { type: 'warning' })
    await tagApi.delete(row.id)
    ElMessage.success('删除成功')
    await fetchTags()
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

onMounted(fetchTags)
</script>

<style scoped>
.tags-page {
  min-height: 100vh;
  background: #f0f0f0;
  padding: 24px;
  box-sizing: border-box;
}

.tags-page :deep(.el-card) {
  background: rgba(255, 255, 255, 0.68);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-radius: 28px;
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow: 0 4px 32px rgba(30, 50, 90, 0.06);
}

.tags-page :deep(.el-card__body) {
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
  border-radius: 12px;
  overflow: hidden;
}

.empty-state {
  display: flex;
  justify-content: center;
  padding: 48px 0;
}

.text-muted {
  color: #909399;
}

:global(.el-dialog) {
  border-radius: 24px;
  overflow: hidden;
}

@media (max-width: 768px) {
  .tags-page {
    padding: 12px;
  }
  .tags-page :deep(.el-card__body) {
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
