<template>
  <div class="categories-page">
    <el-card>
      <div class="toolbar">
        <div class="toolbar-title">
          <h2>分类管理</h2>
          <p>层级卡片化展示，提升浏览和定位效率</p>
        </div>
        <div class="toolbar-actions">
          <el-input
            v-model="filterText"
            clearable
            placeholder="搜索分类名称"
            class="capsule-input category-search"
          />
          <el-button
            v-if="canCreate"
            type="primary"
            class="capsule-btn capsule-btn-primary"
            @click="showCreateDialog = true"
          >
            新增分类
          </el-button>
        </div>
      </div>

      <div class="category-board">
        <div
          v-loading="loading"
          class="category-board-inner"
        >
          <div
            v-for="root in filteredCategories"
            :key="root.id"
            class="category-card"
          >
            <div class="category-card-header">
              <div>
                <div class="category-name-row">
                  <span class="category-name">{{ root.categoryName }}</span>
                  <el-tag size="small" type="info">L{{ root.level }}</el-tag>
                </div>
                <p class="category-meta">
                  排序 {{ root.sort || 0 }} · {{ root.children?.length || 0 }} 个子分类
                </p>
              </div>
              <div class="tree-actions visible">
                <el-button
                  v-if="canEdit"
                  text
                  class="action-link"
                  @click="handleEdit(root)"
                >
                  编辑
                </el-button>
                <el-button
                  v-if="canDelete"
                  text
                  class="action-link danger"
                  @click="handleDelete(root)"
                >
                  删除
                </el-button>
              </div>
            </div>

            <div
              v-if="root.children && root.children.length"
              class="category-children"
            >
              <div
                v-for="child in root.children"
                :key="child.id"
                class="category-child"
              >
                <div class="child-main">
                  <div>
                    <div class="child-title-row">
                      <span class="child-name">{{ child.categoryName }}</span>
                      <el-tag size="small" type="info">L{{ child.level }}</el-tag>
                    </div>
                    <p class="child-meta">
                      排序 {{ child.sort || 0 }}
                      <span v-if="child.children?.length">· {{ child.children.length }} 个子分类</span>
                    </p>
                  </div>
                  <div class="tree-actions visible">
                    <el-button
                      v-if="canEdit"
                      text
                      class="action-link"
                      @click="handleEdit(child)"
                    >
                      编辑
                    </el-button>
                    <el-button
                      v-if="canDelete"
                      text
                      class="action-link danger"
                      @click="handleDelete(child)"
                    >
                      删除
                    </el-button>
                  </div>
                </div>

                <div
                  v-if="child.children && child.children.length"
                  class="category-grandchildren"
                >
                  <span
                    v-for="grand in child.children"
                    :key="grand.id"
                    class="grand-chip"
                  >
                    <span class="grand-name">{{ grand.categoryName }}</span>
                    <span class="grand-sort">{{ grand.sort || 0 }}</span>
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div
            v-if="!loading && filteredCategories.length === 0"
            class="empty-state"
          >
            <el-empty description="暂无分类" />
          </div>
        </div>
      </div>
    </el-card>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="showCreateDialog"
      :title="editingItem ? '编辑分类' : '新增分类'"
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
          label="分类名称"
          prop="categoryName"
        >
          <el-input
            v-model="form.categoryName"
            placeholder="请输入分类名称"
          />
        </el-form-item>
        <el-form-item
          label="上级分类"
          prop="parentId"
        >
          <el-tree-select
            v-model="form.parentId"
            :data="categoryTreeForSelect"
            :props="{ checkStrictly: true, label: 'categoryName', value: 'id', children: 'children' }"
            placeholder="顶级分类（留空）"
            clearable
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item
          label="排序"
          prop="sort"
        >
          <el-input-number
            v-model="form.sort"
            :min="0"
            style="width: 100%"
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
import { categoryApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'

const authStore = useAuthStore()
const userPermissions = computed(() => authStore.userPermissions)
const canCreate = computed(() => hasPermission(userPermissions.value, 'category:create'))
const canEdit = computed(() => hasPermission(userPermissions.value, 'category:edit'))
const canDelete = computed(() => hasPermission(userPermissions.value, 'category:delete'))

const loading = ref(false)
const categories = ref<any[]>([])
const filterText = ref('')
const showCreateDialog = ref(false)
const editingItem = ref<any>(null)
const submitting = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  categoryName: '',
  parentId: undefined as string | undefined,
  sort: 0,
})

const rules: FormRules = {
  categoryName: [{ required: true, message: '请输入分类名称', trigger: 'blur' }],
}

const categoryTreeForSelect = computed(() => {
  // Flatten the tree for select, excluding the currently edited node
  const flatten = (nodes: any[], excludeId?: string): any[] => {
    const result: any[] = []
    for (const node of nodes) {
      if (node.id === excludeId) continue
      const children = node.children?.length ? flatten(node.children, excludeId) : []
      result.push({ ...node, children: children.length ? children : undefined })
    }
    return result
  }
  return flatten(categories.value, editingItem.value?.id)
})

