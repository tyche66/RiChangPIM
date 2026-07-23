<template>
  <div class="product-detail-page">
    <el-card
      v-if="loading"
      v-loading="loading"
      class="glass-card skeleton-card"
      style="min-height: 200px;"
    />
    <el-card
      v-else-if="pageState !== 'success'"
      class="glass-card not-found"
    >
      <el-result
        :icon="errorResult.icon"
        :title="errorResult.title"
        :sub-title="errorResult.subtitle"
      >
        <template #extra>
          <el-button
            v-if="pageState === 'server-error' || pageState === 'network-error'"
            type="primary"
            class="capsule-btn capsule-btn-primary"
            @click="fetchProduct"
          >
            重试
          </el-button>
          <el-button
            :type="pageState === 'not-found' || pageState === 'forbidden' ? 'primary' : 'default'"
            class="capsule-btn"
            @click="$router.push('/products')"
          >
            返回产品列表
          </el-button>
        </template>
      </el-result>
    </el-card>
    <el-card
      v-else
      class="glass-card"
    >
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
              class="capsule-tag-lg"
            >
              {{ statusMap[product.status] || product.status }}
            </el-tag>
            <el-tag
              v-if="product.stockStatus"
              :type="product.stockStatus === 'in_stock' ? 'success' : product.stockStatus === 'out_of_stock' ? 'danger' : product.stockStatus === 'unknown' ? 'info' : 'warning'"
              size="large"
              class="capsule-tag-lg"
            >
              {{ stockStatusMap[product.stockStatus] || product.stockStatus }}
            </el-tag>
            <el-button
              v-if="canEdit"
              type="primary"
              class="capsule-btn capsule-btn-primary"
              @click="editMode = !editMode"
            >
              {{ editMode ? '取消编辑' : '编辑' }}
            </el-button>
            <el-button
              v-if="canChangeStatus"
              class="capsule-btn"
              @click="showStatusDialog = true"
            >
              改状态
            </el-button>
            <el-button
              v-if="canClone"
              class="capsule-btn"
              @click="handleClone"
            >
              克隆
            </el-button>
            <el-button
              v-if="canDelete"
              type="danger"
              class="capsule-btn"
              @click="handleDelete"
            >
              删除
            </el-button>
            <el-button
              class="capsule-btn"
              @click="$router.push('/products')"
            >
              返回
            </el-button>
          </div>
        </div>
      </template>

      <el-descriptions
        :column="2"
        border
        class="glass-descriptions"
      >
        <el-descriptions-item label="产品编号">
          <span class="mono-text">{{ product.productNo }}</span>
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
          <el-tag
            v-if="product.facePrice === 99999 && product.completenessStatus === 'pending'"
            size="small"
            type="warning"
            class="capsule-tag"
          >
            待核价
          </el-tag>
          <span
            v-else
            class="price-text"
          >¥{{ product.facePrice.toFixed(2) }}</span>
        </el-descriptions-item>
        <el-descriptions-item
          v-if="canViewCost"
          label="成本价"
        >
          <span
            v-if="product.costPrice != null"
            class="price-text"
          >¥{{ product.costPrice.toFixed(2) }}</span>
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
        <el-descriptions-item label="规格">
          {{ product.specification || '待补充' }}
        </el-descriptions-item>
        <el-descriptions-item label="颜色">
          {{ product.colors || '待补充' }}
        </el-descriptions-item>
        <el-descriptions-item label="数据完整性">
          <el-tag
            :type="product.completenessStatus === 'complete' ? 'success' : 'warning'"
            class="capsule-tag"
          >
            {{ product.completenessStatus === 'complete' ? '完整' : '待补充' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="来源">
          {{ product.dataSource || '-' }}
        </el-descriptions-item>
        <el-descriptions-item
          label="产品描述"
          :span="2"
        >
          {{ product.description || '待补充' }}
        </el-descriptions-item>
      </el-descriptions>

      <section class="manual-section glass-section">
        <h4 class="section-title">
          说明书状态
        </h4>
        <div class="table-wrapper">
          <el-table
            :data="manuals"
            size="small"
            empty-text="暂无说明书"
            class="mini-table"
          >
            <el-table-column
              prop="doc_type"
              label="类型"
            />
            <el-table-column
              prop="parse_status"
              label="解析状态"
            />
            <el-table-column
              prop="index_status"
              label="索引状态"
            />
            <el-table-column
              label="失败原因"
              min-width="180"
            >
              <template #default="scope">
                {{ scope.row.parse_error || scope.row.index_error || '-' }}
              </template>
            </el-table-column>
            <el-table-column
              label="操作"
              width="110"
              align="center"
            >
              <template #default="scope">
                <el-button
                  text
                  size="small"
                  type="danger"
                  @click="handleDeleteManual(scope.row)"
                >
                  删除说明书
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </section>

      <div
        v-if="product.tags && product.tags.length"
        class="tags-section glass-section"
      >
        <h4 class="section-title">
          标签
        </h4>
        <div class="tags-wrap">
          <el-tag
            v-for="tag in product.tags"
            :key="tag"
            type="info"
            class="capsule-tag"
          >
            {{ tag }}
          </el-tag>
        </div>
      </div>

      <ProductImageManager
        v-if="product"
        :product-id="route.params.id as string"
        :images="productImages"
        @change="onProductImagesChange"
      />
      <SceneImageSelector
        v-if="product"
        :product-id="route.params.id as string"
        :images="sceneImages"
        @change="onSceneImagesChange"
      />

      <!-- Edit Form -->
      <el-dialog
        v-if="editMode"
        v-model="editMode"
        title="编辑产品"
        class="glass-dialog"
        append-to-body
        lock-scroll
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
            <el-col :span="24">
              <el-form-item
                label="产品名称"
                prop="productName"
              >
                <el-input
                  v-model="editForm.productName"
                  class="capsule-input"
                />
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
                  class="capsule-number full-width"
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
                  class="capsule-select full-width"
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
                  class="capsule-select full-width"
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
                  class="capsule-select full-width"
                  placeholder="请选择"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="库存状态">
                <el-select
                  v-model="editForm.stockStatus"
                  class="capsule-select full-width"
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
                  class="capsule-number full-width"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="材质">
                <el-input
                  v-model="editForm.material"
                  class="capsule-input"
                />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="状态">
            <el-select
              v-model="editForm.status"
              class="capsule-select full-width"
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
              class="capsule-select full-width"
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
          <el-button
            class="capsule-btn"
            @click="editMode = false"
          >
            取消
          </el-button>
          <el-button
            type="primary"
            :loading="saving"
            class="capsule-btn capsule-btn-primary"
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
        class="glass-dialog dialog-sm"
        append-to-body
        lock-scroll
        :close-on-click-modal="false"
      >
        <el-form label-width="80px">
          <el-form-item label="状态">
            <el-select
              v-model="statusForm.status"
              class="capsule-select full-width"
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
          <el-button
            class="capsule-btn"
            @click="showStatusDialog = false"
          >
            取消
          </el-button>
          <el-button
            type="primary"
            :loading="statusSaving"
            class="capsule-btn capsule-btn-primary"
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
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { productApi, categoryApi, brandApi, supplierApi, tagApi, manualApi } from '@/api'
import type { ProductManual } from '@/types/manuals'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'
import ProductImageManager from '@/components/ProductImageManager.vue'
import type { ProductBindImage } from '@/components/ProductImageManager.vue'
import SceneImageSelector from '@/components/SceneImageSelector.vue'
import type { SceneImageItem } from '@/components/SceneImageSelector.vue'
import { classifyProductDetailError } from '@/utils/productDetailError'

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
const stockStatusMap: Record<string, string> = { in_stock: '有货', out_of_stock: '缺货', preorder: '预售', unknown: '未知' }

type PageState = 'loading' | 'not-found' | 'forbidden' | 'server-error' | 'network-error' | 'success'

const pageState = ref<PageState>('loading')
const loading = computed(() => pageState.value === 'loading')
const product = ref<any>(null)
const manuals = ref<ProductManual[]>([])
const errorResult = computed(() => {
  if (pageState.value === 'forbidden') {
    return { icon: 'warning', title: '无权限查看该产品', subtitle: '请联系管理员开通产品查看权限' }
  }
  if (pageState.value === 'server-error') {
    return { icon: 'error', title: '产品详情加载失败', subtitle: '服务器暂时不可用，请稍后重试' }
  }
  if (pageState.value === 'network-error') {
    return { icon: 'error', title: '无法连接服务器', subtitle: '请检查后端服务' }
  }
  return { icon: 'error', title: '产品不存在', subtitle: '该产品可能已被删除' }
})

const productImages = computed<ProductBindImage[]>(() => {
  if (!product.value?.productImages) return []
  return product.value.productImages.map((img: any, index: number) => ({
    imageId: img.imageId,
    attachmentId: img.attachmentId,
    url: img.url,
    thumbnailUrl: img.thumbnailUrl,
    name: img.name,
    sortOrder: img.sortOrder ?? index,
    isPrimary: img.isPrimary,
  }))
})

const sceneImages = computed<SceneImageItem[]>(() => {
  if (!product.value?.sceneImages) return []
  return product.value.sceneImages.map((img: any, index: number) => ({
    sceneImageId: img.sceneImageId || img.id,
    attachmentId: img.attachmentId,
    url: img.url,
    thumbnailUrl: img.thumbnailUrl,
    name: img.name,
    sortOrder: img.sortOrder ?? index,
  }))
})

function onProductImagesChange(images: ProductBindImage[]) {
  if (!product.value) return
  product.value.primaryImageId = images.find((img) => img.isPrimary)?.imageId || null
  const primaryImg = images.find((img) => img.isPrimary)
  product.value.primaryImage = primaryImg
    ? { id: primaryImg.imageId, url: primaryImg.url, thumbnailUrl: primaryImg.thumbnailUrl, name: primaryImg.name }
    : null
  product.value.productImages = images.map((img, i) => ({
    imageId: img.imageId,
    attachmentId: img.attachmentId,
    url: img.url,
    thumbnailUrl: img.thumbnailUrl,
    name: img.name,
    sortOrder: i,
    isPrimary: img.isPrimary,
  }))
}

function onSceneImagesChange(images: SceneImageItem[]) {
  if (!product.value) return
  product.value.sceneImages = images.map((img, i) => ({
    sceneImageId: img.sceneImageId,
    attachmentId: img.attachmentId,
    url: img.url,
    thumbnailUrl: img.thumbnailUrl,
    name: img.name,
    sortOrder: i,
  }))
}
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
  facePrice: 99999,
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
  pageState.value = 'loading'
  try {
    const res = await productApi.get(route.params.id as string)
    product.value = normalizeProduct(res.data || res)
    pageState.value = 'success'
  } catch (error) {
    const errorState = classifyProductDetailError(error)
    if (errorState !== 'unauthorized') pageState.value = errorState
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
  primaryImage: item.cover_image_url
    ? {
        id: item.cover_image_id,
        url: item.cover_image_url,
        thumbnailUrl: item.cover_image_url,
        name: item.cover_image_filename,
      }
    : null,
  primaryImageId: item.cover_image_id || null,
  productImages: (item.images || []).map((img: any) => ({
    imageId: img.id,
    attachmentId: img.attachment_id,
    url: img.file_url,
    thumbnailUrl: img.file_url,
    name: img.file_name,
    sortOrder: img.sort,
    isPrimary: img.is_cover,
  })),
  sceneImages: (item.scene_images || []).map((img: any) => ({
    id: img.id,
    sceneImageId: img.id,
    attachmentId: img.attachment_id,
    url: img.file_url,
    thumbnailUrl: img.file_url,
    name: img.name,
    sortOrder: img.sort,
  })),
})

const normalizeCategory = (item: any): any => ({
  ...item,
  categoryName: item.category_name,
  children: (item.children || []).map(normalizeCategory),
})

const fetchManuals = async () => {
  try {
    const res = await manualApi.list({ product_id: route.params.id, page: 1, size: 50 }) as any
    manuals.value = res.data?.list || []
  } catch {
    manuals.value = []
  }
}

const handleDeleteManual = async (manual: ProductManual) => {
  try {
    await ElMessageBox.confirm(`确定删除说明书吗？删除后将解除与当前产品的关联。`, '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await manualApi.delete(manual.id)
    ElMessage.success('说明书已删除')
    await fetchManuals()
  } catch (e: any) {
    console.error('[manual delete] failed', e?.response?.status, e?.response?.data)
    // user-facing message is rendered by the response interceptor
  }
}

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
  editForm.tagIds = product.value.tagIds?.length
    ? [...product.value.tagIds]
    : (product.value.tags || [])
      .map((name: string) => tags.value.find((tag) => tag.tagName === name || tag.tag_name === name)?.id)
      .filter(Boolean)
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
  fetchManuals()
  fetchMasterData()
})

