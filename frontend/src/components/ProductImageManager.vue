<template>
  <div class="product-image-manager">
    <div class="image-section-header">
      <h4 class="section-title">
        产品图片
      </h4>
      <span class="image-count">{{ images.length }}/10</span>
      <el-button
        size="small"
        class="capsule-btn btn-sm"
        :disabled="images.length >= 10"
        @click="showAddDialog = true"
      >
        + 添加图片
      </el-button>
    </div>
    <p class="section-hint">
      解绑不会删除媒体库文件，仅移除与当前产品的关联
    </p>

    <div
      v-if="images.length === 0"
      class="empty-state"
    >
      <el-empty
        description="暂无产品图片"
        :image-size="80"
      />
    </div>

    <div
      v-else
      class="image-grid"
    >
      <div
        v-for="(img, index) in images"
        :key="img.imageId"
        class="image-card"
      >
        <div class="image-card-inner">
          <el-image
            :src="img.thumbnailUrl || img.url"
            fit="contain"
            class="product-thumb-img"
            @click="previewImg = img.url"
          >
            <template #error>
              <div class="thumb-error">
                <el-icon :size="24">
                  <Picture />
                </el-icon>
              </div>
            </template>
          </el-image>
          <div
            v-if="img.isPrimary"
            class="primary-badge"
          >
            主图
          </div>
          <div class="image-actions">
            <el-tooltip
              content="设为主图"
              placement="top"
            >
              <el-button
                :icon="StarFilled"
                size="small"
                circle
                :type="img.isPrimary ? 'warning' : 'default'"
                :disabled="img.isPrimary"
                @click="setPrimary(img.imageId)"
              />
            </el-tooltip>
            <el-tooltip
              content="上移"
              placement="top"
            >
              <el-button
                :icon="ArrowUp"
                size="small"
                circle
                :disabled="index === 0"
                @click="moveUp(index)"
              />
            </el-tooltip>
            <el-tooltip
              content="下移"
              placement="top"
            >
              <el-button
                :icon="ArrowDown"
                size="small"
                circle
                :disabled="index === images.length - 1"
                @click="moveDown(index)"
              />
            </el-tooltip>
            <el-tooltip
              content="解绑"
              placement="top"
            >
              <el-button
                :icon="Remove"
                size="small"
                circle
                type="danger"
                @click="unbind(img.imageId)"
              />
            </el-tooltip>
          </div>
        </div>
      </div>
    </div>

    <!-- Add dialog -->
    <el-dialog
      v-model="showAddDialog"
      title="添加产品图片"
      class="glass-dialog add-image-dialog"
      append-to-body
      lock-scroll
      destroy-on-close
    >
      <div class="dialog-scroll-body">
        <el-tabs
          v-model="addTab"
          class="add-tabs"
        >
          <el-tab-pane
            label="上传图片"
            name="upload"
          >
            <MediaUploader @uploaded="handleUploaded" />
          </el-tab-pane>
          <el-tab-pane
            label="从媒体库选择"
            name="picker"
          >
            <div class="picker-section">
              <el-button
                type="primary"
                class="capsule-btn"
                @click="showMediaPicker = true"
              >
                打开媒体库
              </el-button>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-dialog>

    <MediaPicker
      v-model="showMediaPicker"
      @select="handlePickerSelect"
    />

    <!-- Image preview -->
    <el-image-viewer
      v-if="previewImg"
      :url-list="[previewImg]"
      @close="previewImg = ''"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { StarFilled, ArrowUp, ArrowDown, Remove, Picture } from '@element-plus/icons-vue'
import { productApi } from '@/api'
import MediaUploader from './MediaUploader.vue'
import MediaPicker from './MediaPicker.vue'
import type { MediaItem } from '@/api/media'

export interface ProductBindImage {
  imageId: string
  attachmentId?: string
  url: string
  thumbnailUrl?: string
  name: string
  sortOrder: number
  isPrimary: boolean
}

const props = defineProps<{
  productId: string
  images: ProductBindImage[]
}>()

const emit = defineEmits<{
  change: [images: ProductBindImage[]]
}>()

const localImages = ref<ProductBindImage[]>([...props.images])

watch(() => props.images, (val) => {
  localImages.value = [...val]
}, { deep: true })

const showAddDialog = ref(false)
const addTab = ref('upload')
const showMediaPicker = ref(false)
const previewImg = ref('')

const MAX_IMAGES = 10

function syncImages() {
  emit('change', [...localImages.value])
}

async function setPrimary(imageId: string) {
  try {
    await productApi.setCoverImage(props.productId, imageId)
    localImages.value = localImages.value.map((img) => ({
      ...img,
      isPrimary: img.imageId === imageId,
    }))
    syncImages()
    ElMessage.success('主图设置成功')
  } catch {
    // handled by interceptor
  }
}

async function moveUp(index: number) {
  if (index <= 0) return
  const arr = [...localImages.value]
  ;[arr[index - 1], arr[index]] = [arr[index], arr[index - 1]]
  arr.forEach((img, i) => (img.sortOrder = i))
  localImages.value = arr
  syncImages()
  try {
    await productApi.reorderProductImages(props.productId, {
      items: arr.map((img, i) => ({ image_id: img.imageId, sort: i })),
    })
  } catch {
    // handled by interceptor
  }
}

