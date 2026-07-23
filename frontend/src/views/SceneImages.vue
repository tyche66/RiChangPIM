<template>
  <div class="scene-images-page">
    <!-- Header -->
    <div class="si-header">
      <div>
        <h2 class="si-title">
          场景图管理
        </h2>
        <p class="si-subtitle">
          管理用于产品展示和客户分享的场景图片
        </p>
      </div>
      <div class="header-actions">
        <el-button
          v-if="canEdit"
          :type="selectedIds.length > 0 ? 'warning' : 'default'"
          :icon="Link"
          :disabled="selectedIds.length === 0"
          @click="showBatchBindDialog = true"
        >
          批量绑定{{ selectedIds.length > 0 ? ` (${selectedIds.length})` : '' }}
        </el-button>
        <el-button
          v-if="canCreate"
          type="primary"
          :icon="Plus"
          @click="openCreate"
        >
          新建场景图
        </el-button>
      </div>
    </div>

    <!-- Filter Toolbar -->
    <div class="si-toolbar">
      <div class="toolbar-left">
        <el-input
          v-model="keyword"
          placeholder="搜索场景图名称..."
          clearable
          :prefix-icon="Search"
          class="si-search"
          @input="debouncedFetch"
        />
        <el-input
          v-model="productKeyword"
          placeholder="按产品搜索（名称/编号）..."
          clearable
          :prefix-icon="Goods"
          class="si-search"
          @input="debouncedFetch"
        />
      </div>
      <div class="toolbar-right">
        <el-select
          v-model="statusFilter"
          placeholder="绑定状态"
          clearable
          class="si-filter"
        >
          <el-option
            label="全部"
            value=""
          />
          <el-option
            label="已绑定产品"
            value="bound"
          />
          <el-option
            label="未绑定产品"
            value="unbound"
          />
        </el-select>
        <el-select
          v-model="sortOrder"
          placeholder="排序"
          class="si-filter"
        >
          <el-option
            label="最新创建"
            value="newest"
          />
          <el-option
            label="名称 A-Z"
            value="name_asc"
          />
          <el-option
            label="名称 Z-A"
            value="name_desc"
          />
          <el-option
            label="绑定数量（多到少）"
            value="bound_desc"
          />
          <el-option
            label="绑定数量（少到多）"
            value="bound_asc"
          />
        </el-select>
        <el-radio-group
          v-model="viewMode"
          size="small"
        >
          <el-radio-button value="grid">
            <el-icon><Grid /></el-icon>
          </el-radio-button>
          <el-radio-button value="list">
            <el-icon><List /></el-icon>
          </el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- Gallery Grid -->
    <div
      v-if="viewMode === 'grid'"
      v-loading="loading"
      class="si-gallery"
    >
      <div
        v-for="item in items"
        :key="item.id"
        class="gallery-card"
        :class="{ 'is-selected': selectedIds.includes(item.id) }"
        @click="toggleSelect(item)"
        @dblclick="handleEdit(item)"
      >
        <div class="card-select-checkbox">
          <el-checkbox
            :model-value="selectedIds.includes(item.id)"
            @click.stop="toggleSelect(item)"
          />
        </div>
        <div
          class="gallery-thumb"
          @click.stop="openPreview(item)"
        >
          <el-image
            :src="item.preview_url || item.file_url"
            fit="cover"
            class="gallery-img"
          >
            <template #error>
              <div class="thumb-placeholder">
                <el-icon :size="32">
                  <Picture />
                </el-icon>
              </div>
            </template>
          </el-image>
          <div
            class="gallery-overlay"
            @click.stop
          >
            <el-button
              circle
              size="small"
              @click="openPreview(item)"
            >
              <el-icon><ZoomIn /></el-icon>
            </el-button>
            <el-button
              circle
              size="small"
              @click.stop="handleEdit(item)"
            >
              <el-icon><Edit /></el-icon>
            </el-button>
            <el-button
              circle
              size="small"
              @click.stop="handleBindProducts(item)"
            >
              <el-icon><Link /></el-icon>
            </el-button>
            <el-button
              circle
              size="small"
              @click.stop="openBindingsDrawer(item)"
            >
              <el-icon><View /></el-icon>
            </el-button>
            <el-button
              v-if="canDelete"
              circle
              size="small"
              type="danger"
              @click.stop="handleDelete(item)"
            >
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </div>
        <div class="gallery-info">
          <p class="gallery-name">
            {{ item.name }}
          </p>
          <div class="gallery-meta">
            <span><el-icon><Sort /></el-icon> {{ item.sort }}</span>
            <span>{{ formatDate(item.update_time) }}</span>
          </div>
          <div class="gallery-bindings">
            <el-tag
              v-if="item.bound_products.length > 0"
              size="small"
              type="warning"
              effect="plain"
            >
              <el-icon><Link /></el-icon>
              已绑定 {{ item.bound_products.length }} 个产品
            </el-tag>
            <el-tag
              v-else
              size="small"
              type="info"
              effect="plain"
            >
              未绑定
            </el-tag>
          </div>
        </div>
      </div>
      <div
        v-if="items.length === 0 && !loading"
        class="gallery-empty"
      >
        <el-empty description="暂无场景图">
          <el-button
            v-if="canCreate"
            type="primary"
            @click="openCreate"
          >
            新建场景图
          </el-button>
        </el-empty>
      </div>
    </div>

    <!-- List View -->
    <div
      v-else
      v-loading="loading"
      class="si-list"
    >
      <el-table
        :data="items"
        stripe
        style="width: 100%"
        @row-dblclick="handleEdit"
        @selection-change="handleSelectionChange"
      >
        <el-table-column
          type="selection"
          width="40"
          align="center"
        />
        <el-table-column
          label="缩略图"
          width="100"
          align="center"
        >
          <template #default="{ row }">
            <el-image
              :src="row.preview_url || row.file_url"
              fit="cover"
              class="list-thumb"
              @click="openPreview(row)"
            >
              <template #error>
                <div class="thumb-placeholder">
                  <el-icon :size="24">
                    <Picture />
                  </el-icon>
                </div>
              </template>
            </el-image>
          </template>
        </el-table-column>
        <el-table-column
          prop="name"
          label="名称"
          min-width="180"
        />
        <el-table-column
          prop="sort"
          label="排序"
          width="80"
          align="center"
        />
        <el-table-column
          label="绑定产品"
          width="120"
          align="center"
        >
          <template #default="{ row }">
            <el-tag
              :type="row.bound_products.length > 0 ? 'warning' : 'info'"
              size="small"
              effect="plain"
            >
              {{ row.bound_products.length }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          label="更新时间"
          width="160"
        >
          <template #default="{ row }">
            {{ formatDate(row.update_time) }}
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
          width="300"
          align="center"
          fixed="right"
        >
          <template #default="{ row }">
            <el-button
              text
              size="small"
              @click="openPreview(row)"
            >
              预览
            </el-button>
            <el-button
              text
              size="small"
              @click="handleEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              text
              size="small"
              @click="handleBindProducts(row)"
            >
              绑定
            </el-button>
            <el-button
              text
              size="small"
              @click="openBindingsDrawer(row)"
            >
              查看绑定
            </el-button>
            <el-button
              v-if="canDelete"
              text
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

    <!-- Pagination -->
    <div
      v-if="total > 0"
      class="pagination-bar"
    >
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        :total="total"
        @change="fetchData"
      />
    </div>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="showCreateDialog"
      :title="editingItem ? '编辑场景图' : '新建场景图'"
      class="glass-dialog"
      append-to-body
      lock-scroll
      :close-on-click-modal="false"
      destroy-on-close
      width="560px"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="90px"
      >
        <el-form-item
          label="场景图图片"
          prop="attachment_id"
        >
          <div class="media-select-area">
            <div
              v-if="selectedMediaList.length > 0"
              class="selected-media-preview-wrap"
              @click="showMediaPicker = true"
            >
              <el-image
                :src="selectedMediaList[0].thumbnailUrl || selectedMediaList[0].url"
                fit="cover"
                class="selected-media-preview"
              >
                <template #error>
                  <div class="thumb-placeholder">
                    <el-icon :size="24">
                      <Picture />
                    </el-icon>
                  </div>
                </template>
              </el-image>
              <div
                v-if="selectedMediaList.length > 1"
                class="selected-media-more"
              >
                已选择 {{ selectedMediaList.length }} 张图片
              </div>
            </div>
            <el-button
              v-else
              type="primary"
              class="capsule-btn"
              @click="showMediaPicker = true"
            >
              <el-icon><Plus /></el-icon>
              从媒体库选择图片
            </el-button>
            <el-button
              v-if="selectedMediaList.length > 0"
              size="small"
              text
              type="danger"
              @click="clearMedia"
            >
              清除
            </el-button>
          </div>
        </el-form-item>
        <el-form-item
          label="场景图名称"
          prop="name"
        >
          <el-input
            v-model="form.name"
            class="capsule-input"
            placeholder="请输入场景图名称"
          />
        </el-form-item>
        <el-form-item label="排序值">
          <el-input-number
            v-model="form.sort"
            :min="0"
            class="capsule-number full-width"
          />
        </el-form-item>
        <el-divider content-position="left">
          绑定产品（可选）
        </el-divider>
        <el-form-item label="直接绑定">
          <div class="bind-products-inline">
            <el-input
              v-model="createFormProductSearch"
              placeholder="搜索产品名称/编号..."
              clearable
              :prefix-icon="Search"
              class="bind-search-input"
              @input="searchProductsForCreate"
            />
            <div
              v-loading="productSearchLoading"
              class="product-search-results"
            >
              <div
                v-for="p in productSearchResults"
                :key="p.id"
                class="product-card"
                :class="{ 'is-bound': formProductIds.includes(p.id) }"
                @click="toggleFormProduct(p)"
              >
                <div class="product-thumb">
                  <el-image
                    v-if="p.cover_image_url"
                    :src="p.cover_image_url"
                    fit="cover"
                    class="product-thumb-img"
                  >
                    <template #error>
                      <div class="thumb-placeholder">
                        <el-icon :size="16">
                          <Picture />
                        </el-icon>
                      </div>
                    </template>
                  </el-image>
                  <div
                    v-else
                    class="thumb-placeholder"
                  >
                    <el-icon :size="16">
                      <Goods />
                    </el-icon>
                  </div>
                </div>
                <div class="product-info">
                  <span class="product-no">{{ p.product_no }}</span>
                  <span class="product-name">{{ p.product_name }}</span>
                </div>
                <el-icon
                  v-if="formProductIds.includes(p.id)"
                  color="var(--el-color-success)"
                  :size="16"
                >
                  <Check />
                </el-icon>
                <el-icon
                  v-else
                  color="var(--el-color-primary)"
                  :size="16"
                >
                  <Plus />
                </el-icon>
              </div>
              <div
                v-if="productSearchResults.length === 0 && !productSearchLoading"
                class="empty-tip"
              >
                输入关键词搜索产品
              </div>
            </div>
          </div>
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
          :loading="saving"
          class="capsule-btn capsule-btn-primary"
          @click="handleSubmit"
        >
          保存
        </el-button>
      </template>
    </el-dialog>

    <!-- Single Bind Products Dialog -->
    <el-dialog
      v-model="showBindDialog"
      title="绑定产品"
      class="glass-dialog"
      append-to-body
      lock-scroll
      :close-on-click-modal="false"
      destroy-on-close
      width="700px"
    >
      <div
        v-if="bindingItem"
        class="bind-dialog-body"
      >
        <div class="bind-info">
          <el-image
            :src="bindingItem.preview_url || bindingItem.file_url"
            fit="cover"
            class="bind-thumb"
          />
          <div class="bind-meta">
            <p class="bind-name">
              {{ bindingItem.name }}
            </p>
            <p class="bind-count">
              已绑定 {{ bindingItem.bound_products.length }} 个产品
            </p>
          </div>
        </div>

        <el-tabs v-model="bindTab">
          <el-tab-pane
            label="已绑定产品"
            name="bound"
          >
            <div
              v-if="bindingItem.bound_products.length === 0"
              class="empty-tip"
            >
              暂无已绑定产品，请切换到"添加绑定"标签页
            </div>
            <div
              v-else
              class="bound-product-list"
            >
              <div
                v-for="p in bindingItem.bound_products"
                :key="p.id"
                class="bound-product-item"
              >
                <span class="product-no">{{ p.product_no }}</span>
                <span class="product-name">{{ p.product_name }}</span>
                <div class="bound-actions">
                  <el-button
                    text
                    size="small"
                    type="primary"
                    @click="navigateToProduct(p.id)"
                  >
                    <el-icon><View /></el-icon> 详情
                  </el-button>
                  <el-button
                    text
                    size="small"
                    type="danger"
                    @click="confirmUnbind(p.id)"
                  >
                    <el-icon><Delete /></el-icon> 解绑
                  </el-button>
                </div>
              </div>
            </div>
          </el-tab-pane>
          <el-tab-pane
            label="添加绑定"
            name="add"
          >
            <div class="add-bind-section">
              <el-input
                v-model="bindSearch"
                placeholder="搜索产品编号/名称..."
                clearable
                :prefix-icon="Search"
                class="capsule-input"
                @input="searchProducts"
              />
              <div
                v-loading="productSearchLoading"
                class="product-search-results"
              >
                <div
                  v-for="p in productSearchResults"
                  :key="p.id"
                  class="product-card"
                  :class="{ 'is-bound': isProductBound(p.id) }"
                  @click="selectProductForBind(p.id)"
                >
                  <div class="product-thumb">
                    <el-image
                      v-if="p.cover_image_url"
                      :src="p.cover_image_url"
                      fit="cover"
                      class="product-thumb-img"
                    >
                      <template #error>
                        <div class="thumb-placeholder">
                          <el-icon :size="16">
                            <Picture />
                          </el-icon>
                        </div>
                      </template>
                    </el-image>
                    <div
                      v-else
                      class="thumb-placeholder"
                    >
                      <el-icon :size="16">
                        <Goods />
                      </el-icon>
                    </div>
                  </div>
                  <span class="product-no">{{ p.product_no }}</span>
                  <span class="product-name">{{ p.product_name }}</span>
                  <el-icon
                    v-if="isProductBound(p.id)"
                    color="var(--el-color-success)"
                    :size="16"
                  >
                    <Check />
                  </el-icon>
                  <el-icon
                    v-else
                    color="var(--el-color-primary)"
                    :size="16"
                  >
                    <Plus />
                  </el-icon>
                </div>
                <div
                  v-if="productSearchResults.length === 0 && !productSearchLoading"
                  class="empty-tip"
                >
                  未找到匹配产品
                </div>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
      <template #footer>
        <el-button
          class="capsule-btn"
          @click="showBindDialog = false"
        >
          关闭
        </el-button>
      </template>
    </el-dialog>

    <!-- Batch Bind Dialog -->
    <el-dialog
      v-model="showBatchBindDialog"
      title="批量绑定产品"
      class="glass-dialog"
      append-to-body
      lock-scroll
      :close-on-click-modal="false"
      destroy-on-close
      width="700px"
    >
      <div class="batch-bind-body">
        <div class="batch-bind-info">
          <el-alert
            :title="`已选择 ${selectedIds.length} 张场景图进行批量绑定`"
            type="info"
            :closable="false"
            show-icon
          />
        </div>
        <el-divider>选择要绑定的产品</el-divider>
        <el-input
          v-model="batchProductSearch"
          placeholder="搜索产品编号/名称..."
          clearable
          :prefix-icon="Search"
          class="capsule-input"
          @input="searchBatchProducts"
        />
        <div
          v-loading="batchProductSearchLoading"
          class="product-search-results"
        >
          <div
            v-for="p in batchProductSearchResults"
            :key="p.id"
            class="product-card"
            :class="{ 'is-bound': batchSelectedProductIds.includes(p.id) }"
            @click="toggleBatchProduct(p)"
          >
            <div class="product-thumb">
              <el-image
                v-if="p.cover_image_url"
                :src="p.cover_image_url"
                fit="cover"
                class="product-thumb-img"
              >
                <template #error>
                  <div class="thumb-placeholder">
                    <el-icon :size="16">
                      <Picture />
                    </el-icon>
                  </div>
                </template>
              </el-image>
              <div
                v-else
                class="thumb-placeholder"
              >
                <el-icon :size="16">
                  <Goods />
                </el-icon>
              </div>
            </div>
            <span class="product-no">{{ p.product_no }}</span>
            <span class="product-name">{{ p.product_name }}</span>
            <el-icon
              v-if="batchSelectedProductIds.includes(p.id)"
              color="var(--el-color-success)"
              :size="16"
            >
              <Check />
            </el-icon>
            <el-icon
              v-else
              color="var(--el-color-primary)"
              :size="16"
            >
              <Plus />
            </el-icon>
          </div>
          <div
            v-if="batchProductSearchResults.length === 0 && !batchProductSearchLoading"
            class="empty-tip"
          >
            输入关键词搜索产品
          </div>
        </div>
      </div>
      <template #footer>
        <el-button
          class="capsule-btn"
          @click="showBatchBindDialog = false"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="batchBinding"
          :disabled="batchSelectedProductIds.length === 0"
          class="capsule-btn capsule-btn-primary"
          @click="confirmBatchBind"
        >
          确认绑定
        </el-button>
      </template>
    </el-dialog>

    <!-- Bindings Drawer -->
    <el-drawer
      v-model="showBindingsDrawer"
      title="场景图绑定关系"
      size="480px"
      append-to-body
      lock-scroll
      :before-close="handleCloseDrawer"
    >
      <div
        v-if="drawerItem"
        class="drawer-body"
      >
        <div class="drawer-scene-info">
          <el-image
            :src="drawerItem.preview_url || drawerItem.file_url"
            fit="cover"
            class="drawer-scene-thumb"
          />
          <div class="drawer-scene-meta">
            <p class="drawer-scene-name">
              {{ drawerItem.name }}
            </p>
            <p class="drawer-scene-count">
              共绑定 <strong>{{ drawerItem.bound_products.length }}</strong> 个产品
            </p>
          </div>
        </div>

        <el-divider>绑定产品列表</el-divider>

        <div
          v-if="drawerItem.bound_products.length === 0"
          class="empty-tip"
        >
          该场景图暂未绑定任何产品
        </div>
        <div
          v-else
          class="drawer-product-list"
        >
          <div
            v-for="p in drawerItem.bound_products"
            :key="p.id"
            class="drawer-product-item"
          >
            <div class="drawer-product-left">
              <span class="product-no">{{ p.product_no }}</span>
              <span class="product-name">{{ p.product_name }}</span>
            </div>
            <div class="drawer-product-actions">
              <el-button
                text
                size="small"
                type="primary"
                @click="navigateToProduct(p.id)"
              >
                <el-icon><View /></el-icon>
              </el-button>
              <el-button
                v-if="canEdit"
                text
                size="small"
                type="danger"
                @click="confirmUnbindFromDrawer(p.id)"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- Media Picker -->
    <MediaPicker
      v-model="showMediaPicker"
      :type-filter="'image'"
      :multiple="true"
      @select="handleMediaSelect"
    />

    <!-- Image Preview -->
    <el-image-viewer
      v-if="previewUrl"
      :url-list="[previewUrl]"
      @close="previewUrl = ''"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Search, Plus, Picture, Check, Grid, List,
  ZoomIn, Link, Edit, Delete, View, Sort, Goods,
} from '@element-plus/icons-vue'
import { sceneImageApi, productApi } from '@/api'
import type { SceneImage } from '@/api'
import { formatDate } from '@/api/media'
import MediaPicker from '@/components/MediaPicker.vue'
import type { MediaItem } from '@/api/media'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'

