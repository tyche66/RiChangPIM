<template>
  <div class="categories-page">
    <el-card>
      <div class="toolbar">
        <h2>分类管理</h2>
        <el-button
          v-if="canCreate"
          type="primary"
          @click="showCreateDialog = true"
        >
          新增分类
        </el-button>
      </div>

      <el-tree
        v-loading="loading"
        :data="categories"
        :props="{ label: 'categoryName', children: 'children' }"
        node-key="id"
        default-expand-all
        :expand-on-click-node="false"
        class="category-tree"
      >
        <template #default="{ node, data }">
          <div class="tree-node">
            <span class="tree-label">
              {{ node.label }}
              <el-tag
                v-if="data.sort"
                size="small"
                type="info"
                style="margin-left: 8px"
              >排序:{{ data.sort }}</el-tag>
              <el-tag
                size="small"
                style="margin-left: 4px"
              >L{{ data.level }}</el-tag>
            </span>
            <span class="tree-actions">
              <el-button
                v-if="canEdit"
                size="small"
                @click="handleEdit(data)"
              >编辑</el-button>
              <el-button
                v-if="canDelete"
                size="small"
                type="danger"
                @click="handleDelete(data)"
              >删除</el-button>
            </span>
          </div>
        </template>
      </el-tree>

      <div
        v-if="!loading && categories.length === 0"
        class="empty-state"
      >
        <el-empty description="暂无分类" />
      </div>
    </el-card>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="showCreateDialog"
      :title="editingItem ? '编辑分类' : '新增分类'"
      width="480px"
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

const fetchCategories = async () => {
  loading.value = true
  try {
    const res = await categoryApi.list()
    categories.value = res.data || []
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
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 8px;
}

.toolbar h2 {
  margin: 0;
  font-size: 18px;
}

.category-tree {
  min-height: 200px;
}

.tree-node {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 4px 0;
}

.tree-label {
  flex: 1;
  font-size: 14px;
}

.tree-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}

.tree-node:hover .tree-actions {
  opacity: 1;
}

.empty-state {
  display: flex;
  justify-content: center;
  padding: 40px 0;
}
</style>
