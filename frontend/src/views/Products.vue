<template>
  <div class="products-page">
    <el-card class="glass-card">
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
              class="filter-input capsule-input"
            />
          </el-form-item>
          <el-form-item label="分类">
            <el-cascader
              v-model="queryParams.categoryId"
              :options="categoryOptions"
              :props="{ checkStrictly: true, value: 'id', label: 'categoryName', children: 'children' }"
              placeholder="全部"
              clearable
              class="filter-input capsule-select"
            />
          </el-form-item>
          <el-form-item label="品牌">
            <el-select
              v-model="queryParams.brandId"
              placeholder="全部"
              clearable
              class="filter-input capsule-select"
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
              class="filter-input capsule-select"
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
              class="filter-input capsule-select"
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
              class="filter-input capsule-select"
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
              class="filter-input capsule-select"
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
                class="capsule-number"
              />
              <span class="price-sep">-</span>
              <el-input-number
                v-model="queryParams.maxPrice"
                :min="0"
                :precision="2"
                placeholder="最高"
                controls-position="right"
                class="capsule-number"
              />
            </div>
          </el-form-item>
          <el-form-item>
            <el-button
              type="primary"
              class="capsule-btn"
              @click="handleSearch"
            >
              查询
            </el-button>
            <el-button
              class="capsule-btn"
              @click="handleReset"
            >
              重置
            </el-button>
          </el-form-item>
        </el-form>
        <div class="toolbar-actions">
          <el-button
            class="capsule-btn"
            @click="toggleAutoFit"
          >
            <el-icon>
              <Operation v-if="autoFit" />
              <Grid v-else />
            </el-icon>
            <span>{{ autoFit ? '紧凑' : '自适应' }}</span>
          </el-button>
          <el-button
            v-if="canExport"
            type="success"
            class="capsule-btn"
            @click="handleExport"
          >
            导出
          </el-button>
          <el-button
            v-if="canCreate"
            type="primary"
            class="capsule-btn capsule-btn-primary"
            @click="showCreateDialog = true"
          >
            新增产品
          </el-button>
          <el-button
            v-if="canProposalCreate"
            type="success"
            class="capsule-btn"
            @click="enterProposalMode"
          >
            制作方案
          </el-button>
        </div>
      </div>

      <div
        v-if="proposalMode"
        class="selection-bar"
      >
        <span class="selection-count">已选 {{ selectedCount }} 项</span>
        <div class="selection-actions">
          <el-button
            class="capsule-btn"
            @click="exitProposalMode"
          >
            取消
          </el-button>
          <el-button
            type="primary"
            class="capsule-btn capsule-btn-primary"
            :disabled="selectedCount === 0"
            @click="finishProposal"
          >
            完成
          </el-button>
        </div>
      </div>

      <div
        v-if="proposalMode"
        class="proposal-mobile-list"
      >
        <button
          v-for="row in products"
          :key="row.id"
          type="button"
          class="proposal-mobile-item"
          :class="{ selected: selectedIds.has(row.id) }"
          :disabled="!isSelectable(row)"
          @click="toggleMobileSelection(row)"
        >
          <span class="proposal-mobile-check">{{ selectedIds.has(row.id) ? '已选' : '选择' }}</span>
          <span class="proposal-mobile-product">
            <strong>{{ row.productName }}</strong>
            <small>{{ row.productNo }} · ¥{{ row.facePrice.toFixed(2) }}</small>
          </span>
          <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'">
            {{ statusMap[row.status] || row.status }}
          </el-tag>
        </button>
      </div>

      <div class="table-wrapper">
        <el-table
          ref="productTableRef"
          v-loading="loading"
          :data="products"
          border
          stripe
          class="product-table"
          :fit="false"
          :row-key="(row: any) => row.id"
          :reserve-selection="true"
          @header-dragend="onHeaderDragEnd"
          @selection-change="onSelectionChange"
        >
          <el-table-column
            v-if="proposalMode"
            type="selection"
            width="50"
            fixed="left"
            :selectable="isSelectable"
          />
          <el-table-column
            label="图片"
            width="80"
            align="center"
          >
            <template #default="{ row }">
              <div
                class="product-thumb"
                @click="previewProductImage(row)"
              >
                <el-image
                  v-if="row.primaryImage?.thumbnailUrl || row.primaryImage?.url"
                  :src="row.primaryImage.thumbnailUrl || row.primaryImage.url"
                  fit="cover"
                  class="thumb-img"
                >
                  <template #error>
                    <div class="thumb-placeholder">
                      {{ getPlaceholderText(row.productName) }}
                    </div>
                  </template>
                </el-image>
                <div
                  v-else
                  class="thumb-placeholder"
                >
                  {{ getPlaceholderText(row.productName) }}
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column
            prop="productNo"
            label="产品编号"
            :width="autoFit ? colWidths['productNo'] : 120"
            :show-overflow-tooltip="{ teleported: true, placement: 'top' }"
          />
          <el-table-column
            prop="productName"
            label="产品名称"
            :width="autoFit ? colWidths['productName'] : 180"
            :show-overflow-tooltip="{ teleported: true, placement: 'top' }"
          />
          <el-table-column
            prop="brandName"
            label="品牌"
            :width="autoFit ? colWidths['brandName'] : 100"
            :show-overflow-tooltip="{ teleported: true, placement: 'top' }"
          />
          <el-table-column
            prop="categoryName"
            label="分类"
            :width="autoFit ? colWidths['categoryName'] : 100"
            :show-overflow-tooltip="{ teleported: true, placement: 'top' }"
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
                class="capsule-tag"
              >
                待核价
              </el-tag>
              <span
                v-else
                class="price-text"
              >¥{{ row.facePrice.toFixed(2) }}</span>
            </template>
          </el-table-column>
          <el-table-column
            v-if="canViewCost"
            prop="costPrice"
            label="成本价"
            width="90"
            align="right"
          >
            <template #header>
              <span class="cost-header">
                成本价
                <el-button
                  link
                  size="small"
                  class="cost-eye"
                  :title="costVisible ? '隐藏成本价' : '显示成本价'"
                  @click.stop="costVisible = !costVisible"
                >
                  <el-icon>
                    <View v-if="costVisible" />
                    <Hide v-else />
                  </el-icon>
                </el-button>
              </span>
            </template>
            <template #default="{ row }">
              <span
                v-if="costVisible && row.costPrice != null"
                class="price-text"
              >¥{{ row.costPrice.toFixed(2) }}</span>
              <span
                v-else
                class="text-muted"
              >—</span>
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
                class="capsule-tag"
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
                class="capsule-tag"
              >
                {{ statusMap[row.status] || row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            label="操作"
            class="op-col"
            :width="autoFit ? colWidths['operation'] : 280"
            fixed="right"
            align="center"
          >
            <template #default="{ row }">
              <el-button
                size="small"
                class="capsule-btn btn-sm"
                @click="handleView(row)"
              >
                查看
              </el-button>
              <el-button
                v-if="canEdit"
                size="small"
                class="capsule-btn btn-sm"
                @click="handleEdit(row)"
              >
                编辑
              </el-button>
              <el-button
                v-if="canChangeStatus"
                size="small"
                class="capsule-btn btn-sm"
                @click="showStatusDialog(row)"
              >
                状态
              </el-button>
              <el-button
                v-if="canClone"
                size="small"
                class="capsule-btn btn-sm"
                @click="handleClone(row)"
              >
                克隆
              </el-button>
              <el-button
                v-if="canDelete"
                size="small"
                type="danger"
                class="capsule-btn btn-sm"
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
        class="pagination-wrap"
        @current-change="fetchProducts"
        @size-change="fetchProducts"
      />
    </el-card>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="showCreateDialog"
      :title="editingProduct ? '编辑产品' : '新增产品'"
      class="glass-dialog"
      append-to-body
      lock-scroll
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
          <el-col :span="24">
            <el-form-item
              label="产品编号"
              prop="productNo"
            >
              <el-input
                v-model="productForm.productNo"
                :disabled="!!editingProduct"
                class="capsule-input"
              />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item
              label="产品名称"
              prop="productName"
            >
              <el-input
                v-model="productForm.productName"
                class="capsule-input"
              />
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
            <el-form-item
              label="供应商"
              prop="supplierId"
            >
              <el-select
                v-model="productForm.supplierId"
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
            <el-form-item
              label="分类"
              prop="categoryId"
            >
              <el-cascader
                v-model="productForm.categoryId"
                :options="categoryOptions"
                :props="{ checkStrictly: true, value: 'id', label: 'categoryName', children: 'children' }"
                class="capsule-select full-width"
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
                class="capsule-number full-width"
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
                class="capsule-number full-width"
                :placeholder="canViewCost ? '可选' : '无权限'"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="材质">
              <el-input
                v-model="productForm.material"
                class="capsule-input"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="库存状态">
              <el-select
                v-model="productForm.stockStatus"
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
          <el-col :span="12">
            <el-form-item label="状态">
              <el-select
                v-model="productForm.status"
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
          </el-col>
        </el-row>
        <el-form-item label="标签">
          <el-select
            v-model="productForm.tagIds"
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
          @click="showCreateDialog = false"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="submitting"
          class="capsule-btn capsule-btn-primary"
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
          @click="statusDialogVisible = false"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="statusSubmitting"
          class="capsule-btn capsule-btn-primary"
          @click="confirmStatusChange"
        >
          确定
        </el-button>
      </template>
    </el-dialog>

    <el-image-viewer
      v-if="previewUrl"
      :url-list="[previewUrl]"
      @close="previewUrl = ''"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { View, Hide, Operation, Grid } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { productApi, categoryApi, brandApi, supplierApi, tagApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'
import type { ProductOption, ProposalToken } from '@/types/sales'

const authStore = useAuthStore()
const router = useRouter()
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
const canProposalCreate = computed(() => hasPermission(userPermissions.value, 'proposal:create'))

const statusMap: Record<string, string> = { active: '上架', inactive: '下架', draft: '草稿' }
const stockStatusMap: Record<string, string> = { in_stock: '有货', out_of_stock: '缺货', preorder: '预售', unknown: '未知' }

const loading = ref(false)
const products = ref<any[]>([])
const total = ref(0)
const showCreateDialog = ref(false)
const editingProduct = ref<any>(null)
const submitting = ref(false)
const productFormRef = ref<FormInstance>()

const autoFit = ref(true)
const costVisible = ref(false)
const colWidths = ref<Record<string, number>>({})
const productTableRef = ref()
const previewUrl = ref('')

// ===== Proposal mode state =====
const proposalMode = ref(false)
const selectedIds = ref(new Set<string>())
const allSelectedProducts = ref<ProductOption[]>([])

const selectedCount = computed(() => selectedIds.value.size)

function getPlaceholderText(name: string): string {
  if (!name) return '无图'
  const chineseChars = name.match(/[\u4e00-\u9fa5]/g)
  if (chineseChars && chineseChars.length >= 2) {
    return chineseChars.slice(0, 2).join('')
  }
  const alnum = name.replace(/[^a-zA-Z0-9]/g, '')
  if (alnum.length >= 4) return alnum.slice(0, 4).toUpperCase()
  if (alnum.length > 0) return alnum.toUpperCase()
  return name.slice(0, 2)
}

function previewProductImage(row: any) {
  if (row.primaryImage?.url) {
    previewUrl.value = row.primaryImage.url
  }
}

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
    if (autoFit.value) computeFillWidths()
  } catch {
    ElMessage.error('加载产品列表失败')
  } finally {
    loading.value = false
  }
}

// 文本列：按内容自适应（设最小/最大阈值）
const FIT_TEXT = [
  { prop: 'productNo', label: '产品编号', min: 110, max: 240 },
  { prop: 'brandName', label: '品牌', min: 90, max: 200 },
  { prop: 'categoryName', label: '分类', min: 90, max: 200 },
]
// 固定列宽（不参与内容测量）
const FIXED_WIDTHS: Record<string, number> = {
  image: 80,
  facePrice: 90,
  stockStatus: 90,
  status: 90,
  costPrice: 90,
  operation: 360,
}
const NAME_MIN = 140
const NAME_MAX = 520

const _measureCanvas = document.createElement('canvas')
const _measureCtx = _measureCanvas.getContext('2d')!

function measureTextWidth(text: string): number {
  _measureCtx.font = '14px "Helvetica Neue", Helvetica, Arial, "PingFang SC", "Microsoft YaHei", sans-serif'
  return _measureCtx.measureText(text == null ? '' : String(text)).width
}

function getTableWidth(): number {
  const el = productTableRef.value?.$el as HTMLElement | undefined
  return el ? el.clientWidth : 0
}

// 确定性填充：所有列宽之和 == 表格容器宽度，productName 作为弹性填充列。
// 这样不会留下右侧空白，操作列始终吸附右边缘（即便手动拖拽其它列）。
function computeFillWidths() {
  if (!autoFit.value) return
  const container = getTableWidth()
  if (!container) return
  const result: Record<string, number> = {}
  for (const c of FIT_TEXT) {
    let w = measureTextWidth(c.label) + 28
    for (const row of products.value) {
      const txt = row[c.prop] == null ? '' : String(row[c.prop])
      w = Math.max(w, measureTextWidth(txt) + 24)
    }
    result[c.prop] = Math.round(Math.min(Math.max(w, c.min), c.max))
  }
  for (const [k, v] of Object.entries(FIXED_WIDTHS)) {
    if (k === 'costPrice' && !canViewCost.value) continue
    if (k === 'operation') continue
    result[k] = v
  }
  const others = Object.values(result).reduce((a, b) => a + b, 0)
  let nameW = container - others - FIXED_WIDTHS.operation
  nameW = Math.min(Math.max(nameW, NAME_MIN), NAME_MAX)
  result.productName = Math.round(nameW)
  result.operation = FIXED_WIDTHS.operation
  colWidths.value = result
  nextTick(() => productTableRef.value?.doLayout())
}

// 手动拖拽列宽后，重新计算填充列使总宽仍等于容器宽度（消除右侧空白）
function onHeaderDragEnd(newWidth: number, _oldWidth: number, column: any) {
  if (!autoFit.value) return
  const prop = column?.property
  if (!prop || prop === 'productName') {
    computeFillWidths()
    return
  }
  colWidths.value = { ...colWidths.value, [prop]: Math.round(newWidth) }
  const container = getTableWidth()
  const others = Object.entries(colWidths.value)
    .filter(([k]) => k !== 'productName')
    .reduce((a, [, v]) => a + (v as number), 0)
  let nameW = container - others
  nameW = Math.min(Math.max(nameW, NAME_MIN), NAME_MAX)
  colWidths.value = { ...colWidths.value, productName: Math.round(nameW) }
  nextTick(() => productTableRef.value?.doLayout())
}

function toggleAutoFit() {
  autoFit.value = !autoFit.value
  if (autoFit.value) computeFillWidths()
  nextTick(() => productTableRef.value?.doLayout())
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

// ===== Proposal mode =====

function isSelectable(row: { id: string; status: string }): boolean {
  return row.status === 'active'
}

const enterProposalMode = () => {
  proposalMode.value = true
  selectedIds.value = new Set()
  allSelectedProducts.value = []
}

const exitProposalMode = () => {
  productTableRef.value?.clearSelection()
  proposalMode.value = false
  selectedIds.value = new Set()
  allSelectedProducts.value = []
}

const buildProductOption = (row: any): ProductOption => ({
  id: row.id,
  product_name: row.productName,
  product_no: row.productNo,
  face_price: row.facePrice ?? null,
  stock_status: row.stockStatus ?? null,
  cover_image_url: row.primaryImage?.url ?? null,
})

const onSelectionChange = (rows: any[]) => {
  selectedIds.value = new Set(rows.map((r) => r.id))
  allSelectedProducts.value = rows.map(buildProductOption)
}

const toggleMobileSelection = (row: any) => {
  if (!isSelectable(row)) return
  const next = new Set(selectedIds.value)
  const nextProducts = [...allSelectedProducts.value]
  if (next.has(row.id)) {
    next.delete(row.id)
    const index = nextProducts.findIndex((product) => product.id === row.id)
    if (index >= 0) nextProducts.splice(index, 1)
  } else {
    next.add(row.id)
    nextProducts.push(buildProductOption(row))
  }
  selectedIds.value = next
  allSelectedProducts.value = nextProducts
}

const finishProposal = () => {
  if (selectedIds.value.size === 0) return
  const token: ProposalToken = {
    productIds: [...selectedIds.value],
    options: allSelectedProducts.value,
  }
  const tokenId = crypto.randomUUID()
  sessionStorage.setItem(`proposal_token_${tokenId}`, JSON.stringify(token))
  exitProposalMode()
  router.push({
    path: '/proposals',
    query: { mode: 'create', selection_token: tokenId },
  })
}

onMounted(() => {
  fetchMasterData()
  fetchProducts()
  nextTick(() => computeFillWidths())
  let resizeTimer: number | undefined
  window.addEventListener('resize', () => {
    if (!autoFit.value) return
    clearTimeout(resizeTimer)
    resizeTimer = setTimeout(() => computeFillWidths(), 150) as unknown as number
  })
})
</script>

<style scoped>
/* ===== CSS Variables ===== */
.products-page {
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
  --shadow-hover: 0 8px 32px rgba(30, 50, 90, 0.1);
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
  padding: 20px 24px;
}

/* ===== Toolbar ===== */
.toolbar {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 16px;
}

.filter-form {
  width: 100%;
}

.filter-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.filter-form :deep(.el-form-item__label) {
  color: var(--text-primary);
  font-weight: 500;
  font-size: 13px;
}

.toolbar-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

/* ===== Capsule Inputs & Selects ===== */
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

.capsule-input :deep(.el-input__wrapper.is-focus),
.capsule-select :deep(.el-select__wrapper.is-focus),
.capsule-select :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 2px rgba(30, 50, 90, 0.3) inset;
}

.filter-input {
  width: 160px;
}

.capsule-number {
  width: 110px;
}

.capsule-number :deep(.el-input-number__decrease),
.capsule-number :deep(.el-input-number__increase) {
  border-radius: 0;
}

.capsule-number :deep(.el-input__wrapper) {
  border-radius: 20px;
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

.btn-sm {
  padding: 5px 14px;
  font-size: 12px;
  border-radius: 16px !important;
}

/* ===== Price Range ===== */
.price-range {
  display: flex;
  align-items: center;
  gap: 6px;
}

.price-sep {
  color: var(--text-secondary);
  font-size: 14px;
}

/* ===== Table ===== */
.table-wrapper {
  overflow-x: auto;
  border-radius: var(--radius-md);
}

.product-table {
  width: 100%;
  border-radius: var(--radius-md);
  overflow: hidden;
}

.cost-header {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.cost-eye {
  margin: 0;
  padding: 2px;
  height: auto;
  color: var(--text-secondary);
}

.cost-eye:hover {
  color: var(--brand-primary);
}

.product-table :deep(.op-col .cell) {
  display: flex;
  flex-wrap: nowrap;
  justify-content: center;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.product-table :deep(.el-table__header-wrapper) {
  background: var(--brand-lighter);
}

.product-table :deep(.el-table__header th) {
  background: var(--brand-lighter);
  color: var(--text-primary);
  font-weight: 600;
  font-size: 13px;
  padding: 14px 0;
}

.product-table :deep(.el-table__row td) {
  padding: 12px 0;
}

.product-table :deep(.el-table__row:hover td) {
  background: var(--brand-lighter);
}

.product-table :deep(.el-table--border)::after,
.product-table :deep(.el-table--border)::before {
  background: rgba(30, 50, 90, 0.06);
}

.price-text {
  color: var(--brand-deep);
  font-weight: 600;
  font-family: monospace;
}

/* ===== Product Thumb ===== */
.product-thumb {
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.thumb-img {
  width: 64px;
  height: 64px;
  border-radius: 8px;
  display: block;
}

.thumb-img :deep(img) {
  border-radius: 8px;
  background: #fff;
}

.thumb-placeholder {
  width: 64px;
  height: 64px;
  border-radius: 8px;
  background: var(--brand-lighter);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 1px;
  user-select: none;
}

.capsule-tag {
  border-radius: 12px;
  padding: 2px 10px;
  font-weight: 500;
}

/* ===== Pagination ===== */
.pagination-wrap {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.pagination-wrap :deep(.el-pagination) {
  padding: 8px 0;
}

.pagination-wrap :deep(.el-pager li),
.pagination-wrap :deep(.el-pagination .btn-prev),
.pagination-wrap :deep(.el-pagination .btn-next) {
  border-radius: 50%;
  min-width: 32px;
  height: 32px;
  line-height: 32px;
  transition: var(--transition-fast);
}

.pagination-wrap :deep(.el-pager li.active),
.pagination-wrap :deep(.el-pager li.active:hover) {
  background: var(--brand-primary);
  color: #fff;
}

.pagination-wrap :deep(.el-pager li:hover:not(.active)),
.pagination-wrap :deep(.el-pagination .btn-prev:hover),
.pagination-wrap :deep(.el-pagination .btn-next:hover) {
  background: var(--brand-light);
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
}

.glass-dialog :deep(.el-dialog__footer) {
  padding: 16px 24px;
}

.dialog-sm :deep(.el-dialog) {
  width: 380px !important;
  max-width: 90vw;
}

.full-width {
  width: 100%;
}

/* ===== Text ===== */
.text-muted {
  color: var(--text-secondary);
}

/* ===== Selection Bar ===== */
.selection-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: rgba(30, 50, 90, 0.06);
  border-radius: var(--radius-md);
  margin-bottom: 16px;
}

.selection-count {
  font-size: 14px;
  font-weight: 600;
  color: var(--brand-deep);
}

.selection-actions {
  display: flex;
  gap: 8px;
}

.proposal-mobile-list {
  display: none;
}

@media (max-width: 768px) {
  .proposal-mobile-list {
    display: grid;
    gap: 10px;
    margin: 12px 0;
  }

  .proposal-mobile-item {
    width: 100%;
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 10px;
    padding: 12px;
    border: 1px solid rgba(30, 50, 90, 0.12);
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.86);
    color: var(--text-primary);
    text-align: left;
  }

  .proposal-mobile-item.selected {
    border-color: var(--brand-primary);
    background: var(--brand-light);
  }

  .proposal-mobile-item:disabled {
    opacity: 0.55;
  }

  .proposal-mobile-check {
    color: var(--brand-primary);
    font-weight: 700;
  }

  .proposal-mobile-product {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .proposal-mobile-product small {
    margin-top: 4px;
    color: var(--text-secondary);
  }

  .selection-bar {
    flex-direction: column;
    gap: 8px;
    align-items: stretch;
  }

  .selection-actions {
    justify-content: space-between;
  }

  .selection-actions .capsule-btn {
    flex: 1;
  }
}
@media (max-width: 768px) {
  .products-page {
    padding: 8px;
  }

  .glass-card {
    border-radius: var(--radius-md);
  }

  .glass-card :deep(.el-card__header),
  .glass-card :deep(.el-card__body) {
    padding: 16px;
  }

  .toolbar {
    gap: 12px;
  }

  .filter-input {
    width: 100%;
  }

  .filter-form :deep(.el-form-item) {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    width: 100%;
  }

  .filter-form :deep(.el-form-item__content) {
    width: 100% !important;
    margin-left: 0 !important;
  }

  .toolbar-actions {
    flex-direction: column;
    width: 100%;
  }

  .toolbar-actions .capsule-btn {
    width: 100%;
  }

  .capsule-number {
    width: 100%;
  }

  .price-range {
    width: 100%;
  }

  .price-range :deep(.el-input-number) {
    flex: 1;
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

  .product-table :deep(.el-table__header-wrapper),
  .product-table :deep(.el-table__row td) {
    font-size: 12px;
  }

  .pagination-wrap {
    justify-content: center;
  }
}

@media (min-width: 769px) {
  .toolbar {
    flex-direction: row;
    justify-content: space-between;
    align-items: flex-start;
  }

  .toolbar-actions {
    flex-shrink: 0;
  }
}
</style>