watch(editMode, (val) => {
  if (val) populateEditForm()
  else {
    statusForm.status = product.value?.status || 'draft'
  }
})
</script>

<style scoped>
/* ===== CSS Variables ===== */
.product-detail-page {
  --brand-deep: rgba(30, 50, 90, 0.92);
  --brand-primary: rgba(30, 50, 90, 0.85);
  --brand-light: rgba(30, 50, 90, 0.08);
  --brand-lighter: rgba(30, 50, 90, 0.04);
  --text-primary: #5E6470;
  --text-secondary: rgba(30, 50, 90, 0.6);
  --bg-mist: #f0f0f0;
  --glass-bg: rgba(255, 255, 255, 0.72);
  --glass-border: rgba(255, 255, 255, 0.5);
  --radius-lg: 28px;
  --radius-md: 18px;
  --radius-sm: 12px;
  --shadow-soft: 0 4px 24px rgba(30, 50, 90, 0.06);
  --transition-fast: 200ms cubic-bezier(0.4, 0, 0.2, 1);
  padding: 16px;
  min-height: 100vh;
  background: var(--bg-mist);
}

/* ===== Glass Card ===== */
.glass-card {
  background: var(--glass-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-soft);
  overflow: hidden;
}

.glass-card :deep(.el-card__header) {
  background: transparent;
  border-bottom: 1px solid rgba(30, 50, 90, 0.06);
  padding: 20px 24px;
}