const router = useRouter()
const authStore = useAuthStore()
const userPermissions = computed(() => authStore.userPermissions)
const canCreate = computed(() => hasPermission(userPermissions.value, 'scene_image:create'))
const canEdit = computed(() => hasPermission(userPermissions.value, 'scene_image:edit'))
const canDelete = computed(() => hasPermission(userPermissions.value, 'scene_image:delete'))

const loading = ref(false)
const saving = ref(false)
const items = ref<SceneImage[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const productKeyword = ref('')
const statusFilter = ref('')
const sortOrder = ref('newest')
const viewMode = ref<'grid' | 'list'>('grid')

// Multi-select
const selectedIds = ref<string[]>([])

// Dialogs
const showCreateDialog = ref(false)
const showBindDialog = ref(false)
const showBatchBindDialog = ref(false)
const showBindingsDrawer = ref(false)
const showMediaPicker = ref(false)
const previewUrl = ref('')

const editingItem = ref<SceneImage | null>(null)
const bindingItem = ref<SceneImage | null>(null)
const drawerItem = ref<SceneImage | null>(null)
const selectedMediaList = ref<MediaItem[]>([])
const bindTab = ref('bound')
const bindSearch = ref('')
const productSearchResults = ref<any[]>([])
const productSearchLoading = ref(false)

// Form
const form = reactive({
  name: '',
  attachment_id: '',
  sort: 0,
})
const formProductIds = ref<string[]>([])
const createFormProductSearch = ref('')

// Batch bind
const batchProductSearch = ref('')
const batchProductSearchResults = ref<any[]>([])
const batchProductSearchLoading = ref(false)
const batchSelectedProductIds = ref<string[]>([])
const batchBinding = ref(false)

const rules = {
  name: [{ required: true, message: '请输入场景图名称', trigger: 'blur' }],
  attachment_id: [{ required: true, message: '请选择一张图片', trigger: 'change' }],
}

const formRef = ref()

// Debounced fetch
let fetchTimer: ReturnType<typeof setTimeout> | null = null
function debouncedFetch() {
  if (fetchTimer) clearTimeout(fetchTimer)
  fetchTimer = setTimeout(() => {
    page.value = 1
    fetchData()
  }, 300)
}

async function fetchData() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      keyword: keyword.value,
      page: page.value,
      size: pageSize.value,
    }
    if (statusFilter.value) params.status = statusFilter.value
    if (productKeyword.value) params.product_keyword = productKeyword.value
    if (sortOrder.value) params.sort = sortOrder.value

    const res: any = await sceneImageApi.list(params)
    const data = res.data?.data || res.data || res
    items.value = data.list || []
    total.value = data.total || items.value.length
  } catch {
    // handled by interceptor
  } finally {
    loading.value = false
  }
}