async function moveDown(index: number) {
  if (index >= localImages.value.length - 1) return
  const arr = [...localImages.value]
  ;[arr[index], arr[index + 1]] = [arr[index + 1], arr[index]]
  arr.forEach((img, i) => (img.sortOrder = i))
  localImages.value = arr
  syncImages()
  try {
    await productApi.reorderProductImages(props.productId, {
      items: arr.map((img, i) => ({ image_id: img.imageId, sort: i })),
    })
  } catch {
    // handled by interceptor
  }
}

async function unbind(imageId: string) {
  try {
    await productApi.unbindProductImage(props.productId, imageId)
    localImages.value = localImages.value.filter((img) => img.imageId !== imageId)
    syncImages()
    ElMessage.success('图片已解绑')
  } catch {
    // handled by interceptor
  }
}

async function handleUploaded(item: MediaItem) {
  if (localImages.value.length >= MAX_IMAGES) {
    ElMessage.warning(`产品图片最多 ${MAX_IMAGES} 张`)
    return
  }
  try {
    const res: any = await productApi.bindProductImages(props.productId, { attachment_ids: [item.id] })
    const created = res?.data?.added?.[0]
    if (!created?.id) throw new Error('产品图片关联创建失败')
    const newImg: ProductBindImage = {
      imageId: created.id,
      attachmentId: item.id,
      url: created.url || item.url,
      thumbnailUrl: created.thumbnail_url || item.thumbnailUrl,
      name: created.name || item.name,
      sortOrder: localImages.value.length,
      isPrimary: localImages.value.length === 0,
    }
    localImages.value.push(newImg)
    if (localImages.value.length === 1) {
      await setPrimary(newImg.imageId)
    }
    syncImages()
    ElMessage.success('图片已添加')
  } catch {
    // handled by interceptor
  }
}

async function handlePickerSelect(payload: MediaItem | MediaItem[]) {
  const item = Array.isArray(payload) ? payload[0] : payload
  if (!item) return
  if (localImages.value.length >= MAX_IMAGES) {
    ElMessage.warning(`产品图片最多 ${MAX_IMAGES} 张`)
    return
  }
  try {
    const res: any = await productApi.bindProductImages(props.productId, { attachment_ids: [item.id] })
    const created = res?.data?.added?.[0]
    if (!created?.id) throw new Error('产品图片关联创建失败')
    const newImg: ProductBindImage = {
      imageId: created.id,
      attachmentId: item.id,
      url: created.url || item.url,
      thumbnailUrl: created.thumbnail_url || item.thumbnailUrl,
      name: created.name || item.name,
      sortOrder: localImages.value.length,
      isPrimary: localImages.value.length === 0,
    }
    localImages.value.push(newImg)
    if (localImages.value.length === 1) {
      await setPrimary(newImg.imageId)
    }
    syncImages()
    ElMessage.success('图片已添加')
    showAddDialog.value = false
  } catch {
    // handled by interceptor
  }
}
</script>

<style scoped>
.product-image-manager {
  margin-top: 24px;
  padding: 20px;
  background: var(--brand-lighter);
  border-radius: var(--radius-md);
}

.image-section-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.section-title {
  margin: 0;
  color: var(--brand-deep);
  font-size: 15px;
  font-weight: 600;
}

.image-count {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

.empty-state {
  min-height: 100px;
  display: flex;
  justify-content: center;
  align-items: center;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
}

.image-card {
  aspect-ratio: 1;
  border-radius: 12px;
  overflow: hidden;
  border: 2px solid rgba(30, 50, 90, 0.08);
  background: #fff;
  position: relative;
  transition: border-color 0.2s;
}

.image-card:hover {
  border-color: rgba(30, 50, 90, 0.2);
}

.image-card-inner {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  position: relative;
}

.product-thumb-img {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.product-thumb-img :deep(img) {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #fff;
}

.thumb-error {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-lighter);
  color: var(--el-text-color-secondary);
}

.primary-badge {
  position: absolute;
  top: 4px;
  left: 4px;
  background: var(--el-color-warning);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 8px;
  line-height: 1.6;
}

.image-actions {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  justify-content: center;
  gap: 4px;
  padding: 4px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(4px);
  opacity: 0;
  transition: opacity 0.2s;
}

.image-card:hover .image-actions {
  opacity: 1;
}

.add-image-dialog :deep(.el-dialog) {
  width: 560px !important;
  max-width: 90vw;
}

.add-tabs {
  min-height: 280px;
}

.dialog-scroll-body {
  max-height: 70vh;
  overflow-y: auto;
}

.picker-section {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}

:deep(.capsule-btn) {
  border-radius: 20px !important;
  padding: 8px 20px;
  font-weight: 500;
  transition: var(--transition-fast);
}

.btn-sm {
  padding: 5px 14px;
  font-size: 12px;
  border-radius: 16px !important;
}

.capsule-btn:hover {
  transform: scale(1.03);
}

.capsule-btn:active {
  transform: scale(0.97);
}

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

@media (max-width: 768px) {
  .add-image-dialog :deep(.el-dialog) {
    width: calc(100vw - 16px) !important;
    max-width: calc(100vw - 16px);
    margin: 8px auto;
  }
}

.glass-dialog :deep(.el-dialog__footer) {
  padding: 16px 24px;
}

.section-hint {
  margin: -8px 0 16px 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}
</style>