.glass-card :deep(.el-card__body) {
  padding: 24px;
}

.skeleton-card {
  min-height: 200px;
}

/* ===== Detail Header ===== */
.detail-header {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}

.product-no {
  font-size: 14px;
  color: var(--text-secondary);
  font-family: monospace;
}

.product-name {
  font-size: 22px;
  font-weight: 700;
  color: var(--brand-deep);
}

.detail-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

/* ===== Capsule Buttons ===== */
.capsule-btn {
  border-radius: 20px !important;
  padding: 8px 20px;
  font-weight: 500;
  transition: var(--transition-fast);
}

.capsule-btn:hover {
  transform: scale(1.03);
}

.capsule-btn:active {
  transform: scale(0.97);
}

.capsule-btn-primary {
  background: var(--brand-primary);
  border-color: var(--brand-primary);
}

.capsule-btn-primary:hover {
  background: var(--brand-deep);
  border-color: var(--brand-deep);
}

/* ===== Capsule Tags ===== */
.capsule-tag {
  border-radius: 12px;
  padding: 2px 10px;
  font-weight: 500;
}

.capsule-tag-lg {
  border-radius: 16px;
  padding: 4px 14px;
  font-weight: 500;
  font-size: 13px;
}

/* ===== Descriptions ===== */
.glass-descriptions {
  margin-top: 20px;
  border-radius: var(--radius-md);
  overflow: hidden;
}

