<template>
  <div class="tags-page">
    <el-card>
      <div class="toolbar">
        <div class="toolbar-title">
          <h2>标签管理</h2>
          <p>按类型聚合展示，减少纵向无限排列</p>
        </div>
        <div class="toolbar-actions">
          <el-input
            v-model="filterText"
            clearable
            placeholder="搜索标签名称/类型"
            class="capsule-input tag-search"
          />
          <el-button
            v-if="canCreate"
            type="primary"
            class="capsule-btn capsule-btn-primary"
            @click="showCreateDialog = true"
          >
            新增标签
          </el-button>
        </div>
      </div>

      <div
        v-loading="loading"
        class="tag-board"
      >
        <div
          v-for="group in groupedTags"
          :key="group.key"
          class="tag-group"
        >
          <div class="tag-group-header">
            <div>
              <h3 class="tag-group-title">
                {{ group.title }}
              </h3>
              <p class="tag-group-meta">
                {{ group.items.length }} 个标签
              </p>
            </div>
          </div>

          <div class="tag-cloud">
            <div
              v-for="row in group.items"
              :key="row.id"
              class="tag-chip"
            >
              <div class="tag-chip-main">
                <span class="tag-chip-name">{{ row.tagName }}</span>
                <span
                  v-if="row.tagType"
                  class="tag-chip-type"
                >{{ row.tagType }}</span>
              </div>
              <div class="tag-chip-actions">
                <el-button
                  v-if="canEdit"
                  text
                  class="action-link"
                  @click="handleEdit(row)"
                >
                  编辑
                </el-button>
                <el-button
                  v-if="canDelete"
                  text
                  class="action-link danger"
                  @click="handleDelete(row)"
                >
                  删除
                </el-button>
              </div>
            </div>
          </div>
        </div>

        <div
          v-if="!loading && groupedTags.length === 0"
          class="empty-state"
        >
          <el-empty description="暂无标签" />
        </div>
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
const filterText = ref('')
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

const groupedTags = computed(() => {
  const keyword = filterText.value.trim().toLowerCase()
  const source = keyword
    ? tags.value.filter((tag) => {
        const name = tag.tagName?.toLowerCase() || ''
        const type = tag.tagType?.toLowerCase() || ''
        return name.includes(keyword) || type.includes(keyword)
      })
    : tags.value

  const groups = new Map<string, { key: string; title: string; items: any[] }>()
  for (const tag of source) {
    const key = tag.tagType || '未分类'
    if (!groups.has(key)) {
      groups.set(key, { key, title: key, items: [] })
    }
    groups.get(key)!.items.push(tag)
  }

  return [...groups.values()].sort((a, b) => a.title.localeCompare(b.title, 'zh-Hans-CN'))
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
  align-items: flex-start;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}

.toolbar-title {
  display: grid;
  gap: 6px;
}

.toolbar-title h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: rgb(30, 50, 90);
  letter-spacing: 0.3px;
}

.toolbar-title p {
  margin: 0;
  color: rgba(30, 50, 90, 0.52);
  font-size: 13px;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.tag-search {
  width: 260px;
}

.tag-board {
  display: grid;
  gap: 16px;
  min-height: 200px;
}

.tag-group {
  display: grid;
  gap: 14px;
  padding: 18px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(30, 50, 90, 0.06);
  box-shadow: 0 4px 24px rgba(30, 50, 90, 0.05);
}

.tag-group-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
}

.tag-group-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: rgba(30, 50, 90, 0.92);
}

.tag-group-meta {
  margin: 6px 0 0;
  color: rgba(30, 50, 90, 0.52);
  font-size: 13px;
}

.tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.tag-chip {
  min-width: 180px;
  flex: 1 1 220px;
  display: grid;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(30, 50, 90, 0.03);
  border: 1px solid rgba(30, 50, 90, 0.05);
}

.tag-chip-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.tag-chip-name {
  font-size: 15px;
  font-weight: 600;
  color: rgba(30, 50, 90, 0.92);
}

.tag-chip-type {
  color: rgba(30, 50, 90, 0.56);
  font-size: 12px;
  white-space: nowrap;
}

.tag-chip-actions {
  display: flex;
  gap: 6px;
}

.action-link {
  padding: 0;
  min-height: 0;
  border: 0;
  background: transparent;
  color: rgba(30, 50, 90, 0.78);
  font-weight: 500;
}

.action-link:hover {
  color: rgba(30, 50, 90, 0.98);
  background: transparent;
}

.action-link.danger {
  color: #f56c6c;
}

.action-link.danger:hover {
  color: #d94b4b;
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

  .toolbar-actions {
    width: 100%;
  }

  .tag-search {
    width: 100%;
  }

  .tag-group {
    padding: 16px;
  }

  .tag-group-title {
    font-size: 16px;
  }

  .tag-chip {
    min-width: 100%;
  }

  :global(.el-dialog) {
    width: 95vw !important;
    max-width: 95vw !important;
  }
}
</style>