function toggleSelect(item: SceneImage) {
  const idx = selectedIds.value.indexOf(item.id)
  if (idx > -1) {
    selectedIds.value.splice(idx, 1)
  } else {
    selectedIds.value.push(item.id)
  }
}

function handleSelectionChange(selection: any[]) {
  selectedIds.value = selection.map((s) => s.id)
}

function openPreview(row: SceneImage) {
  previewUrl.value = row.preview_url || row.file_url
}

function openCreate() {
  editingItem.value = null
  form.name = ''
  form.attachment_id = ''
  form.sort = 0
  formProductIds.value = []
  createFormProductSearch.value = ''
  selectedMediaList.value = []
  if (formRef.value) formRef.value.resetFields()
  showCreateDialog.value = true
}

function handleEdit(item: SceneImage) {
  editingItem.value = item
  form.name = item.name
  form.attachment_id = item.attachment_id
  form.sort = item.sort
  formProductIds.value = item.bound_products.map((p) => p.id)
  selectedMediaList.value = [{
    id: item.attachment_id,
    name: item.file_name,
    type: 'image',
    mimeType: '',
    size: 0,
    url: item.preview_url || item.file_url,
    thumbnailUrl: item.preview_url || item.file_url,
    uploadedAt: item.create_time,
  } as MediaItem]
  showCreateDialog.value = true
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    saving.value = true
    try {
      if (editingItem.value || selectedMediaList.value.length <= 1) {
        const payload = {
          name: form.name,
          attachment_id: form.attachment_id,
          sort: form.sort,
          product_ids: formProductIds.value.length > 0 ? formProductIds.value : undefined,
        }
        if (editingItem.value) {
          await sceneImageApi.update(editingItem.value.id, payload)
          ElMessage.success('场景图已更新')
        } else {
          await sceneImageApi.create(payload)
          ElMessage.success('场景图已创建')
        }
      } else {
        const results = await Promise.allSettled(
          selectedMediaList.value.map((media, index) => sceneImageApi.create({
            name: form.name.trim() ? `${form.name.trim()}-${index + 1}` : media.name,
            attachment_id: media.id,
            sort: form.sort + index,
            product_ids: formProductIds.value.length > 0 ? formProductIds.value : undefined,
          })),
        )
        const successCount = results.filter((r) => r.status === 'fulfilled').length
        const failCount = results.length - successCount
        if (successCount > 0) ElMessage.success(`已创建 ${successCount} 张场景图`)
        if (failCount > 0) ElMessage.error(`有 ${failCount} 张场景图创建失败`)
      }
      showCreateDialog.value = false
      resetForm()
      fetchData()
    } catch {
      // handled by interceptor
    } finally {
      saving.value = false
    }
  })
}