.glass-descriptions :deep(.el-descriptions__header) {
  margin-bottom: 0;
}

.glass-descriptions :deep(.el-descriptions__body) {
  background: transparent;
}

.glass-descriptions :deep(.el-descriptions__label) {
  background: var(--brand-lighter);
  color: var(--text-primary);
  font-weight: 600;
}

.glass-descriptions :deep(.el-descriptions__content) {
  color: var(--text-primary);
}

.mono-text {
  font-family: monospace;
  color: var(--text-secondary);
}

.price-text {
  color: var(--brand-deep);
  font-weight: 600;
  font-family: monospace;
}

/* ===== Sections ===== */
.glass-section {
  margin-top: 24px;
  padding: 20px;
  background: var(--brand-lighter);
  border-radius: var(--radius-md);
}

.section-title {
  margin: 0 0 16px 0;
  color: var(--brand-deep);
  font-size: 15px;
  font-weight: 600;
}

/* ===== Table ===== */
.table-wrapper {
  overflow-x: auto;
  border-radius: var(--radius-sm);
}

.mini-table {
  width: 100%;
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.mini-table :deep(.el-table__header-wrapper) {
  background: var(--brand-light);
}

.mini-table :deep(.el-table__header th) {
  background: var(--brand-light);
  color: var(--text-primary);
  font-weight: 600;
  font-size: 12px;
}

.mini-table :deep(.el-table__row:hover td) {
  background: var(--brand-lighter);
}

/* ===== Tags ===== */
.tags-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* ===== Glass Dialog ===== */
.glass-dialog :deep(.el-dialog) {
  border-radius: var(--radius-lg) !important;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(30, 50, 90, 0.15);
}

.glass-dialog :deep(.el-dialog__header) {
  background: linear-gradient(135deg, rgba(30, 50, 90, 0.06), rgba(30, 50, 90, 0.02));
  padding: 20px 24px 16px;
  margin-right: 0;
  border-bottom: 1px solid rgba(30, 50, 90, 0.06);
}

.glass-dialog :deep(.el-dialog__title) {
  color: var(--text-primary);
  font-weight: 700;
  font-size: 18px;
}

.glass-dialog :deep(.el-dialog__body) {
  padding: 24px;
  max-height: 70vh;
  overflow-y: auto;
}

.glass-dialog :deep(.el-dialog__footer) {
  padding: 16px 24px;
}

.dialog-sm :deep(.el-dialog) {
  width: 400px !important;
  max-width: 90vw;
}

.full-width {
  width: 100%;
}

/* ===== Capsule Inputs ===== */
.capsule-input :deep(.el-input__wrapper),
.capsule-select :deep(.el-select__wrapper),
.capsule-select :deep(.el-input__wrapper) {
  border-radius: 20px;
  box-shadow: 0 0 0 1px rgba(30, 50, 90, 0.1) inset;
  padding: 4px 16px;
  transition: var(--transition-fast);
}

.capsule-input :deep(.el-input__wrapper):hover,
.capsule-select :deep(.el-select__wrapper):hover,
.capsule-select :deep(.el-input__wrapper):hover {
  box-shadow: 0 0 0 1px rgba(30, 50, 90, 0.25) inset;
}

.capsule-number :deep(.el-input__wrapper) {
  border-radius: 20px;
}

.capsule-number :deep(.el-input-number__decrease),
.capsule-number :deep(.el-input-number__increase) {
  border-radius: 0;
}

/* ===== Not Found ===== */
.not-found {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
}

.text-muted {
  color: var(--text-secondary);
}

/* ===== Responsive ===== */
@media (max-width: 768px) {
  .product-detail-page {
    padding: 8px;
  }

  .glass-card {
    border-radius: var(--radius-md);
  }

  .glass-card :deep(.el-card__header),
  .glass-card :deep(.el-card__body) {
    padding: 16px;
  }

  .detail-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .detail-title {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }

  .product-name {
    font-size: 18px;
  }

  .detail-actions {
    width: 100%;
  }

  .detail-actions .capsule-btn,
  .detail-actions :deep(.el-button) {
    flex: 1;
    min-width: 0;
    text-align: center;
  }

  .glass-section {
    padding: 16px;
  }

  .glass-descriptions :deep(.el-descriptions__label),
  .glass-descriptions :deep(.el-descriptions__content) {
    font-size: 12px;
  }

  .glass-dialog :deep(.el-dialog) {
    width: 95vw !important;
    max-width: 95vw;
    margin: 8px auto;
  }

  .glass-dialog :deep(.el-dialog__body) {
    padding: 16px;
  }

  .dialog-sm :deep(.el-dialog) {
    width: 90vw !important;
  }
}

@media (min-width: 769px) {
  .detail-header {
    flex-direction: row;
    justify-content: space-between;
    align-items: center;
  }
}
</style>
