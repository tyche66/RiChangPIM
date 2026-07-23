<template>
  <div class="media-library">
    <!-- Header -->
    <div class="ml-header">
      <div>
        <h2 class="ml-title">
          媒体库
        </h2>
        <p class="ml-subtitle">
          管理系统中的图片、PDF 和文件资源
        </p>
      </div>
      <div class="header-actions">
        <el-button
          type="primary"
          :icon="Upload"
          @click="showUpload = true"
        >
          上传文件
        </el-button>
      </div>
    </div>

    <!-- Upload Dialog -->
    <el-dialog
      v-model="showUpload"
      title="上传文件"
      width="600px"
      append-to-body
      lock-scroll
      destroy-on-close
    >
      <MediaUploader @uploaded="handleUploaded" />
    </el-dialog>

    <!-- Toolbar -->
    <div class="ml-toolbar">
      <div class="toolbar-left">
        <el-input
          v-model="searchQuery"
          placeholder="搜索文件名..."
          clearable
          :prefix-icon="Search"
          class="ml-search"
        />
        <el-select
          v-model="typeFilter"
          placeholder="文件类型"
          clearable
          class="ml-filter"
        >
          <el-option
            label="全部类型"
            value=""
          />
          <el-option
            label="图片"
            value="image"
          />
          <el-option
            label="PDF"
            value="pdf"
          />
          <el-option
            label="其他"
            value="other"
          />
        </el-select>
        <el-select
          v-model="refFilter"
          placeholder="引用状态"
          clearable
          class="ml-filter"
        >
          <el-option
            label="全部"
            value=""
          />
          <el-option
            label="已引用"
            value="referenced"
          />
          <el-option
            label="未引用"
            value="unreferenced"
          />
        </el-select>
      </div>
      <div class="toolbar-right">
        <div class="selection-summary">
          已选 {{ selectedFileIds.length }} 项
        </div>
        <el-button
          v-if="selectedFileIds.length > 0 && hasPermission(['media:delete'])"
          type="danger"
          :icon="Delete"
          @click="handleBatchDelete"
        >
          批量删除
        </el-button>
        <el-select
          v-model="sortBy"
          class="ml-filter ml-sort"
        >
          <el-option
            label="最新上传"
            value="newest"
          />
          <el-option
            label="文件名 A-Z"
            value="nameAsc"
          />
          <el-option
            label="文件名 Z-A"
            value="nameDesc"
          />
          <el-option
            label="文件大小"
            value="size"
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
      class="ml-gallery"
    >
      <div
        v-for="item in filteredItems"
        :key="item.id"
        class="gallery-card"
        :class="{ 'is-selected': selectedFileIds.includes(item.id) }"
        @click="openDetail(item)"
        @dblclick="openPreview(item)"
      >
        <div class="gallery-thumb">
          <img
            v-if="item.type === 'image'"
            :src="item.thumbnailUrl || item.url"
            :alt="item.name"
            loading="lazy"
            class="gallery-image"
          >
          <div
            v-else
            class="pdf-card"
          >
            <el-icon
              :size="40"
              color="#e74c3c"
            >
              <Document />
            </el-icon>
            <span class="pdf-label">PDF</span>
          </div>
          <div class="gallery-overlay">
            <div class="overlay-actions">
              <el-button
                circle
                size="small"
                :title="selectedFileIds.includes(item.id) ? '取消选择' : '选择'"
                @click.stop="toggleFileSelection(item)"
              >
                <el-icon><Check /></el-icon>
              </el-button>
              <el-button
                circle
                size="small"
                title="预览"
                @click.stop="openPreview(item)"
              >
                <el-icon><ZoomIn /></el-icon>
              </el-button>
              <el-button
                circle
                size="small"
                title="详情"
                @click.stop="openDetail(item)"
              >
                <el-icon><InfoFilled /></el-icon>
              </el-button>
              <el-button
                v-if="hasPermission(['media:edit', 'media:replace'])"
                circle
                size="small"
                title="替换"
                @click.stop="handleReplace(item)"
              >
                <el-icon><Refresh /></el-icon>
              </el-button>
              <el-button
                v-if="hasPermission(['media:delete'])"
                circle
                size="small"
                type="danger"
                title="删除"
                @click.stop="handleDelete(item)"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>
        </div>
        <div class="gallery-info">
          <p
            class="gallery-name"
            :title="item.name"
          >
            {{ item.name }}
          </p>
          <div class="gallery-meta">
            <el-tag
              :type="item.type === 'image' ? 'success' : item.type === 'pdf' ? 'warning' : 'info'"
              size="small"
              round
            >
              {{ typeLabel(item.type) }}
            </el-tag>
            <span class="gallery-size">{{ formatSize(item.size) }}</span>
          </div>
          <div class="gallery-ref">
            <el-tag
              :type="item.refCount > 0 ? 'warning' : 'info'"
              size="small"
              effect="plain"
              round
            >
              <el-icon><Link /></el-icon>
              {{ item.refCount > 0 ? `已引用 (${item.refCount})` : '未引用' }}
            </el-tag>
          </div>
        </div>
      </div>
      <div
        v-if="filteredItems.length === 0 && !loading"
        class="gallery-empty"
      >
        <el-empty description="媒体库为空">
          <el-button
            type="primary"
            @click="showUpload = true"
          >
            上传文件
          </el-button>
        </el-empty>
      </div>
    </div>

    <!-- List View -->
    <div
      v-else
      v-loading="loading"
      class="ml-list"
    >
      <el-table
        :data="filteredItems"
        stripe
        style="width: 100%"
        @row-dblclick="openPreview"
        @selection-change="handleSelectionChange"
      >
        <el-table-column
          type="selection"
          width="42"
        />
        <el-table-column
          label="预览"
          width="80"
          align="center"
        >
          <template #default="{ row }">
            <div
              class="list-thumb"
              :class="{ 'checkerboard': row.type === 'image' }"
            >
              <img
                v-if="row.type === 'image'"
                :src="row.thumbnailUrl || row.url"
              >
              <el-icon
                v-else
                :size="28"
                color="#e74c3c"
              >
                <Document />
              </el-icon>
            </div>
          </template>
        </el-table-column>
        <el-table-column
          label="文件名"
          min-width="200"
        >
          <template #default="{ row }">
            <span
              class="list-name"
              :title="row.name"
            >{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column
          label="类型"
          width="100"
        >
          <template #default="{ row }">
            <el-tag
              :type="row.type === 'image' ? 'success' : row.type === 'pdf' ? 'warning' : 'info'"
              size="small"
              round
            >
              {{ typeLabel(row.type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          label="大小"
          width="100"
        >
          <template #default="{ row }">
            {{ formatSize(row.size) }}
          </template>
        </el-table-column>
        <el-table-column
          label="上传时间"
          width="120"
        >
          <template #default="{ row }">
            {{ formatDate(row.uploadedAt) }}
          </template>
        </el-table-column>
        <el-table-column
          label="引用状态"
          width="120"
        >
          <template #default="{ row }">
            <el-tag
              :type="row.refCount > 0 ? 'warning' : 'info'"
              size="small"
              effect="plain"
              round
            >
              {{ row.refCount > 0 ? `已引用 (${row.refCount})` : '未引用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
          width="180"
          align="center"
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
              @click="openDetail(row)"
            >
              详情
            </el-button>
            <el-button
              v-if="hasPermission(['media:edit', 'media:replace'])"
              text
              size="small"
              @click="handleReplace(row)"
            >
              替换
            </el-button>
            <el-button
              v-if="hasPermission(['media:delete'])"
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

    <!-- File Detail Drawer -->
    <el-drawer
      v-model="detailVisible"
      :title="detailItem?.name"
      size="480px"
      direction="rtl"
      append-to-body
      lock-scroll
      destroy-on-close
      class="detail-drawer"
    >
      <div
        v-if="detailItem"
        class="detail-body"
      >
        <!-- Preview Area -->
        <div
          class="detail-preview"
          :class="{ 'checkerboard': detailItem.type === 'image' }"
        >
          <img
            v-if="detailItem.type === 'image'"
            :src="detailItem.url"
            :alt="detailItem.name"
            class="detail-image"
          >
          <div
            v-else
            class="detail-pdf-preview"
          >
            <el-icon
              :size="64"
              color="#e74c3c"
            >
              <Document />
            </el-icon>
            <p>{{ detailItem.name }}</p>
            <el-button
              type="primary"
              @click="openPdfUrl(detailItem.url)"
            >
              打开 PDF
              <el-icon class="ml-1">
                <TopRight />
              </el-icon>
            </el-button>
          </div>
        </div>

        <!-- File Info -->
        <div class="detail-section">
          <h4 class="section-title">
            文件信息
          </h4>
          <el-descriptions
            :column="1"
            size="small"
          >
            <el-descriptions-item label="文件名">
              {{ detailItem.name }}
            </el-descriptions-item>
            <el-descriptions-item label="类型">
              {{ typeLabel(detailItem.type) }} ({{ detailItem.mimeType }})
            </el-descriptions-item>
            <el-descriptions-item label="大小">
              {{ formatSize(detailItem.size) }}
            </el-descriptions-item>
            <el-descriptions-item label="上传时间">
              {{ detailItem.uploadedAt }}
            </el-descriptions-item>
            <el-descriptions-item label="文件 ID">
              {{ detailItem.id }}
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- Reference Relationships -->
        <div class="detail-section">
          <h4 class="section-title">
            <el-icon><Link /></el-icon>
            引用关系 ({{ detailItem.refCount }})
          </h4>
          <div
            v-if="detailItem.refCount === 0"
            class="no-refs"
          >
            <el-empty
              description="该文件未被任何资源引用"
              :image-size="60"
            />
          </div>
          <div v-else>
            <!-- Product Cover Images -->
            <div
              v-if="bindings.coverImages.length > 0"
              class="ref-group"
            >
              <h5 class="ref-group-title">
                产品主图引用
              </h5>
              <div
                v-for="binding in bindings.coverImages"
                :key="binding.product_id"
                class="ref-item"
                @click="goToProduct(binding.product_id)"
              >
                <div
                  v-if="binding.cover_image_url"
                  class="ref-thumb"
                >
                  <img :src="binding.cover_image_url">
                </div>
                <div class="ref-info">
                  <p class="ref-product-no">
                    {{ binding.product_no }}
                  </p>
                  <p class="ref-product-name">
                    {{ binding.product_name }}
                  </p>
                </div>
                <el-icon class="ref-arrow">
                  <ArrowRight />
                </el-icon>
              </div>
            </div>
            <!-- Scene Images -->
            <div
              v-if="bindings.sceneImages.length > 0"
              class="ref-group"
            >
              <h5 class="ref-group-title">
                场景图引用
              </h5>
              <div
                v-for="binding in bindings.sceneImages"
                :key="binding.scene_id + '_' + binding.product_id"
                class="ref-item"
                @click="goToProduct(binding.product_id)"
              >
                <div
                  v-if="binding.scene_image_url"
                  class="ref-thumb"
                >
                  <img :src="binding.scene_image_url">
                </div>
                <div class="ref-info">
                  <p class="ref-product-no">
                    {{ binding.product_no }}
                  </p>
                  <p class="ref-product-name">
                    {{ binding.product_name }}
                  </p>
                  <p
                    v-if="binding.scene_name"
                    class="ref-scene-name"
                  >
                    场景: {{ binding.scene_name }}
                  </p>
                </div>
                <el-icon class="ref-arrow">
                  <ArrowRight />
                </el-icon>
              </div>
            </div>
            <!-- Manuals / PDFs -->
            <div
              v-if="bindings.manuals.length > 0"
              class="ref-group"
            >
              <h5 class="ref-group-title">
                产品说明书/PDF引用
              </h5>
              <div
                v-for="binding in bindings.manuals"
                :key="binding.product_id"
                class="ref-item"
                @click="goToProduct(binding.product_id)"
              >
                <div class="ref-thumb">
                  <el-icon
                    :size="24"
                    color="#e74c3c"
                  >
                    <Document />
                  </el-icon>
                </div>
                <div class="ref-info">
                  <p class="ref-product-no">
                    {{ binding.product_no }}
                  </p>
                  <p class="ref-product-name">
                    {{ binding.product_name }}
                  </p>
                </div>
                <el-icon class="ref-arrow">
                  <ArrowRight />
                </el-icon>
              </div>
            </div>
          </div>
        </div>

        <!-- Action Buttons -->
        <div class="detail-actions">
          <el-button
            v-if="detailItem.refCount === 0 && hasPermission(['media:delete'])"
            type="danger"
            :icon="Delete"
            @click="handleDelete(detailItem)"
          >
            删除文件
          </el-button>
          <el-button
            v-if="hasPermission(['media:edit', 'media:replace'])"
            type="primary"
            :icon="Refresh"
            @click="handleReplace(detailItem)"
          >
            替换文件
          </el-button>
        </div>
      </div>
    </el-drawer>

    <!-- Preview Dialog (large image) -->
    <el-dialog
      v-model="previewVisible"
      :title="previewItem?.name"
      width="90%"
      top="2vh"
      append-to-body
      lock-scroll
      destroy-on-close
      class="preview-dialog"
    >
      <div
        class="preview-container"
        :class="{ 'checkerboard': previewItem?.type === 'image' }"
      >
        <img
          v-if="previewItem?.type === 'image'"
          :src="previewItem.url"
          :alt="previewItem.name"
          class="preview-full-image"
        >
        <div
          v-else
          class="preview-pdf-container"
        >
          <el-icon
            :size="80"
            color="#e74c3c"
          >
            <Document />
          </el-icon>
          <p>{{ previewItem?.name }}</p>
          <el-button
            type="primary"
            @click="openPdfUrl(previewItem?.url)"
          >
            在新窗口打开 PDF
            <el-icon class="ml-1">
              <TopRight />
            </el-icon>
          </el-button>
        </div>
      </div>
    </el-dialog>

    <!-- Replace Dialog -->
    <el-dialog
      v-model="replaceVisible"
      title="替换文件"
      width="480px"
      append-to-body
      lock-scroll
      destroy-on-close
    >
      <div
        v-if="replaceTarget"
        class="replace-body"
      >
        <p class="replace-hint">
          正在替换: <strong>{{ replaceTarget.name }}</strong>
        </p>
        <el-alert
          :title="`仅可替换为${replaceTarget.type === 'image' ? '图片' : 'PDF'}文件，替换后所有引用自动更新。`"
          type="warning"
          :closable="false"
          show-icon
          class="mb-3"
        />
        <el-upload
          ref="replaceUploadRef"
          drag
          :auto-upload="false"
          :accept="replaceTarget.type === 'image' ? 'image/*' : '.pdf'"
          :limit="1"
          :on-change="onReplaceFile"
        >
          <el-icon
            class="upload-icon"
            :size="32"
          >
            <UploadFilled />
          </el-icon>
          <div class="el-upload__text">
            点击选择文件或拖拽到此处
            <br>
            <span class="upload-hint">仅支持 {{ replaceTarget.type === 'image' ? '图片 (JPG/PNG/WebP)' : 'PDF' }} 文件</span>
          </div>
        </el-upload>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Upload, Search, Grid, List, Document, ZoomIn, Refresh, Delete, Check,
  TopRight, UploadFilled, Link, InfoFilled, ArrowRight,
} from '@element-plus/icons-vue'
import type { UploadFile } from 'element-plus'
import MediaUploader from '@/components/MediaUploader.vue'
import { mediaApi, formatSize, formatDate } from '@/api/media'
import type { MediaItem } from '@/api/media'
import { useAuthStore } from '@/stores/auth'

interface ExtendedMediaItem extends MediaItem {
  refCount: number
  productBindings?: Array<{
    id: string
    product_no: string
    product_name: string
    cover_image_url?: string
  }>
}

interface CoverImageBinding {
  product_id: string
  product_no: string
  product_name: string
  cover_image_url?: string
}

interface SceneImageBinding {
  scene_id: string
  product_id: string
  product_no: string
  product_name: string
  scene_image_url?: string
  scene_name?: string
}

interface ManualBinding {
  product_id: string
  product_no: string
  product_name: string
}

interface Bindings {
  coverImages: CoverImageBinding[]
  sceneImages: SceneImageBinding[]
  manuals: ManualBinding[]
}

const router = useRouter()
const authStore = useAuthStore()

const showUpload = ref(false)
const loading = ref(false)
const rawItems = ref<ExtendedMediaItem[]>([])
const searchQuery = ref('')
const typeFilter = ref('')
const refFilter = ref('')
const sortBy = ref('newest')
const viewMode = ref<'grid' | 'list'>('grid')

const detailVisible = ref(false)
const detailItem = ref<ExtendedMediaItem | null>(null)
const bindings = ref<Bindings>({ coverImages: [], sceneImages: [], manuals: [] })
const selectedFileIds = ref<string[]>([])

const previewVisible = ref(false)
const previewItem = ref<ExtendedMediaItem | null>(null)

const replaceVisible = ref(false)
const replaceTarget = ref<ExtendedMediaItem | null>(null)
const replaceUploadRef = ref()

function hasPermission(perms: string[]): boolean {
  return perms.some(p => authStore.permissions.includes(p))
}

function typeLabel(type: string): string {
  const map: Record<string, string> = { image: '图片', pdf: 'PDF', other: '其他' }
  return map[type] || type.toUpperCase()
}

// Filtered and sorted items
const filteredItems = computed(() => {
  let items = [...rawItems.value]

  // Search filter
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    items = items.filter(i => i.name.toLowerCase().includes(q))
  }

  // Type filter
  if (typeFilter.value) {
    items = items.filter(i => i.type === typeFilter.value)
  }

  // Reference filter
  if (refFilter.value === 'referenced') {
    items = items.filter(i => i.refCount > 0)
  } else if (refFilter.value === 'unreferenced') {
    items = items.filter(i => i.refCount === 0)
  }

  // Sort
  switch (sortBy.value) {
    case 'newest':
      items.sort((a, b) => new Date(b.uploadedAt).getTime() - new Date(a.uploadedAt).getTime())
      break
    case 'nameAsc':
      items.sort((a, b) => a.name.localeCompare(b.name))
      break
    case 'nameDesc':
      items.sort((a, b) => b.name.localeCompare(a.name))
      break
    case 'size':
      items.sort((a, b) => b.size - a.size)
      break
  }

  return items
})

async function fetchData() {
  loading.value = true
  try {
    const typeParam = typeFilter.value || undefined
    const list = await mediaApi.list({ search: searchQuery.value, type: typeParam })

    rawItems.value = list.map(item => ({ ...item, refCount: item.refCount || 0 }))
  } catch {
    ElMessage.error('加载数据失败')
  } finally {
    loading.value = false
  }
}

watch([searchQuery, typeFilter, refFilter, sortBy], () => {
  fetchData()
})

fetchData()

function handleUploaded() {
  fetchData()
}

function toggleFileSelection(item: ExtendedMediaItem) {
  const idx = selectedFileIds.value.indexOf(item.id)
  if (idx >= 0) selectedFileIds.value.splice(idx, 1)
  else selectedFileIds.value.push(item.id)
}

function handleSelectionChange(selection: ExtendedMediaItem[]) {
  selectedFileIds.value = selection.map((item) => item.id)
}

function openPreview(item: ExtendedMediaItem) {
  previewItem.value = item
  previewVisible.value = true
}

async function openDetail(item: ExtendedMediaItem) {
  detailItem.value = item
  detailVisible.value = true

  // Fetch binding details
  bindings.value = { coverImages: [], sceneImages: [], manuals: [] }

  try {
    const detail = await mediaApi.get(item.id, true)
    detailItem.value = { ...item, ...detail, refCount: detail.refCount || 0 }
    const refs = detail.references
    bindings.value.coverImages = (refs?.product_images || []).map(ref => ({
      product_id: ref.product_id,
      product_no: ref.product_no,
      product_name: ref.product_name,
    }))
    bindings.value.sceneImages = (refs?.scene_images || []).flatMap(ref =>
      ref.bound_products.map(product => ({
        scene_id: ref.scene_image_id,
        scene_name: ref.scene_image_name,
        product_id: product.product_id,
        product_no: product.product_no,
        product_name: product.product_name,
        scene_image_url: item.url,
      }))
    )
    bindings.value.manuals = (refs?.manuals || []).map(ref => ({
      product_id: ref.product_id,
      product_no: ref.product_no,
      product_name: ref.product_name,
    }))
  } catch (err) {
    console.error('[MediaLibrary] Failed to load references:', err)
  }
}

function goToProduct(productId: string) {
  router.push(`/products/${productId}`)
}

function openPdfUrl(url?: string) {
  if (url) window.open(url, '_blank')
}

function handleReplace(item: ExtendedMediaItem) {
  replaceTarget.value = item
  replaceVisible.value = true
}

async function onReplaceFile(uploadFile: UploadFile) {
  const file = uploadFile.raw
  if (!file || !replaceTarget.value) return

  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error('文件超过 50MB 限制')
    return
  }

  // Type validation
  const targetType = replaceTarget.value.type
  if (targetType === 'image' && !file.type.startsWith('image/')) {
    ElMessage.error('图片文件只能替换为图片')
    return
  }
  if (targetType === 'pdf' && file.type !== 'application/pdf') {
    ElMessage.error('PDF 文件只能替换为 PDF')
    return
  }

  try {
    await mediaApi.replace(replaceTarget.value.id, file)
    ElMessage.success('文件替换成功，所有引用已自动更新')
    replaceVisible.value = false
    replaceTarget.value = null
    fetchData()
    if (detailVisible.value && replaceTarget.value) {
      openDetail(replaceTarget.value)
    }
  } catch (err: unknown) {
    ElMessage.error(err instanceof Error ? err.message : '替换失败')
  }
}

async function handleDelete(item: ExtendedMediaItem) {
  if (item.refCount > 0) {
    try {
      await ElMessageBox.confirm(
        `该文件已被 ${item.refCount} 处引用，删除可能影响相关产品。确定要删除 "${item.name}" 吗？`,
        '确认删除',
        { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
      )
    } catch {
      return
    }
  } else {
    try {
      await ElMessageBox.confirm(
        `确定要删除 "${item.name}" 吗？此操作不可撤销。`,
        '确认删除',
        { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
      )
    } catch {
      return
    }
  }

  try {
    await mediaApi.delete(item.id)
    ElMessage.success('删除成功')
    detailVisible.value = false
    fetchData()
  } catch (err: unknown) {
    if (err instanceof Error) {
      ElMessage.error(err.message || '删除失败')
    }
  }
}

async function handleBatchDelete() {
  const targets = rawItems.value.filter((item) => selectedFileIds.value.includes(item.id))
  if (targets.length === 0) return

  try {
    await ElMessageBox.confirm(`确定删除选中的 ${targets.length} 个文件吗？`, '确认批量删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }

  const successes: string[] = []
  const failures: string[] = []
  for (const item of targets) {
    try {
      await mediaApi.delete(item.id, { suppressErrorMessage: true })
      successes.push(item.name)
    } catch {
      failures.push(item.name)
    }
  }

  if (successes.length > 0) {
    ElMessage.success(`已删除 ${successes.length} 个文件`)
  }
  if (failures.length > 0) {
    ElMessage.error(`删除失败 ${failures.length} 个文件`)
  }

  selectedFileIds.value = []
  detailVisible.value = false
  await fetchData()
}
</script>

<style scoped>
/* ===== CSS Variables for checkerboard pattern ===== */
.checkerboard {
  background-image:
    linear-gradient(45deg, #e0e0e0 25%, transparent 25%),
    linear-gradient(-45deg, #e0e0e0 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, #e0e0e0 75%),
    linear-gradient(-45deg, transparent 75%, #e0e0e0 75%);
  background-size: 16px 16px;
  background-position: 0 0, 0 8px, 8px -8px, -8px 0px;
}

.media-library {
  max-width: 1440px;
  margin: 0 auto;
}

/* Header */
.ml-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
  gap: 16px;
}

.ml-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin: 0;
  line-height: 1.3;
}

.ml-subtitle {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  margin: 4px 0 0;
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* Toolbar */
.ml-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fff;
  border-radius: 12px;
  border: 1px solid var(--el-border-color-light);
}

.toolbar-left {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.toolbar-right {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.selection-summary {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  white-space: nowrap;
}

.ml-search {
  width: 220px;
}

.ml-filter {
  width: 130px;
}

.ml-sort {
  width: 130px;
}

/* Gallery Grid */
.ml-gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
  min-height: 300px;
}

.gallery-card {
  background: #fff;
  border: 2px solid var(--el-border-color-light);
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.25s ease;
  display: flex;
  flex-direction: column;
}

.gallery-card.is-selected {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px var(--el-color-primary-light-7);
}

.gallery-card:hover {
  border-color: var(--el-color-primary-light-3);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

.gallery-thumb {
  position: relative;
  aspect-ratio: 4/3;
  background: var(--el-fill-color-lighter);
  overflow: hidden;
}

.gallery-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s;
}

.gallery-card:hover .gallery-image {
  transform: scale(1.05);
}

.pdf-card {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: #fafafa;
}

.pdf-label {
  font-size: 13px;
  font-weight: 600;
  color: #e74c3c;
}

.gallery-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  opacity: 0;
  transition: opacity 0.25s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.gallery-card:hover .gallery-overlay {
  opacity: 1;
}

.overlay-actions {
  display: flex;
  gap: 8px;
}

.gallery-info {
  padding: 10px 12px;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gallery-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gallery-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.gallery-size {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.gallery-ref {
  margin-top: auto;
}

.gallery-empty {
  grid-column: 1 / -1;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 300px;
}

/* List View */
.ml-list {
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
}

.list-thumb {
  width: 48px;
  height: 48px;
  border-radius: 6px;
  overflow: hidden;
  background: var(--el-fill-color-lighter);
  display: flex;
  align-items: center;
  justify-content: center;
}

.list-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.list-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Detail Drawer */
.detail-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding-bottom: 20px;
}

.detail-preview {
  width: 100%;
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 240px;
  max-height: 400px;
  background: var(--el-fill-color-lighter);
}

.detail-image {
  max-width: 100%;
  max-height: 400px;
  object-fit: contain;
}

.detail-pdf-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 24px;
  color: var(--el-text-color-secondary);
}

.detail-section {
  background: var(--el-fill-color-lighter);
  border-radius: 12px;
  padding: 16px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin: 0 0 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.no-refs {
  display: flex;
  justify-content: center;
  padding: 16px 0;
}

.ref-group {
  margin-bottom: 16px;
}

.ref-group:last-child {
  margin-bottom: 0;
}

.ref-group-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-regular);
  margin: 0 0 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--el-border-color-light);
}

.ref-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  background: #fff;
  border-radius: 8px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.ref-item:hover {
  background: var(--el-color-primary-light-9);
}

.ref-thumb {
  width: 40px;
  height: 40px;
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-lighter);
}

.ref-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.ref-info {
  flex: 1;
  min-width: 0;
}

.ref-product-no {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
  margin: 0;
}

.ref-product-name {
  font-size: 13px;
  color: var(--el-text-color-primary);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ref-scene-name {
  font-size: 11px;
  color: var(--el-color-primary);
  margin: 2px 0 0;
}

.ref-arrow {
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}

.detail-actions {
  display: flex;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-light);
}

/* Preview Dialog */
.preview-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  border-radius: 12px;
  overflow: hidden;
  background: var(--el-fill-color-lighter);
}

.preview-full-image {
  max-width: 100%;
  max-height: 75vh;
  object-fit: contain;
}

.preview-pdf-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  color: var(--el-text-color-secondary);
  padding: 40px;
}

/* Replace Dialog */
.replace-body {
  padding: 4px 0;
}

.replace-hint {
  font-size: 14px;
  color: var(--el-text-color-primary);
  margin-bottom: 12px;
}

.mb-3 {
  margin-bottom: 12px;
}

.upload-icon {
  margin-bottom: 8px;
  color: var(--el-color-primary);
}

.upload-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.ml-1 {
  margin-left: 4px;
}

/* Mobile Responsive */
@media (max-width: 768px) {
  .ml-header {
    flex-direction: column;
    align-items: stretch;
  }

  .header-actions {
    justify-content: flex-end;
  }

  .ml-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .toolbar-left,
  .toolbar-right {
    justify-content: stretch;
  }

  .ml-search,
  .ml-filter,
  .ml-sort {
    width: 100%;
  }

  .ml-gallery {
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 10px;
  }

  .el-drawer {
    width: 100% !important;
    max-width: 100vw;
  }
}
</style>