const filteredCategories = computed(() => {
  const keyword = filterText.value.trim().toLowerCase()
  if (!keyword) return categories.value

  const matches = (node: any): boolean => {
    if (node.categoryName?.toLowerCase().includes(keyword)) return true
    return (node.children || []).some(matches)
  }

  const cloneWithMatches = (node: any): any | null => {
    if (!matches(node)) return null
    return {
      ...node,
      children: (node.children || []).map(cloneWithMatches).filter(Boolean),
    }
  }

  return categories.value.map(cloneWithMatches).filter(Boolean)
})

const normalizeCategory = (item: any): any => ({
  ...item,
  categoryName: item.category_name,
  parentId: item.parent_id,
  children: (item.children || []).map(normalizeCategory),
})

const fetchCategories = async () => {
  loading.value = true
  try {
    const res = await categoryApi.list()
    categories.value = (res.data || []).map(normalizeCategory)
  } catch {
    ElMessage.error('加载分类失败')
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  form.categoryName = ''
  form.parentId = undefined
  form.sort = 0
}

const handleEdit = (data: any) => {
  editingItem.value = data
  form.categoryName = data.categoryName
  form.parentId = data.parentId
  form.sort = data.sort ?? 0
  showCreateDialog.value = true
}

const handleSubmit = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      const payload = {
        category_name: form.categoryName,
        parent_id: form.parentId || null,
        sort: form.sort,
      }
      if (editingItem.value) {
        await categoryApi.update(editingItem.value.id, payload)
        ElMessage.success('更新成功')
      } else {
        await categoryApi.create(payload)
        ElMessage.success('创建成功')
      }
      showCreateDialog.value = false
      resetForm()
      await fetchCategories()
    } catch {
      // handled by interceptor
    } finally {
      submitting.value = false
    }
  })
}

const handleDelete = async (data: any) => {
  try {
    await ElMessageBox.confirm(`确定删除分类 "${data.categoryName}"？如有子分类则无法删除。`, '确认删除', { type: 'warning' })
    await categoryApi.delete(data.id)
    ElMessage.success('删除成功')
    await fetchCategories()
  } catch (e: any) {
    if (e !== 'cancel') {
      // handled by interceptor
    }
  }
}

onMounted(() => {
  if (canCreate.value) {
    // showCreateDialog handler is bound directly in template
  }
  fetchCategories()
})
</script>

<style scoped>
.categories-page {
  min-height: 100vh;
  background: #f0f0f0;
  padding: 24px;
  box-sizing: border-box;
}

.categories-page :deep(.el-card) {
  background: rgba(255, 255, 255, 0.68);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-radius: 28px;
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow: 0 4px 32px rgba(30, 50, 90, 0.06);
}

.categories-page :deep(.el-card__body) {
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

.category-search {
  width: 240px;
}

.category-board {
  display: grid;
  gap: 16px;
  min-height: 200px;
}

.category-board-inner {
  display: grid;
  gap: 16px;
}

.category-card {
  display: grid;
  gap: 16px;
  padding: 18px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(30, 50, 90, 0.06);
  box-shadow: 0 4px 24px rgba(30, 50, 90, 0.05);
}

.category-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.category-name-row,
.child-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.category-name,
.child-name {
  font-weight: 600;
  color: rgba(30, 50, 90, 0.92);
}

.category-name {
  font-size: 18px;
}

.child-name {
  font-size: 15px;
}

.tree-actions {
  display: flex;
  gap: 6px;
}

.tree-actions.visible {
  opacity: 1;
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

.category-meta,
.child-meta {
  margin: 6px 0 0;
  color: rgba(30, 50, 90, 0.52);
  font-size: 13px;
}

.category-children {
  display: grid;
  gap: 12px;
  padding-left: 4px;
}

.category-child {
  display: grid;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(30, 50, 90, 0.03);
  border: 1px solid rgba(30, 50, 90, 0.05);
}

.child-main {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.category-grandchildren {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.grand-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(30, 50, 90, 0.06);
  color: rgba(30, 50, 90, 0.82);
  font-size: 13px;
}

.grand-name {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.grand-sort {
  color: rgba(30, 50, 90, 0.45);
  font-family: monospace;
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
  .categories-page {
    padding: 12px;
  }
  .categories-page :deep(.el-card__body) {
    padding: 16px;
  }
  .toolbar {
    flex-direction: column;
    align-items: flex-start;
  }

  .toolbar-actions {
    width: 100%;
  }

  .category-search {
    width: 100%;
  }

  .category-card-header,
  .child-main {
    flex-direction: column;
    align-items: flex-start;
  }

  .category-card {
    padding: 16px;
  }

  .category-name {
    font-size: 16px;
  }

  .grand-name {
    max-width: 120px;
  }

  :global(.el-dialog) {
    width: 95vw !important;
    max-width: 95vw !important;
  }
}
</style>
