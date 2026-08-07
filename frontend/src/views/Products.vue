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
          <el-radio-group
            v-model="viewMode"
            size="small"
            class="view-mode-toggle"
          >
            <el-radio-button value="table">
              <el-icon><List /></el-icon>
            </el-radio-button>
            <el-radio-button value="grid">
              <el-icon><Grid /></el-icon>
            </el-radio-button>
          </el-radio-group>
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
          <span
            class="status-text"
            :class="`tone-${statusTone(row.status)}`"
          >{{ statusMap[row.status] || row.status }}</span>
        </button>
      </div>

      <div
        v-if="viewMode === 'table'"
        class="table-wrapper"
      >
        <el-table
          ref="productTableRef"
          v-loading="loading"
          :data="products"
          stripe
          class="product-table"
          :fit="!autoFit"
          :row-key="(row: any) => row.id"
          :reserve-selection="true"
          @header-dragend="onHeaderDragEnd"
          @selection-change="onSelectionChange"
        >
          <el-table-column
            v-if="proposalMode"
            type="selection"
            :width="SELECTION_WIDTH"
            fixed="left"
            :selectable="isSelectable"
          />
          <el-table-column
            label="图片"
            :width="IMAGE_WIDTH"
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
                  loading="lazy"
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
            class-name="cell-code"
            :width="colWidth('productNo')"
            :min-width="colMin('productNo')"
            :show-overflow-tooltip="{ teleported: true, placement: 'top' }"
          />
          <el-table-column
            prop="productName"
            label="产品名称"
            class-name="cell-strong"
            :width="colWidth('productName')"
            :min-width="colMin('productName')"
            :show-overflow-tooltip="{ teleported: true, placement: 'top' }"
          />
          <el-table-column
            prop="brandName"
            label="品牌"
            class-name="cell-soft"
            :width="colWidth('brandName')"
            :min-width="colMin('brandName')"
            :show-overflow-tooltip="{ teleported: true, placement: 'top' }"
          />
          <el-table-column
            prop="categoryName"
            label="分类"
            class-name="cell-soft"
            :width="colWidth('categoryName')"
            :min-width="colMin('categoryName')"
            :show-overflow-tooltip="{ teleported: true, placement: 'top' }"
          />
          <el-table-column
            prop="facePrice"
            label="面价"
            :width="colWidth('facePrice')"
            :min-width="colMin('facePrice')"
            align="right"
          >
            <template #default="{ row }">
              <span
                v-if="isPendingPrice(row)"
                class="status-text tone-warn"
              >待核价</span>
              <span
                v-else
                class="price-text"
              >{{ facePriceText(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column
            v-if="canViewCost"
            prop="costPrice"
            label="成本价"
            :width="colWidth('costPrice')"
            :min-width="colMin('costPrice')"
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
            :width="colWidth('stockStatus')"
            :min-width="colMin('stockStatus')"
            align="center"
          >
            <template #default="{ row }">
              <span
                class="status-text"
                :class="`tone-${stockTone(row.stockStatus)}`"
              >{{ stockStatusMap[row.stockStatus] || row.stockStatus }}</span>
            </template>
          </el-table-column>
          <el-table-column
            prop="status"
            label="状态"
            :width="colWidth('status')"
            :min-width="colMin('status')"
            align="center"
          >
            <template #default="{ row }">
              <span
                class="status-text"
                :class="`tone-${statusTone(row.status)}`"
              >{{ statusMap[row.status] || row.status }}</span>
            </template>
          </el-table-column>
          <el-table-column
            label="操作"
            class-name="op-col"
            :width="colWidth('operation')"
            :min-width="colMin('operation')"
            align="center"
          >
            <template #default="{ row }">
              <el-button
                size="small"
                text
                class="action-link"
                @click="handleView(row)"
              >
                查看
              </el-button>
              <el-button
                v-if="canEdit"
                size="small"
                text
                class="action-link"
                @click="handleEdit(row)"
              >
                编辑
              </el-button>
              <el-dropdown trigger="click">
                <button
                  type="button"
                  class="more-trigger"
                  aria-label="更多操作"
                >
                  <el-icon><ArrowDown /></el-icon>
                </button>
                <template #dropdown>
                  <el-dropdown-menu class="flat-action-menu">
                    <el-dropdown-item
                      v-if="canChangeStatus"
                      @click="showStatusDialog(row)"
                    >
                      状态
                    </el-dropdown-item>
                    <el-dropdown-item
                      v-if="canClone"
                      @click="handleClone(row)"
                    >
                      克隆
                    </el-dropdown-item>
                    <el-dropdown-item
                      v-if="canDelete"
                      class="dropdown-item-danger"
                      @click="handleDelete(row)"
                    >
                      删除
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div
        v-else
        class="product-grid-wrap"
      >
        <div class="product-grid">
          <article
            v-for="row in products"
            :key="row.id"
            class="product-tile"
            :class="{ 'is-selected': proposalMode && selectedIds.has(row.id) }"
            role="button"
            tabindex="0"
            :aria-label="`查看产品 ${row.productName}`"
            @click="handleGridTileClick(row)"
            @keydown.enter="handleGridTileClick(row)"
            @keydown.space.prevent="handleGridTileClick(row)"
          >
            <div class="product-tile-image">
              <el-image
                v-if="row.primaryImage?.tileUrl || row.primaryImage?.url"
                :src="row.primaryImage.tileUrl || row.primaryImage.url"
                fit="cover"
                loading="lazy"
                class="tile-img"
              >
                <template #error>
                  <div class="tile-placeholder">
                    {{ getPlaceholderText(row.productName) }}
                  </div>
                </template>
              </el-image>
              <div
                v-else
                class="tile-placeholder"
              >
                {{ getPlaceholderText(row.productName) }}
              </div>
            </div>
            <div class="product-tile-body">
              <div class="product-tile-meta">
                <span class="product-tile-no">{{ row.productNo }}</span>
                <span
                  class="status-text tile-status"
                  :class="`tone-${statusTone(row.status)}`"
                >{{ statusMap[row.status] || row.status }}</span>
              </div>
              <h3 class="product-tile-name">
                {{ row.productName }}
              </h3>
              <p class="product-tile-brand">
                {{ row.brandName || '未设置品牌' }}
              </p>
              <div class="product-tile-footer">
                <span class="product-tile-price">¥{{ row.facePrice.toFixed(2) }}</span>
                <span class="product-tile-category">
                  {{ row.categoryName || '-' }}
                </span>
              </div>
            </div>
          </article>
        </div>
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
import { ref, reactive, computed, onMounted, nextTick, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { View, Hide, Operation, Grid, List, ArrowDown } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { productApi, categoryApi, brandApi, supplierApi, tagApi } from '@/api'
import { usePreference } from '@/composables/usePreference'
import { fillColumnWidths, type FillColumn } from '@/utils/columnFill'
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
/**
 * 状态只是次要信息，不再用实色标签，改成低饱和的纯文字（.status-text）。
 * 这里只决定语义色调，具体颜色在样式里；找不到映射就退化成最弱的 muted。
 */
const STATUS_TONE: Record<string, string> = { active: 'ok', inactive: 'danger', draft: 'muted' }
const STOCK_TONE: Record<string, string> = { in_stock: 'ok', out_of_stock: 'danger', preorder: 'warn', unknown: 'muted' }
const statusTone = (value: string) => STATUS_TONE[value] || 'muted'
const stockTone = (value: string) => STOCK_TONE[value] || 'muted'

// 面价 99999 + 资料待完善 = 还没核过价，列里显示「待核价」而不是那个占位数字。
const isPendingPrice = (row: any) => row.facePrice === 99999 && row.completenessStatus === 'pending'
const facePriceText = (row: any) => (isPendingPrice(row) ? '待核价' : `¥${Number(row.facePrice).toFixed(2)}`)

const loading = ref(false)
const products = ref<any[]>([])
const total = ref(0)
const showCreateDialog = ref(false)
const editingProduct = ref<any>(null)
const submitting = ref(false)
const productFormRef = ref<FormInstance>()

// 视图模式和列宽策略是用户习惯，记在浏览器里，下次进来沿用上次的选择。
const viewMode = usePreference<'table' | 'grid'>('products.viewMode', 'table', ['table', 'grid'] as const)
const autoFit = usePreference('products.autoFit', true)
// 成本价开关是敏感信息的临时揭示，只在本次会话生效，不做持久化。
const costVisible = ref(false)
const colWidths = ref<Record<string, number>>({})
// 手动拖过的列宽（自适应模式下当固定列用），切换列宽策略时清空
const pinnedWidths = ref<Record<string, number>>({})
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

const handleGridTileClick = (row: any) => {
  if (proposalMode.value) {
    toggleMobileSelection(row)
    return
  }
  handleView(row)
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

/**
 * 量宽用的字体串必须跟 design-system.css 对齐：正文取 --pim-font-sans，产品编号列套了
 * .cell-code（--pim-font-mono 12px），产品名称是 .cell-strong（600），价格是 .price-text
 * （--pim-font-mono 600），表头统一 12px/500。换字体不同步这里，列宽就会整体偏窄或偏宽。
 * canvas 的 font 简写不接受 ui-sans-serif / system-ui，所以只留能被解析的部分。
 */
const FAMILY_SANS = '"HarmonyOS Sans", "HarmonyOS Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif'
const FAMILY_MONO = '"HarmonyOS Sans", Menlo, Consolas, monospace'
const FONT_BODY = `14px ${FAMILY_SANS}`
const FONT_STRONG = `600 14px ${FAMILY_SANS}`
const FONT_CODE = `12px ${FAMILY_MONO}`
const FONT_PRICE = `600 14px ${FAMILY_MONO}`
const FONT_STATUS = `500 13px ${FAMILY_SANS}`
const FONT_HEAD = `500 12px ${FAMILY_SANS}`
// 表头 letter-spacing: 0.06em @12px、产品编号列 0.02em @12px，canvas 量不到字距，按字数补
const TRACK_HEAD = 0.72
const TRACK_CODE = 0.24
/**
 * 操作列宽度。只需容纳「查看 / 编辑 / 更多」三个控件。chromium 实测（132px 列宽下）：
 * 两个 12px 双字文本按钮各 24px、更多按钮 28px + 6px 左外边距；按钮之间除了
 * .op-col .cell 的 gap: 4px，还叠着 Element Plus 默认的
 * `.el-button + .el-button { margin-left: 12px }`（本页没有重置它），所以两个文本按钮
 * 之间实际是 16px、文本按钮到更多按钮之间是 10px，按钮组实测 102px。
 * 再加单元格左右内边距 2×14px（design-system.css 的 .el-table .cell），合计 130px，
 * 132px 只剩约 2px 余量 —— 改按钮尺寸/文案/间距或收窄列宽都会立刻溢出。
 * 它只是操作列的**下限**，宽屏上 computeFillWidths() 会按权重再分一点给它。
 */
const OPERATION_WIDTH = 132
const SELECTION_WIDTH = 50
const IMAGE_WIDTH = 80
// 单元格左右内边距：design-system.css 的 .el-table .cell 是 padding-inline: 14px
const CELL_PADDING = 28

/**
 * 列宽模型：每列给「最小宽 / 最大宽 / 弹性权重」，算法见 @/utils/columnFill。
 * grow 是**剩余空间的分配权重**，不是绝对宽度 —— 产品名称拿最大一份，状态类列只拿一点点
 * （内容就两三个字，拉太宽只会让整行更散）。max 是上限，产品名称不设上限，兜住所有余量，
 * 所以 2K / 4K 屏上列宽之和始终等于容器宽度，右侧不留白。
 * text/font 决定量哪段文本、用哪个字体串；headExtra 给表头里除文字之外的控件留位置。
 */
interface ColumnSpec {
  prop: string
  label: string
  min: number
  max: number
  grow: number
  font: string
  track?: number
  headExtra?: number
  text?: (row: any) => string
}
const COLUMNS: ColumnSpec[] = [
  { prop: 'productNo', label: '产品编号', min: 110, max: 260, grow: 0.6, font: FONT_CODE, track: TRACK_CODE },
  { prop: 'productName', label: '产品名称', min: 180, max: Number.POSITIVE_INFINITY, grow: 3, font: FONT_STRONG },
  { prop: 'brandName', label: '品牌', min: 92, max: 220, grow: 0.7, font: FONT_BODY },
  { prop: 'categoryName', label: '分类', min: 96, max: 240, grow: 0.7, font: FONT_BODY },
  {
    prop: 'facePrice',
    label: '面价',
    min: 104,
    max: 180,
    grow: 0.5,
    font: FONT_PRICE,
    text: (row) => facePriceText(row),
  },
  {
    prop: 'costPrice',
    label: '成本价',
    min: 108,
    max: 180,
    grow: 0.5,
    font: FONT_PRICE,
    headExtra: 26,
    text: (row) => (row.costPrice == null ? '—' : `¥${Number(row.costPrice).toFixed(2)}`),
  },
  { prop: 'stockStatus', label: '库存', min: 76, max: 130, grow: 0.4, font: FONT_STATUS, text: (row) => stockStatusMap[row.stockStatus] || row.stockStatus || '' },
  { prop: 'status', label: '状态', min: 72, max: 130, grow: 0.4, font: FONT_STATUS, text: (row) => statusMap[row.status] || row.status || '' },
  { prop: 'operation', label: '操作', min: OPERATION_WIDTH, max: 200, grow: 0.6, font: FONT_BODY, text: () => '' },
]
const COL_MIN: Record<string, number> = {}
for (const spec of COLUMNS) COL_MIN[spec.prop] = spec.min

/*
 * 量宽用的 canvas 上下文按需创建，不要在 setup 里就建：jsdom 根本没实现 getContext('2d')，
 * 提前调用会让每个挂载 Products.vue 的组件测试都吐一堆 "Not implemented" 噪音。
 * 而 jsdom 里量不到容器宽度（clientWidth 恒为 0），computeFillWidths() 会提前返回，
 * 也就永远走不到这里。
 */
let _measureCtx: CanvasRenderingContext2D | null = null
let _measureTried = false

function measureCtx(): CanvasRenderingContext2D | null {
  if (!_measureTried) {
    _measureTried = true
    _measureCtx = document.createElement('canvas').getContext('2d')
  }
  return _measureCtx
}

// 拿不到上下文时退化成按字数估宽，不要在这里抛异常。
function measureTextWidth(text: string, font = FONT_BODY): number {
  const str = text == null ? '' : String(text)
  const ctx = measureCtx()
  if (!ctx) return str.length * 8
  ctx.font = font
  return ctx.measureText(str).width
}

function getTableWidth(): number {
  const el = productTableRef.value?.$el as HTMLElement | undefined
  return el ? el.clientWidth : 0
}

// 一列的「自然宽度」：表头和本页所有行里最宽的那段文本 + 单元格内边距。
// +2 是取整余量，宁可多 2px，也别让文字刚好被 ellipsis 掉一个字。
function naturalWidth(spec: ColumnSpec): number {
  let w = measureTextWidth(spec.label, FONT_HEAD) + spec.label.length * TRACK_HEAD + (spec.headExtra ?? 0)
  for (const row of products.value) {
    const txt = spec.text ? spec.text(row) : row[spec.prop] == null ? '' : String(row[spec.prop])
    w = Math.max(w, measureTextWidth(txt, spec.font) + txt.length * (spec.track ?? 0))
  }
  return Math.ceil(w) + CELL_PADDING + 2
}

/**
 * 确定性填充：所有列宽之和 == 表格容器宽度（见 @/utils/columnFill）。
 * 图片列和方案模式的勾选列是死宽度，但也要算进去，否则总宽会差出一列来。
 * 手动拖过的列按拖出来的宽度钉住，不再参与分配。
 */
function computeFillWidths() {
  if (!autoFit.value) return
  const container = getTableWidth()
  if (!container) return
  const cols: FillColumn[] = []
  const fixed = (prop: string, width: number) => ({ prop, natural: width, min: width, max: width, grow: 0 })
  if (proposalMode.value) cols.push(fixed('selection', SELECTION_WIDTH))
  cols.push(fixed('image', IMAGE_WIDTH))
  for (const spec of COLUMNS) {
    if (spec.prop === 'costPrice' && !canViewCost.value) continue
    const pinned = pinnedWidths.value[spec.prop]
    cols.push(
      pinned
        ? fixed(spec.prop, pinned)
        : { prop: spec.prop, natural: naturalWidth(spec), min: spec.min, max: spec.max, grow: spec.grow },
    )
  }
  colWidths.value = fillColumnWidths(cols, container, 'productName')
  nextTick(() => productTableRef.value?.doLayout())
}

/**
 * 拖过的列宽记进 pinnedWidths，之后每次重算都当固定列。产品名称是吸收余量的锚列，
 * 钉住它就等于把右侧留白重新放回来，所以拖它只触发重算。「自适应/紧凑」按钮清空记忆。
 */
function onHeaderDragEnd(newWidth: number, _oldWidth: number, column: any) {
  if (!autoFit.value) return
  const prop = column?.property
  if (prop && prop !== 'productName') {
    pinnedWidths.value = { ...pinnedWidths.value, [prop]: Math.round(newWidth) }
  }
  computeFillWidths()
}

function toggleAutoFit() {
  autoFit.value = !autoFit.value
  pinnedWidths.value = {}
  if (autoFit.value) computeFillWidths()
  nextTick(() => productTableRef.value?.doLayout())
}

// 紧凑模式交回 Element Plus 的 fit 平均分配，此时只给 min-width；自适应模式给算好的定宽。
function colWidth(prop: string): number | undefined {
  return autoFit.value ? colWidths.value[prop] : undefined
}

function colMin(prop: string): number {
  return COL_MIN[prop] ?? 90
}

/*
 * 列表里的图一律走后端缩略图（GET .../content?w=<短边>），不要直接挂原图。
 * 库里的封面基本都是 4000×3000（12MP）的相机原图，一页 20 行光解码就是 ~3GB
 * RGBA，滚动时浏览器反复丢弃/重解码位图 —— 这是滚轮卡顿的主因。
 * 宽度必须落在后端 _THUMB_WIDTHS 白名单里（backend/app/api/v1/files.py），
 * 写错后端直接回 422（故意不静默回退成原图，否则这种 typo 永远发现不了）。
 * 64px 的表格方框取 192（retina 上 3 倍密度，单张也就十几 KB）；
 * 网格瓦片最宽约 360px，取 480 够用。灯箱预览仍用原图 url。
 */
const TABLE_THUMB_WIDTH = 192
const TILE_THUMB_WIDTH = 480

function withThumbWidth(url: string, width: number): string {
  if (!url) return url
  return `${url}${url.includes('?') ? '&' : '?'}w=${width}`
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
        thumbnailUrl: withThumbWidth(item.cover_image_url, TABLE_THUMB_WIDTH),
        tileUrl: withThumbWidth(item.cover_image_url, TILE_THUMB_WIDTH),
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
  // 必须走 router.push：后台是以 base '/admin/' 构建的，`window.open('/products/x')`
  // 会打到 nginx 的 location /（门户），门户没有这条路由 → 白屏。
  // router.push 会自动带上 import.meta.env.BASE_URL，且免掉一次整页重载。
  router.push({ name: 'ProductDetail', params: { id: String(row.id) } })
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

/**
 * 视图模式是持久化的，可能一进页面就是卡片视图，此时表格没渲染、量不到容器宽度。
 * 切回表格视图时补一次测量，否则列宽会全部回落到 min-width。
 * 方案模式增删勾选列同样要重算。
 */
watch([viewMode, proposalMode], () => {
  if (viewMode.value !== 'table') return
  nextTick(() => computeFillWidths())
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
/* 这里不要再加 backdrop-filter：卡片背后是 .products-page 的纯色 #f0f0f0，
   模糊纯色画面上毫无变化，但滚动时每帧都要重算整卡可见区域 —— 列表页滚轮卡顿
   的主因之一。毛玻璃只留给压在内容上的浮层（弹窗、遮罩）。 */
.glass-card {
  background: var(--glass-bg);
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

.view-mode-toggle {
  align-self: center;
}

.view-mode-toggle :deep(.el-radio-button__inner) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 36px;
  padding: 0 12px;
  border: 0;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 0 0 1px rgba(30, 50, 90, 0.08) inset;
}

.view-mode-toggle :deep(.el-radio-button__inner .el-icon) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.view-mode-toggle :deep(.el-radio-button__orig-radio:checked + .el-radio-button__inner) {
  background: rgba(30, 50, 90, 0.92);
  color: #fff;
  box-shadow: none;
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

.action-link {
  padding: 0;
  min-height: 0;
  border: 0;
  background: transparent;
  color: var(--text-primary);
  font-weight: 500;
}

.action-link:hover {
  background: transparent;
  color: var(--brand-deep);
}

.more-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  margin-left: 6px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: var(--transition-fast);
}

.more-trigger:hover {
  color: var(--brand-deep);
  background: rgba(30, 50, 90, 0.06);
}

.flat-action-menu {
  padding: 6px;
}

.flat-action-menu :deep(.el-dropdown-menu__item) {
  border-radius: 10px;
  line-height: 1.1;
  padding: 9px 14px;
  color: var(--text-primary);
}

.flat-action-menu :deep(.el-dropdown-menu__item:hover) {
  background: rgba(30, 50, 90, 0.06);
  color: var(--brand-deep);
}

.dropdown-item-danger {
  color: #f56c6c;
}

.dropdown-item-danger:hover {
  background: #fef0f0;
  color: #f56c6c;
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
  gap: 4px;
  white-space: nowrap;
}

/* 表头与单元格的字号、字重、颜色统一由 design-system.css 的表格规则给出，
   这里只留页面自己的东西（悬停底色、分割线形态），避免两套排版互相打架。 */
.product-table :deep(.el-table__row:hover td) {
  background: var(--brand-lighter);
}

/*
 * 分割线：竖线全部去掉（`border` 属性已从 el-table 上摘掉，design-system.css 里
 * `.el-table:not(.el-table--border) td` 的 border-right 本就是 0），列之间只靠 cell 的
 * 左右内边距留白分隔。横线保留，但两端各内缩一个 cell padding，不再顶到表格边缘 ——
 * 这就是「不满行的横分割线」。
 *
 * 为什么用 td::after 而不是 border-bottom 或 background-image：
 * border-bottom 只能满格，画不出内缩；background-image 会被 design-system.css 里
 * 斑马行那条 `background:` **简写**连着 background-image 一起重置掉，隔行就断线。
 */
.product-table :deep(.el-table__body td.el-table__cell) {
  position: relative;
  border-bottom: 0;
}

.product-table :deep(.el-table__body td.el-table__cell)::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 1px;
  background: var(--pim-line);
  pointer-events: none;
}

.product-table :deep(.el-table__body td.el-table__cell:first-child)::after {
  left: 14px;
}

.product-table :deep(.el-table__body td.el-table__cell:last-child)::after {
  right: 14px;
}

/* 最后一行不画线（design-system.css 对 border-bottom 也是这个口径），
   否则表格底边会和分页区之间多出一条无意义的线。 */
.product-table :deep(.el-table__body tr:last-child td.el-table__cell)::after {
  display: none;
}

/* 表头下面那条同样内缩，和行分割线的左右端点对齐 */
.product-table :deep(.el-table__header th.el-table__cell) {
  position: relative;
  border-bottom: 0;
}

.product-table :deep(.el-table__header th.el-table__cell)::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 1px;
  background: var(--pim-line-strong);
  pointer-events: none;
}

.product-table :deep(.el-table__header th.el-table__cell:first-child)::after {
  left: 14px;
}

.product-table :deep(.el-table__header th.el-table__cell:last-child)::after {
  right: 14px;
}

.price-text {
  color: var(--brand-deep);
  font-weight: 600;
  font-family: var(--pim-font-mono);
  font-variant-numeric: tabular-nums;
}

.product-grid-wrap {
  margin-top: 4px;
}

.product-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}

.product-tile {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-radius: 16px;
  background: #fff;
  border: 1px solid rgba(30, 50, 90, 0.06);
  box-shadow: 0 4px 16px rgba(30, 50, 90, 0.05);
  cursor: pointer;
  transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
}

.product-tile:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 28px rgba(30, 50, 90, 0.08);
}

.product-tile.is-selected {
  border-color: rgba(30, 50, 90, 0.28);
  box-shadow: 0 0 0 2px rgba(30, 50, 90, 0.08), 0 10px 28px rgba(30, 50, 90, 0.08);
}

.product-tile-image {
  aspect-ratio: 1 / 1;
  background: linear-gradient(180deg, rgba(30, 50, 90, 0.03), rgba(30, 50, 90, 0.01));
  overflow: hidden;
}

.tile-img {
  width: 100%;
  height: 100%;
  display: block;
}

.tile-img :deep(img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.tile-placeholder {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  color: rgba(30, 50, 90, 0.42);
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0.08em;
  background: linear-gradient(135deg, rgba(30, 50, 90, 0.04), rgba(30, 50, 90, 0.02));
}

.product-tile-body {
  display: grid;
  gap: 10px;
  padding: 16px;
}

.product-tile-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.product-tile-no {
  color: var(--text-secondary);
  font-family: monospace;
  font-size: 12px;
}

.tile-status {
  flex: 0 0 auto;
}

.product-tile-name {
  margin: 0;
  color: var(--brand-deep);
  font-size: 17px;
  font-weight: 600;
  line-height: 1.35;
  letter-spacing: -0.02em;
  min-height: 2.7em;
}

.product-tile-brand {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.product-tile-footer {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.product-tile-price {
  color: var(--brand-deep);
  font-size: 18px;
  font-weight: 700;
  font-family: monospace;
}

.product-tile-category {
  color: var(--text-secondary);
  font-size: 12px;
  text-align: right;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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

/*
 * 状态标识：不要实色标签、不要按钮容器，只留一行低饱和的字。
 * 状态在这张表里不是重点（上架/有货是绝大多数行的常态），做成 chip 反而抢了名称和价格的视线。
 * 色相保留（绿=正常、琥珀=待定、砖红=异常），但把彩度压到接近灰，同时靠加深保证
 * 对白底 ≥ 4.5:1 的对比度 —— 弱化的是饱和度，不是可读性。
 */
.status-text {
  display: inline-block;
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

.status-text.tone-ok {
  color: #4f6b57;
}

.status-text.tone-warn {
  color: #8a6a3c;
}

.status-text.tone-danger {
  color: #8f5b57;
}

.status-text.tone-muted {
  color: rgba(30, 50, 90, 0.7);
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

  .view-mode-toggle {
    width: 100%;
  }

  .view-mode-toggle :deep(.el-radio-button) {
    flex: 1;
  }

  .view-mode-toggle :deep(.el-radio-button__inner) {
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

  .product-table :deep(.el-table__header th),
  .product-table :deep(.el-table__row td) {
    font-size: 12px;
  }

  .product-grid {
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 10px;
  }

  .product-tile-body {
    padding: 12px;
  }

  .product-tile-name {
    font-size: 15px;
    min-height: 2.4em;
  }

  .product-tile-price {
    font-size: 16px;
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