async function handleDelete(item: SceneImage) {
  try {
    await ElMessageBox.confirm(
      `确定要删除场景图 "${item.name}" 吗？\n\n` +
      `• 将解除与 ${item.bound_products.length} 个产品的绑定关系\n` +
      `• 媒体库中的原始图片文件不会被删除\n` +
      `• 此操作不可撤销`,
      '确认删除场景图',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        distinguishCancelAndClose: true,
      }
    )
    await sceneImageApi.delete(item.id)
    ElMessage.success('场景图已删除，媒体库文件保留')
    selectedIds.value = selectedIds.value.filter((id) => id !== item.id)
    fetchData()
  } catch (err: unknown) {
    if (err instanceof Error && err.message !== 'cancel') {
      // handled by interceptor
    }
  }
}

function handleBindProducts(item: SceneImage) {
  bindingItem.value = item
  bindTab.value = 'bound'
  bindSearch.value = ''
  productSearchResults.value = []
  showBindDialog.value = true
}

async function searchProducts() {
  if (!bindSearch.value.trim()) {
    productSearchResults.value = []
    return
  }
  productSearchLoading.value = true
  try {
    const res: any = await productApi.list({ keyword: bindSearch.value, page: 1, size: 50 })
    const data = res.data?.data || res.data || res
    productSearchResults.value = data.list || data || []
  } catch {
    productSearchResults.value = []
  } finally {
    productSearchLoading.value = false
  }
}

