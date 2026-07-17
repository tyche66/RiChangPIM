<template>
  <div class="product-detail-page">
    <el-card
      v-if="loading"
      v-loading="loading"
      style="min-height: 200px;"
    />
    <el-card
      v-else-if="!product"
      class="not-found"
    >
      <el-result
        icon="error"
        title="产品不存在"
        sub-title="该产品可能已被删除"
      >
        <template #extra>
          <el-button
            type="primary"
            @click="$router.push('/products')"
          >
            返回产品列表
          </el-button>
        </template>
      </el-result>
    </el-card>
    <el-card v-else>
      <template #header>
        <div class="detail-header">
          <div class="detail-title">
            <span class="product-no">[{{ product.productNo }}]</span>
            <span class="product-name">{{ product.productName }}</span>
          </div>
          <div class="detail-actions">
            <el-tag
              v-if="product.status"
              :type="product.status === 'active' ? 'success' : product.status === 'draft' ? 'info' : 'danger'"
              size="large"
            >
              {{ statusMap[product.status] || product.status }}
            </el-tag>
            <el-tag
              v-if="product.stockStatus"
              :type="product.stockStatus === 'in_stock' ? 'success' : product.stockStatus === 'out_of_stock' ? 'danger' : 'warning'"
              size="large"
              style="margin-left: 8px"
            >
              {{ stockStatusMap[product.stockStatus] || product.stockStatus }}
            </el-tag>
            <el-button
              v-if="canEdit"
              type="primary"
              @click="editMode = !editMode"
            >
              {{ editMode ? '取消编辑' : '编辑' }}
            </el-button>
            <el-button
              v-if="canChangeStatus"
              @click="showStatusDialog = true"
            >
              改状态
            </el-button>
            <el-button
              v-if="canClone"
              @click="handleClone"
            >
              克隆
            </el-button>
            <el-button
              v-if="canDelete"
              type="danger"
              @click="handleDelete"
            >
              删除
            </el-button>
            <el-button @click="$router.push('/products')">
              返回
            </el-button>
          </div>
        </div>
      </template>

      <el-descriptions
        :column="2"
        border
      >
        <el-descriptions-item label="产品编号">
          {{ product.productNo }}
        </el-descriptions-item>
        <el-descriptions-item label="产品名称">
          {{ product.productName }}
        </el-descriptions-item>
        <el-descriptions-item label="品牌">
          {{ product.brandName || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="分类">
          {{ product.categoryName || '-' }}
        </el-descriptions-item>
        <el-descriptions-item
          label="供应商"
          :span="canViewCost ? 1 : 0"
        >
          <span v-if="canViewCost">{{ product.supplierName || '-' }}</span>
          <span
            v-else
            class="text-muted"
          >无权限查看</span>
        </el-descriptions-item>
        <el-descriptions-item label="面价">
          ¥{{ (product.facePrice || 0).toFixed(2) }}
        </el-descriptions-item>
        <el-descriptions-item
          v-if="canViewCost"
          label="成本价"
        >
          <span v-if="product.costPrice != null">¥{{ product.costPrice.toFixed(2) }}</span>
          <span
            v-else
            class="text-muted"
          >-</span>
        </el-descriptions-item>
        <el-descriptions-item
          v-if="canViewCost"
          label="材质"
        >
          {{ product.material || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">
          {{ formatDate(product.createTime) }}
        </el-descriptions-item>
        <el-descriptions-item label="更新时间">
          {{ formatDate(product.updateTime) }}
        </el-descriptions-item>
      </el-descriptions>

      <div
        v-if="product.tags && product.tags.length"
        class="tags-section"
      >
        <h4>标签</h4>
        <el-tag
          v-for="tag in product.tags"
          :key="tag"
          type="info"
          style="margin-right: 8px; margin-bottom: 8px;"
        >
          {{ tag }}
        </el-tag>
      </div>

      <!-- Edit Form -->
      <el-dialog
        v-if="editMode"
        v-model="editMode"
        title="编辑产品"
        width="600px"
        :close-on-click-modal="false"
        destroy-on-close
      >
        <el-form
          ref="productFormRef"
          :model="editForm"
          :rules="editRules"
          label-width="90px"
        >
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item
                label="产品名称"
                prop="productName"
              >
                <el-input v-model="editForm.productName" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item
                label="面价"
                prop="facePrice"
              >
                <el-input-number
                  v-model="editForm.facePrice"
                  :min="0"
                  :precision="2"
                  style="width:100%"
                />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="品牌">
                <el-select
                  v-model="editForm.brandId"
                  placeholder="请选择"
                  style="width:100%"
                >
                  <el-option
                    v-for="b in brands"
                    :key="b.id"
                    :label="b.brandName"
                    :value="b.id"
                  />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="供应商">
                <el-select
                  v-model="editForm.supplierId"
                  placeholder="请选择"
                  style="width:100%"
                >
                  <el-option
                    v-for="s in suppliers"
                    :key="s.id"
                    :label="s.supplierName"
                    :value="s.id"
                  />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="分类">
                <el-cascader
                  v-model="editForm.categoryId"
                  :options="categoryOptions"
                  :props="{ checkStrictly: true, value: 'id', label: 'categoryName', children: 'children' }"
                  style="width:100%"
                  placeholder="请选择"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="库存状态">
                <el-select
                  v-model="editForm.stockStatus"
                  style="width:100%"
                >
                  <el-option
                    label="有库存"
                    value="in_stock"
                  />
                  <el-option
                    label="缺货"
                    value="out_of_stock"
                  />
                  <el-option
                    label="预售"
                    value="preorder"
                  />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row
            v-if="canViewCost"
            :gutter="16"
          >
            <el-col :span="12">
              <el-form-item label="成本价">
                <el-input-number
                  v-model="editForm.costPrice"
                  :min="0"
                  :precision="2"
                  style="width:100%"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="材质">
                <el-input v-model="editForm.material" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="状态">
            <el-select
              v-model="editForm.status"
              style="width:100%"
            >
              <el-option
                label="上架"
                value="active"
              />
              <el-option
                label="下架"
                value="inactive"
              />
              <el-option
                label="草稿"
                value="draft"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="标签">
            <el-select
              v-model="editForm.tagIds"
              multiple
              placeholder="请选择标签"
              style="width:100%"
            >
              <el-option
                v-for="t in tags"
                :key="t.id"
                :label="t.tagName"
                :value="t.id"
              />
            </el-select>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="editMode = false">
            取消
          </el-button>
          <el-button
            type="primary"
            :loading="saving"
            @click="handleSaveEdit"
          >
            保存
          </el-button>
        </template>
      </el-dialog>

      <!-- Status Dialog -->
      <el-dialog
        v-model="showStatusDialog"
        title="修改状态"
        width="360px"
        :close-on-click-modal="false"
      >
        <el-form label-width="80px">
          <el-form-item label="状态">
            <el-select
              v-model="statusForm.status"
              style="width:100%"
            >
              <el-option
                label="上架"
                value="active"
              />
              <el-option
                label="下架"
                value="inactive"
              />
              <el-option
                label="草稿"
                value="draft"
              />
            </el-select>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showStatusDialog = false">
            取消
          </el-button>
          <el-button
            type="primary"
            :loading="statusSaving"
            @click="confirmStatusChange"
          >
            确定
          </el-button>
        </template>
      </el-dialog>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { productApi, categoryApi, brandApi, supplierApi, tagApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const userPermissions = computed(() => authStore.userPermissions)
const roleCode = computed(() => authStore.userRoleCode)

const canViewCost = computed(() => {
  const adminRoles = ['admin', 'super_admin', 'finance', 'product_manager']
  return !!roleCode.value && (adminRoles.includes(roleCode.value) || roleCode.value.startsWith('admin'))
})
const canEdit = computed(() => hasPermission(userPermissions.value, 'product:edit'))
const canDelete = computed(() => hasPermission(userPermissions.value, 'product:delete'))
const canClone = computed(() => hasPermission(userPermissions.value, 'product:clone'))
const canChangeStatus = computed(() => hasPermission(userPermissions.value, 'product:status'))

const statusMap: Record<string, string> = { active: '上架', inactive: '下架', draft: '草稿' }
const stockStatusMap: Record<string, string> = { in_stock: '有货', out_of_stock: '缺货', preorder: '预售' }

const loading = ref(false)
const product = ref<any>(null)
const editMode = ref(false)
const saving = ref(false)
const productFormRef = ref<FormInstance>()
const brands = ref<any[]>([])
const suppliers = ref<any[]>([])
const tags = ref<any[]>([])
const categoryOptions = ref<any[]>([])

const editForm = reactive({
  productName: '',
  brandId: '' as string | undefined,
  supplierId: '' as string | undefined,
  categoryId: '' as string | string[] | undefined,
  facePrice: 0,
  costPrice: undefined as number | undefined,
  material: '',
  stockStatus: 'in_stock',
  status: 'draft',
  tagIds: [] as string[],
})

const editRules: FormRules = {
  productName: [{ required: true, message: '请输入产品名称', trigger: 'blur' }],
  facePrice: [{ required: true, message: '请输入面价', trigger: 'blur' }],
  brandId: [{ required: true, message: '请选择品牌', trigger: 'change' }],
  supplierId: [{ required: true, message: '请选择供应商', trigger: 'change' }],
  categoryId: [{ required: true, message: '请选择分类', trigger: 'change' }],
}

const showStatusDialog = ref(false)
const statusForm = reactive({ status: 'draft' })
const statusSaving = ref(false)

const fetchProduct = async () => {
  loading.value = true
  try {
    const res = await productApi.get(route.params.id as string)
    product.value = res.data || res
  } catch {
    product.value = null
  } finally {
    loading.value = false
  }
}

const fetchMasterData = async () => {
  try {
    const [catRes, brandRes, supplierRes, tagRes] = await Promise.all([
      categoryApi.list(),
      brandApi.list(),
      supplierApi.list(),
      tagApi.list(),
    ])
    categoryOptions.value = catRes.data || []
    brands.value = brandRes.data?.list || []
    suppliers.value = supplierRes.data?.list || []
    tags.value = tagRes.data?.list || []
  } catch {
    // silently fail
  }
}

const populateEditForm = () => {
  if (!product.value) return
  editForm.productName = product.value.productName
  editForm.brandId = product.value.brandId
  editForm.supplierId = product.value.supplierId
  editForm.categoryId = product.value.categoryId
  editForm.facePrice = product.value.facePrice
  editForm.costPrice = product.value.costPrice ?? undefined
  editForm.material = product.value.material || ''
  editForm.stockStatus = product.value.stockStatus
  editForm.status = product.value.status
  editForm.tagIds = (product.value.tags || []).filter(Boolean)
}

const handleSaveEdit = async () => {
  if (!productFormRef.value) return
  await productFormRef.value.validate(async (valid) => {
    if (!valid) return
    saving.value = true
    try {
      const payload: Record<string, unknown> = {
        product_name: editForm.productName,
        brand_id: editForm.brandId,
        supplier_id: editForm.supplierId,
        category_id: Array.isArray(editForm.categoryId) ? editForm.categoryId[editForm.categoryId.length - 1] : editForm.categoryId,
        face_price: editForm.facePrice,
        stock_status: editForm.stockStatus,
        status: editForm.status,
        tag_ids: editForm.tagIds,
      }
      if (editForm.costPrice !== undefined && editForm.costPrice !== null) payload.cost_price = editForm.costPrice
      if (editForm.material) payload.material = editForm.material

      await productApi.update(route.params.id as string, payload)
      ElMessage.success('更新成功')
      editMode.value = false
      await fetchProduct()
    } catch {
      // handled by interceptor
    } finally {
      saving.value = false
    }
  })
}

const confirmStatusChange = async () => {
  statusSaving.value = true
  try {
    await productApi.updateStatus(route.params.id as string, statusForm.status)
    ElMessage.success('状态更新成功')
    showStatusDialog.value = false
    await fetchProduct()
  } catch {
    // handled by interceptor
  } finally {
    statusSaving.value = false
  }
}

const handleClone = async () => {
  try {
    await ElMessageBox.confirm(`确定克隆产品 "${product.value.productName}"？`, '确认克隆', { type: 'info' })
    await productApi.clone(route.params.id as string)
    ElMessage.success('克隆成功')
    await fetchProduct()
  } catch (e: any) {
    if (e !== 'cancel') {
      // handled by interceptor
    }
  }
}

const handleDelete = async () => {
  try {
    await ElMessageBox.confirm(`确定删除产品 "${product.value.productName}"？`, '确认删除', { type: 'warning' })
    await productApi.delete(route.params.id as string)
    ElMessage.success('删除成功')
    router.push('/products')
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

onMounted(() => {
  fetchProduct()
  fetchMasterData()
})

// Watch editMode to populate form when entering edit mode
import { watch } from 'vue'
watch(editMode, (val) => {
  if (val) populateEditForm()
  else {
    statusForm.status = product.value?.status || 'draft'
  }
})
</script>

<style scoped>
.detail-header {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}

.product-no {
  font-size: 14px;
  color: #909399;
  font-family: monospace;
}

.product-name {
  font-size: 20px;
  font-weight: bold;
  color: #303133;
}

.detail-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.tags-section {
  margin-top: 24px;
}

.tags-section h4 {
  margin: 0 0 12px 0;
  color: #303133;
}

.not-found {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
}

.text-muted {
  color: #909399;
}

@media (min-width: 768px) {
  .detail-header {
    flex-direction: row;
    justify-content: space-between;
    align-items: center;
  }
}
</style>
