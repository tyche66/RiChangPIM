<template>
  <div class="products-page">
    <el-card>
      <div class="toolbar">
        <el-form
          :inline="true"
          :model="queryParams"
          class="filter-form"
        >
          <el-form-item label="关键词">
            <el-input
              v-model="queryParams.keyword"
              placeholder="产品名称/编号"
              clearable
              class="filter-input"
            />
          </el-form-item>
          <el-form-item label="分类">
            <el-cascader
              v-model="queryParams.categoryId"
              :options="categoryOptions"
              :props="{ checkStrictly: true, value: 'id', label: 'categoryName', children: 'children' }"
              placeholder="全部"
              clearable
              class="filter-input"
            />
          </el-form-item>
          <el-form-item label="品牌">
            <el-select
              v-model="queryParams.brandId"
              placeholder="全部"
              clearable
              class="filter-input"
            >
              <el-option
                v-for="b in brands"
                :key="b.id"
                :label="b.brandName"
                :value="b.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="供应商">
            <el-select
              v-model="queryParams.supplierId"
              placeholder="全部"
              clearable
              class="filter-input"
            >
              <el-option
                v-for="s in suppliers"
                :key="s.id"
                :label="s.supplierName"
                :value="s.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="系列">
            <el-select
              v-model="queryParams.seriesTagId"
              placeholder="全部"
              clearable
              filterable
              class="filter-input"
            >
              <el-option
                v-for="tag in seriesTags"
                :key="tag.id"
                :label="tag.tagName"
                :value="tag.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="状态">
            <el-select
              v-model="queryParams.status"
              placeholder="全部"
              clearable
              class="filter-input"
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
          <el-form-item label="库存">
            <el-select
              v-model="queryParams.stockStatus"
              placeholder="全部"
              clearable
              class="filter-input"
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
              <el-option
                label="未知"
                value="unknown"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="价格区间">
            <div class="price-range">
              <el-input-number
                v-model="queryParams.minPrice"
                :min="0"
                :precision="2"
                placeholder="最低"
                controls-position="right"
                style="width: 90px"
              />
              <span class="price-sep">-</span>
              <el-input-number
                v-model="queryParams.maxPrice"
                :min="0"
                :precision="2"
                placeholder="最高"
                controls-position="right"
                style="width: 90px"
              />
            </div>
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
        <div class="toolbar-actions">
          <el-button
            v-if="canExport"
            type="success"
            @click="handleExport"
          >
            导出
          </el-button>
          <el-button
            v-if="canCreate"
            type="primary"
            @click="showCreateDialog = true"
          >
            新增产品
          </el-button>
        </div>
      </div>

      <el-table
        v-loading="loading"
        :data="products"
        border
        stripe
        class="product-table"
        :fit="false"
      >
        <el-table-column
          prop="productNo"
          label="产品编号"
          min-width="120"
        />
        <el-table-column
          prop="productName"
          label="产品名称"
          min-width="180"
          show-overflow-tooltip
        />
        <el-table-column
          prop="brandName"
          label="品牌"
          width="100"
        />
        <el-table-column
          prop="categoryName"
          label="分类"
          width="100"
        />
        <el-table-column
          prop="facePrice"
          label="面价"
          width="90"
          align="right"
        >
          <template #default="{ row }">
            <el-tag
              v-if="row.facePrice === 99999 && row.completenessStatus === 'pending'"
              size="small"
              type="warning"
            >
              待核价
            </el-tag>
            <span v-else>¥{{ row.facePrice.toFixed(2) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          v-if="canViewCost"
          prop="costPrice"
          label="成本价"
          width="90"
          align="right"
        >
          <template #default="{ row }">
            <span v-if="row.costPrice != null">¥{{ row.costPrice.toFixed(2) }}</span>
            <span
              v-else
              class="text-muted"
            >-</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="stockStatus"
          label="库存"
          width="80"
          align="center"
        >
          <template #default="{ row }">
            <el-tag
              :type="row.stockStatus === 'in_stock' ? 'success' : row.stockStatus === 'out_of_stock' ? 'danger' : row.stockStatus === 'unknown' ? 'info' : 'warning'"
              size="small"
            >
              {{ stockStatusMap[row.stockStatus] || row.stockStatus }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="status"
          label="状态"
          width="80"
          align="center"
        >
          <template #default="{ row }">
            <el-tag
              :type="row.status === 'active' ? 'success' : row.status === 'draft' ? 'info' : 'danger'"
              size="small"
            >
              {{ statusMap[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
          width="280"
          fixed="right"
          align="center"
        >
          <template #default="{ row }">
            <el-button
              size="small"
              @click="handleView(row)"
            >
              查看
            </el-button>
            <el-button
              v-if="canEdit"
              size="small"
              @click="handleEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              v-if="canChangeStatus"
              size="small"
              @click="showStatusDialog(row)"
            >
              状态
            </el-button>
            <el-button
              v-if="canClone"
              size="small"
              @click="handleClone(row)"
            >
              克隆
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

      <el-pagination
        v-model:current-page="queryParams.page"
        v-model:page-size="queryParams.size"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        style="margin-top: 20px; justify-content: flex-end;"
        @current-change="fetchProducts"
        @size-change="fetchProducts"
      />
    </el-card>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="showCreateDialog"
      :title="editingProduct ? '编辑产品' : '新增产品'"
      width="600px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-form
        ref="productFormRef"
        :model="productForm"
        :rules="productRules"
        label-width="90px"
      >
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item
              label="产品编号"
              prop="productNo"
            >
              <el-input
                v-model="productForm.productNo"
                :disabled="!!editingProduct"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item
              label="产品名称"
              prop="productName"
            >
              <el-input v-model="productForm.productName" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item
              label="品牌"
              prop="brandId"
            >
              <el-select
                v-model="productForm.brandId"
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
            <el-form-item
              label="供应商"
              prop="supplierId"
            >
              <el-select
                v-model="productForm.supplierId"
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
            <el-form-item
              label="分类"
              prop="categoryId"
            >
              <el-cascader
                v-model="productForm.categoryId"
                :options="categoryOptions"
                :props="{ checkStrictly: true, value: 'id', label: 'categoryName', children: 'children' }"
                style="width:100%"
                placeholder="请选择"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item
              label="面价"
              prop="facePrice"
            >
              <el-input-number
                v-model="productForm.facePrice"
                :min="0"
                :precision="2"
                style="width:100%"
              />
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
                v-model="productForm.costPrice"
                :min="0"
                :precision="2"
                style="width:100%"
                :placeholder="canViewCost ? '可选' : '无权限'"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="材质">
              <el-input v-model="productForm.material" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="库存状态">
              <el-select
                v-model="productForm.stockStatus"
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
                <el-option
                  label="未知"
                  value="unknown"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态">
              <el-select
                v-model="productForm.status"
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
          </el-col>
        </el-row>
        <el-form-item label="标签">
          <el-select
            v-model="productForm.tagIds"
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

    <!-- Status Change Dialog -->
    <el-dialog
      v-model="statusDialogVisible"
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
        <el-button @click="statusDialogVisible = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="statusSubmitting"
          @click="confirmStatusChange"
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
import { productApi, categoryApi, brandApi, supplierApi, tagApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'

const authStore = useAuthStore()
const userPermissions = computed(() => authStore.userPermissions)
const roleCode = computed(() => authStore.userRoleCode)

const canViewCost = computed(() => {
  const adminRoles = ['admin', 'super_admin', 'finance', 'product_manager']
  return !!roleCode.value && (adminRoles.includes(roleCode.value) || roleCode.value.startsWith('admin'))
})
const canCreate = computed(() => hasPermission(userPermissions.value, 'product:create'))
const canEdit = computed(() => hasPermission(userPermissions.value, 'product:edit'))
const canDelete = computed(() => hasPermission(userPermissions.value, 'product:delete'))
const canExport = computed(() => hasPermission(userPermissions.value, 'product:export'))
const canClone = computed(() => hasPermission(userPermissions.value, 'product:clone'))
const canChangeStatus = computed(() => hasPermission(userPermissions.value, 'product:status'))

const statusMap: Record<string, string> = { active: '上架', inactive: '下架', draft: '草稿' }
const stockStatusMap: Record<string, string> = { in_stock: '有货', out_of_stock: '缺货', preorder: '预售', unknown: '未知' }

const loading = ref(false)
const products = ref<any[]>([])
const total = ref(0)
const showCreateDialog = ref(false)
const editingProduct = ref<any>(null)
const submitting = ref(false)
const productFormRef = ref<FormInstance>()

const brands = ref<any[]>([])
const suppliers = ref<any[]>([])
const tags = ref<any[]>([])
const seriesTags = computed(() => tags.value.filter((tag) => tag.tagType === 'series'))
const categoryOptions = ref<any[]>([])

const queryParams = reactive({
  keyword: '',
  status: '',
  stockStatus: '',
  brandId: '' as string | undefined,
  supplierId: '' as string | undefined,
  seriesTagId: '' as string | undefined,
  categoryId: '' as string | string[] | undefined,
  minPrice: undefined as number | undefined,
  maxPrice: undefined as number | undefined,
  page: 1,
  size: 20,
})

const productForm = reactive({
  productNo: '',
  productName: '',
  brandId: '' as string | undefined,
  supplierId: '' as string | undefined,
  categoryId: '' as string | string[] | undefined,
  facePrice: 99999,
  costPrice: undefined as number | undefined,
  material: '',
  stockStatus: 'in_stock',
  status: 'draft',
  tagIds: [] as string[],
})

const productRules: FormRules = {
  productNo: [{ required: true, message: '请输入产品编号', trigger: 'blur' }],
  productName: [{ required: true, message: '请输入产品名称', trigger: 'blur' }],
  brandId: [{ required: true, message: '请选择品牌', trigger: 'change' }],
  supplierId: [{ required: true, message: '请选择供应商', trigger: 'change' }],
  categoryId: [{ required: true, message: '请选择分类', trigger: 'change' }],
  facePrice: [{ required: true, message: '请输入面价', trigger: 'blur' }],
}

const statusDialogVisible = ref(false)
const statusForm = reactive({ status: 'draft' })
const statusTargetId = ref('')
const statusSubmitting = ref(false)

const fetchProducts = async () => {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      page: queryParams.page,
      size: queryParams.size,
    }
    if (queryParams.keyword) params.keyword = queryParams.keyword
    if (queryParams.status) params.status = queryParams.status
    if (queryParams.stockStatus) params.stock_status = queryParams.stockStatus
    if (queryParams.brandId) params.brand_id = queryParams.brandId
    if (queryParams.supplierId) params.supplier_id = queryParams.supplierId
    if (queryParams.seriesTagId) params.tag_ids = queryParams.seriesTagId
    if (queryParams.categoryId) {
      const catId = Array.isArray(queryParams.categoryId) ? queryParams.categoryId[queryParams.categoryId.length - 1] : queryParams.categoryId
      params.category_id = catId
    }
    if (queryParams.minPrice !== undefined && queryParams.minPrice !== null) params.min_price = queryParams.minPrice
    if (queryParams.maxPrice !== undefined && queryParams.maxPrice !== null) params.max_price = queryParams.maxPrice

    const res = await productApi.list(params)
    products.value = (res.data.list || []).map(normalizeProduct)
    total.value = res.data.total
  } catch {
    ElMessage.error('加载产品列表失败')
  } finally {
    loading.value = false
  }
}

const normalizeProduct = (item: any) => ({
  ...item,
  productNo: item.product_no,
  productName: item.product_name,
  brandId: item.brand_id,
  brandName: item.brand_name,
  supplierId: item.supplier_id,
  supplierName: item.supplier_name,
  categoryId: item.category_id,
  categoryName: item.category_name,
  facePrice: item.face_price,
  costPrice: item.cost_price,
  stockStatus: item.stock_status,
  completenessStatus: item.completeness_status,
  dataSource: item.data_source,
  tagIds: item.tag_ids || [],
  createTime: item.create_time,
  updateTime: item.update_time,
})

const normalizeCategory = (item: any): any => ({
  ...item,
  categoryName: item.category_name,
  children: (item.children || []).map(normalizeCategory),
})

const fetchMasterData = async () => {
  try {
    const [catResult, brandResult, supplierResult, tagResult] = await Promise.allSettled([
      categoryApi.list(),
      brandApi.list(),
      supplierApi.list(),
      tagApi.list(),
    ])
    const catRes = catResult.status === 'fulfilled' ? catResult.value : { data: [] }
    const brandRes = brandResult.status === 'fulfilled' ? brandResult.value : { data: { list: [] } }
    const supplierRes = supplierResult.status === 'fulfilled' ? supplierResult.value : { data: { list: [] } }
    const tagRes = tagResult.status === 'fulfilled' ? tagResult.value : { data: { list: [] } }
    categoryOptions.value = (catRes.data || []).map(normalizeCategory)
    brands.value = (brandRes.data?.list || []).map((item: any) => ({
      ...item,
      brandName: item.brand_name,
    }))
    suppliers.value = (supplierRes.data?.list || []).map((item: any) => ({
      ...item,
      supplierName: item.supplier_name,
    }))
    tags.value = (tagRes.data?.list || []).map((item: any) => ({
      ...item,
      tagName: item.tag_name,
      tagType: item.tag_type,
    }))
  } catch {
    // silently fail - master data is optional for product list
  }
}

const handleSearch = () => {
  queryParams.page = 1
  fetchProducts()
}

const handleReset = () => {
  queryParams.keyword = ''
  queryParams.status = ''
  queryParams.stockStatus = ''
  queryParams.brandId = ''
  queryParams.supplierId = ''
  queryParams.seriesTagId = ''
  queryParams.categoryId = ''
  queryParams.minPrice = undefined
  queryParams.maxPrice = undefined
  queryParams.page = 1
  fetchProducts()
}

const resetProductForm = () => {
  productForm.productNo = ''
  productForm.productName = ''
  productForm.brandId = ''
  productForm.supplierId = ''
  productForm.categoryId = ''
  productForm.facePrice = 99999
  productForm.costPrice = undefined
  productForm.material = ''
  productForm.stockStatus = 'in_stock'
  productForm.status = 'draft'
  productForm.tagIds = []
}

const handleSubmit = async () => {
  if (!productFormRef.value) return
  await productFormRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      const payload: Record<string, unknown> = {
        product_no: productForm.productNo,
        product_name: productForm.productName,
        brand_id: productForm.brandId,
        supplier_id: productForm.supplierId,
        category_id: Array.isArray(productForm.categoryId) ? productForm.categoryId[productForm.categoryId.length - 1] : productForm.categoryId,
        face_price: productForm.facePrice,
        stock_status: productForm.stockStatus,
        status: productForm.status,
        tag_ids: productForm.tagIds,
      }
      if (productForm.costPrice !== undefined && productForm.costPrice !== null) payload.cost_price = productForm.costPrice
      if (productForm.material) payload.material = productForm.material

      if (editingProduct.value) {
        await productApi.update(editingProduct.value.id, payload)
        ElMessage.success('更新成功')
      } else {
        await productApi.create(payload)
        ElMessage.success('创建成功')
      }
      showCreateDialog.value = false
      resetProductForm()
      fetchProducts()
    } catch {
      // error handled by api interceptor
    } finally {
      submitting.value = false
    }
  })
}

const handleView = (row: any) => {
  window.open(`/products/${row.id}`, '_self')
}

const handleEdit = (row: any) => {
  editingProduct.value = row
  productForm.productNo = row.productNo
  productForm.productName = row.productName
  productForm.brandId = row.brandId
  productForm.supplierId = row.supplierId
  productForm.categoryId = row.categoryId
  productForm.facePrice = row.facePrice
  productForm.costPrice = row.costPrice ?? undefined
  productForm.material = row.material || ''
  productForm.stockStatus = row.stockStatus
  productForm.status = row.status
  productForm.tagIds = row.tagIds?.length
    ? [...row.tagIds]
    : (row.tags || [])
      .map((name: string) => tags.value.find((tag) => tag.tagName === name || tag.tag_name === name)?.id)
      .filter(Boolean)
  showCreateDialog.value = true
}

const handleDelete = async (row: any) => {
  try {
    await ElMessageBox.confirm(`确定删除产品 "${row.productName}"？`, '确认删除', { type: 'warning' })
    await productApi.delete(row.id)
    ElMessage.success('删除成功')
    fetchProducts()
  } catch (e: any) {
    if (e !== 'cancel') {
      // error handled by interceptor
    }
  }
}

const showStatusDialog = (row: any) => {
  statusTargetId.value = row.id
  statusForm.status = row.status
  statusDialogVisible.value = true
}

const confirmStatusChange = async () => {
  statusSubmitting.value = true
  try {
    await productApi.updateStatus(statusTargetId.value, statusForm.status)
    ElMessage.success('状态更新成功')
    statusDialogVisible.value = false
    fetchProducts()
  } catch {
    // error handled by interceptor
  } finally {
    statusSubmitting.value = false
  }
}

const handleClone = async (row: any) => {
  try {
    await ElMessageBox.confirm(`确定克隆产品 "${row.productName}"？`, '确认克隆', { type: 'info' })
    await productApi.clone(row.id)
    ElMessage.success('克隆成功')
    fetchProducts()
  } catch (e: any) {
    if (e !== 'cancel') {
      // error handled by interceptor
    }
  }
}

const handleExport = async () => {
  const params: Record<string, string> = {}
  if (queryParams.keyword) params.keyword = queryParams.keyword
  if (queryParams.status) params.status = queryParams.status
  if (queryParams.stockStatus) params.stock_status = queryParams.stockStatus
  if (queryParams.brandId) params.brand_id = queryParams.brandId
  if (queryParams.supplierId) params.supplier_id = queryParams.supplierId
  if (queryParams.seriesTagId) params.tag_ids = queryParams.seriesTagId
  if (queryParams.categoryId) {
    const catId = Array.isArray(queryParams.categoryId) ? queryParams.categoryId[queryParams.categoryId.length - 1] : queryParams.categoryId
    params.category_id = catId
  }
  if (queryParams.minPrice !== undefined && queryParams.minPrice !== null) params.min_price = String(queryParams.minPrice)
  if (queryParams.maxPrice !== undefined && queryParams.maxPrice !== null) params.max_price = String(queryParams.maxPrice)

  try {
    const blob = await productApi.export(params) as unknown as Blob
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'products_export.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    // error handled by api interceptor
  }
}

onMounted(() => {
  fetchMasterData()
  fetchProducts()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}

.toolbar-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.filter-form {
  width: 100%;
}

.filter-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.filter-input {
  width: 160px;
}

.price-range {
  display: flex;
  align-items: center;
  gap: 4px;
}

.price-sep {
  color: #909399;
  font-size: 14px;
}

.product-table {
  width: 100%;
}

.text-muted {
  color: #909399;
}

@media (min-width: 768px) {
  .toolbar {
    flex-direction: row;
    justify-content: space-between;
    align-items: flex-start;
  }
}
</style>