function isProductBound(productId: string): boolean {
  if (!bindingItem.value) return false
  return bindingItem.value.bound_products.some((p) => p.id === productId)
}

async function selectProductForBind(productId: string) {
  if (!bindingItem.value) return
  if (isProductBound(productId)) {
    await confirmUnbind(productId)
    return
  }
  try {
    await sceneImageApi.bind(bindingItem.value.id, [productId])
    ElMessage.success('产品已绑定')
    const res: any = await sceneImageApi.get(bindingItem.value.id)
    bindingItem.value = res.data?.data || res.data
    searchProducts()
  } catch {
    // handled by interceptor
  }
}

async function confirmUnbind(productId: string) {
  if (!bindingItem.value) return
  try {
    await ElMessageBox.confirm('确定要解绑该产品吗？', '确认解绑', {
      confirmButtonText: '解绑',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await sceneImageApi.unbind(bindingItem.value.id, [productId])
    ElMessage.success('产品已解绑')
    const res: any = await sceneImageApi.get(bindingItem.value.id)
    bindingItem.value = res.data?.data || res.data
  } catch (err: unknown) {
    if (err instanceof Error && err.message !== 'cancel') {
      // handled by interceptor
    }
  }
}

// Batch bind
function searchBatchProducts() {
  if (!batchProductSearch.value.trim()) {
    batchProductSearchResults.value = []
    return
  }
  batchProductSearchLoading.value = true
  productApi.list({ keyword: batchProductSearch.value, page: 1, size: 50 })
    .then((res: any) => {
      const data = res.data?.data || res.data || res
      batchProductSearchResults.value = data.list || data || []
    })
    .catch(() => {
      batchProductSearchResults.value = []
    })
    .finally(() => {
      batchProductSearchLoading.value = false
    })
}

function toggleBatchProduct(p: any) {
  const idx = batchSelectedProductIds.value.indexOf(p.id)
  if (idx > -1) {
    batchSelectedProductIds.value.splice(idx, 1)
  } else {
    batchSelectedProductIds.value.push(p.id)
  }
}

async function confirmBatchBind() {
  if (selectedIds.value.length === 0 || batchSelectedProductIds.value.length === 0) return
  batchBinding.value = true
  try {
    await sceneImageApi.batchBind(selectedIds.value, batchSelectedProductIds.value)
    ElMessage.success(`已将 ${batchSelectedProductIds.value.length} 个产品绑定到 ${selectedIds.value.length} 张场景图`)
    showBatchBindDialog.value = false
    selectedIds.value = []
    batchSelectedProductIds.value = []
    batchProductSearch.value = ''
    batchProductSearchResults.value = []
    fetchData()
  } catch {
    // handled by interceptor
  } finally {
    batchBinding.value = false
  }
}

// Bindings drawer
function openBindingsDrawer(item: SceneImage) {
  drawerItem.value = item
  showBindingsDrawer.value = true
}

function handleCloseDrawer(done: () => void) {
  drawerItem.value = null
  done()
}

async function confirmUnbindFromDrawer(productId: string) {
  if (!drawerItem.value) return
  try {
    await ElMessageBox.confirm('确定要解绑该产品吗？', '确认解绑', {
      confirmButtonText: '解绑',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await sceneImageApi.unbind(drawerItem.value.id, [productId])
    ElMessage.success('产品已解绑')
    const res: any = await sceneImageApi.get(drawerItem.value.id)
    drawerItem.value = res.data?.data || res.data
    fetchData()
  } catch (err: unknown) {
    if (err instanceof Error && err.message !== 'cancel') {
      // handled by interceptor
    }
  }
}

function navigateToProduct(productId: string) {
  showBindingsDrawer.value = false
  showBindDialog.value = false
  router.push(`/products/${productId}`)
}

// Create form product search
async function searchProductsForCreate() {
  if (!createFormProductSearch.value.trim()) {
    productSearchResults.value = []
    return
  }
  productSearchLoading.value = true
  try {
    const res: any = await productApi.list({ keyword: createFormProductSearch.value, page: 1, size: 50 })
    const data = res.data?.data || res.data || res
    productSearchResults.value = data.list || data || []
  } catch {
    productSearchResults.value = []
  } finally {
    productSearchLoading.value = false
  }
}

function toggleFormProduct(p: any) {
  const idx = formProductIds.value.indexOf(p.id)
  if (idx > -1) {
    formProductIds.value.splice(idx, 1)
  } else {
    formProductIds.value.push(p.id)
  }
}

function handleMediaSelect(payload: MediaItem | MediaItem[]) {
  const items = Array.isArray(payload) ? payload : [payload]
  selectedMediaList.value = items
  form.attachment_id = items[0]?.id || ''
}

function clearMedia() {
  selectedMediaList.value = []
  form.attachment_id = ''
}

function resetForm() {
  form.name = ''
  form.attachment_id = ''
  form.sort = 0
  formProductIds.value = []
  selectedMediaList.value = []
  editingItem.value = null
  if (formRef.value) formRef.value.resetFields()
}

onMounted(fetchData)
</script>

<style scoped>
.scene-images-page {
  max-width: 1400px;
}

.si-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.si-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin: 0;
}

.si-subtitle {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  margin: 4px 0 0;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.si-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  background: #fff;
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-light);
  gap: 12px;
  flex-wrap: wrap;
}

.toolbar-left {
  display: flex;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.toolbar-right {
  display: flex;
  gap: 8px;
  align-items: center;
}

.si-search {
  width: 240px;
}

.si-filter {
  width: 160px;
}

/* Gallery Grid */
.si-gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
  min-height: 300px;
}

.gallery-card {
  background: #fff;
  border: 2px solid var(--el-border-color-light);
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.2s;
  cursor: pointer;
  position: relative;
}

.gallery-card:hover {
  border-color: var(--el-color-primary-light-3);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
}

.gallery-card.is-selected {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px var(--el-color-primary-light-7);
}

.card-select-checkbox {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 5;
}

.gallery-thumb {
  position: relative;
  aspect-ratio: 4/3;
  background: var(--el-fill-color-lighter);
  overflow: hidden;
}

.gallery-img {
  width: 100%;
  height: 100%;
}

.gallery-img :deep(img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s;
}

.gallery-thumb:hover .gallery-img :deep(img) {
  transform: scale(1.05);
}

.gallery-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  opacity: 0;
  transition: opacity 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.gallery-thumb:hover .gallery-overlay {
  opacity: 1;
}

.gallery-info {
  padding: 12px;
}

.gallery-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  margin: 0 0 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gallery-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.gallery-bindings {
  min-height: 24px;
}

.gallery-empty {
  grid-column: 1 / -1;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 300px;
}

/* List View */
.si-list {
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
}

.list-thumb {
  width: 64px;
  height: 64px;
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  background: var(--el-fill-color-lighter);
}

.list-thumb :deep(img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-lighter);
  color: var(--el-text-color-secondary);
}

.pagination-bar {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

/* Media Select */
.media-select-area {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.selected-media-preview-wrap {
  position: relative;
  cursor: pointer;
}

.selected-media-more {
  position: absolute;
  left: 8px;
  right: 8px;
  bottom: 8px;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(30, 50, 90, 0.72);
  color: #fff;
  font-size: 12px;
  text-align: center;
}

.selected-media-preview {
  width: 120px;
  height: 120px;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  background: var(--el-fill-color-lighter);
}

.selected-media-preview :deep(img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* Bind Dialog */
.bind-dialog-body {
  min-height: 200px;
}

.bind-info {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
}

.bind-thumb {
  width: 80px;
  height: 80px;
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
}

.bind-thumb :deep(img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.bind-meta {
  flex: 1;
}

.bind-name {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.bind-count {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.bound-product-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 350px;
  overflow-y: auto;
}

.bound-product-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}

.bound-actions {
  margin-left: auto;
  display: flex;
  gap: 4px;
}

.product-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
  border: 1px solid transparent;
}

.product-card:hover {
  background: var(--el-fill-color-light);
}

.product-card.is-bound {
  border-color: var(--el-color-success-light-5);
  background: var(--el-color-success-lighter);
}

.product-thumb {
  width: 36px;
  height: 36px;
  border-radius: 4px;
  overflow: hidden;
  flex-shrink: 0;
  background: var(--el-fill-color-lighter);
}

.product-thumb-img {
  width: 100%;
  height: 100%;
}

.product-thumb-img :deep(img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.product-no {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
  flex-shrink: 0;
  width: 90px;
}

.product-info {
  flex: 1;
  min-width: 0;
}

.product-name {
  font-size: 13px;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.add-bind-section {
  min-height: 200px;
}

.product-search-results {
  max-height: 320px;
  overflow-y: auto;
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.empty-tip {
  padding: 24px;
  text-align: center;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

/* Batch Bind */
.batch-bind-body {
  min-height: 200px;
}

.batch-bind-info {
  margin-bottom: 8px;
}

/* Drawer */
.drawer-body {
  padding: 0 4px;
}

.drawer-scene-info {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
  margin-bottom: 16px;
}

.drawer-scene-thumb {
  width: 100px;
  height: 100px;
  border-radius: 8px;
  overflow: hidden;
  flex-shrink: 0;
  background: var(--el-fill-color-lighter);
}

.drawer-scene-thumb :deep(img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.drawer-scene-meta {
  flex: 1;
}

.drawer-scene-name {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.drawer-scene-count {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.drawer-product-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: calc(100vh - 280px);
  overflow-y: auto;
}

.drawer-product-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}

.drawer-product-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.drawer-product-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}
</style>
