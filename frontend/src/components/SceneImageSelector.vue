<template>
  <div class="scene-image-selector">
    <div class="image-section-header">
      <h4 class="section-title">
        场景图
      </h4>
      <span class="image-count">{{ images.length }}/30</span>
      <el-button
        size="small"
        class="capsule-btn btn-sm"
        :disabled="images.length >= 30"
        @click="showSelectorDialog = true"
      >
        + 绑定场景图
      </el-button>
      <el-button
        size="small"
        class="capsule-btn btn-sm"
        @click="$router.push('/scene-images')"
      >
        去场景图管理
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
        description="暂无场景图"
        :image-size="80"
      />
    </div>

    <div
      v-else
      class="image-grid"
    >
      <div
        v-for="(img, index) in images"
        :key="img.sceneImageId"
        class="image-card"
      >
        <div class="image-card-inner">
          <el-image
            :src="img.thumbnailUrl || img.url"
            fit="contain"
            class="scene-thumb-img"
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
          <div class="image-actions">
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
                @click="unbind(img.sceneImageId)"
              />
            </el-tooltip>
          </div>
        </div>
      </div>
    </div>

    <!-- Scene Image Selector Dialog -->
    <el-dialog
      v-model="showSelectorDialog"
      title="选择场景图"
      class="glass-dialog"
      append-to-body
      lock-scroll
      destroy-on-close
      width="700px"
    >
      <div class="dialog-scroll-body">
        <el-tabs v-model="selectorTab">
          <!-- Tab: Choose Existing -->
          <el-tab-pane
            label="选择已有场景图"
            name="existing"
          >
            <div class="selector-toolbar">
              <el-input
                v-model="sceneSearch"
                placeholder="搜索场景图名称..."
                clearable
                :prefix-icon="Search"
                class="selector-search"
                @input="fetchSceneImages"
              />
            </div>
            <div
              v-loading="sceneLoading"
              class="selector-body"
            >
              <div
                v-if="sceneItems.length === 0 && !sceneLoading"
                class="selector-empty"
              >
                <el-empty description="暂无场景图">
                  <el-button
                    type="primary"
                    size="small"
                    @click="selectorTab = 'create'"
                  >
                    去创建场景图
                  </el-button>
                </el-empty>
              </div>
              <div
                v-else
                class="selector-grid"
              >
                <div
                  v-for="item in sceneItems"
                  :key="item.id"
                  class="selector-card"
                  :class="{ 'is-selected': selectedSceneId === item.id, 'is-bound': isBound(item.id) }"
                  @click="selectedSceneId = item.id"
                  @dblclick="confirmBindExisting"
                >
                  <div class="selector-thumb">
                    <el-image
                      :src="item.preview_url || item.file_url"
                      fit="cover"
                      class="selector-thumb-img"
                    >
                      <template #error>
                        <div class="thumb-error">
                          <el-icon :size="24">
                            <Picture />
                          </el-icon>
                        </div>
                      </template>
                    </el-image>
                  </div>
                  <div class="selector-info">
                    <p class="selector-name">
                      {{ item.name }}
                    </p>
                    <p class="selector-meta">
                      <el-tag
                        v-if="item.bound_products.length > 0"
                        size="small"
                        type="warning"
                        effect="plain"
                      >
                        已绑定 {{ item.bound_products.length }}
                      </el-tag>
                      <span
                        v-else
                        class="unbound-tag"
                      >未绑定</span>
                    </p>
                  </div>
                  <div
                    v-if="isBound(item.id)"
                    class="bound-badge"
                  >
                    <el-icon><Check /></el-icon>
                    已绑定
                  </div>
                </div>
              </div>
            </div>
            <template #footer>
              <el-button @click="showSelectorDialog = false">
                取消
              </el-button>
              <el-button
                type="primary"
                :disabled="!selectedSceneId"
                :loading="binding"
                @click="confirmBindExisting"
              >
                确认绑定
              </el-button>
            </template>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-dialog>

    <!-- Image Preview -->
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
import { ArrowUp, ArrowDown, Remove, Picture, Search, Check } from '@element-plus/icons-vue'
import { productApi, sceneImageApi } from '@/api'
import type { SceneImage } from '@/api'

export interface SceneImageItem {
  sceneImageId: string
  attachmentId?: string
  url: string
  thumbnailUrl?: string
  name: string
  sortOrder: number
}

const props = defineProps<{
  productId: string
  images: SceneImageItem[]
}>()

const emit = defineEmits<{
  change: [images: SceneImageItem[]]
}>()

const localImages = ref<SceneImageItem[]>([...props.images])

watch(() => props.images, (val) => {
  localImages.value = [...val]
}, { deep: true })

const previewImg = ref('')
const showSelectorDialog = ref(false)
const selectorTab = ref('existing')
const binding = ref(false)

// Existing scene images
const sceneLoading = ref(false)
const sceneItems = ref<SceneImage[]>([])
const sceneSearch = ref('')
const selectedSceneId = ref<string | null>(null)

const MAX_SCENE_IMAGES = 30

function syncImages() {
  emit('change', [...localImages.value])
}

function isBound(sceneImageId: string): boolean {
  return localImages.value.some((img) => img.sceneImageId === sceneImageId)
}

async function fetchSceneImages() {
  sceneLoading.value = true
  try {
    const res: any = await sceneImageApi.list({ keyword: sceneSearch.value, page: 1, size: 100 })
    const data = res.data?.data || res.data || res
    sceneItems.value = data.list || []
  } catch {
    sceneItems.value = []
  } finally {
    sceneLoading.value = false
  }
}

watch(showSelectorDialog, (val) => {
  if (val) {
    selectedSceneId.value = null
    fetchSceneImages()
  }
})

async function confirmBindExisting() {
  if (!selectedSceneId.value) return
  if (isBound(selectedSceneId.value)) {
    ElMessage.warning('该场景图已绑定到当前产品')
    return
  }
  if (localImages.value.length >= MAX_SCENE_IMAGES) {
    ElMessage.warning(`场景图最多 ${MAX_SCENE_IMAGES} 张`)
    return
  }
  binding.value = true
  try {
    await productApi.bindSceneImages(props.productId, { scene_image_ids: [selectedSceneId.value] })
    const item = sceneItems.value.find((s) => s.id === selectedSceneId.value)
    if (item) {
      localImages.value.push({
        sceneImageId: item.id,
        attachmentId: item.attachment_id,
        url: item.preview_url || item.file_url,
        thumbnailUrl: item.preview_url || item.file_url,
        name: item.name,
        sortOrder: localImages.value.length,
      })
      syncImages()
    }
    ElMessage.success('场景图已绑定')
    showSelectorDialog.value = false
  } catch {
    // handled by interceptor
  } finally {
    binding.value = false
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
    await productApi.reorderSceneImages(props.productId, {
      items: arr.map((img, i) => ({ scene_image_id: img.sceneImageId, sort: i })),
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
    await productApi.reorderSceneImages(props.productId, {
      items: arr.map((img, i) => ({ scene_image_id: img.sceneImageId, sort: i })),
    })
  } catch {
    // handled by interceptor
  }
}

async function unbind(sceneImageId: string) {
  try {
    await productApi.unbindSceneImage(props.productId, sceneImageId)
    localImages.value = localImages.value.filter((img) => img.sceneImageId !== sceneImageId)
    syncImages()
    ElMessage.success('场景图已解绑')
  } catch {
    // handled by interceptor
  }
}
</script>

<style scoped>
.scene-image-selector {
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

.scene-thumb-img {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.scene-thumb-img :deep(img) {
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

/* Selector Dialog */
.selector-toolbar {
  margin-bottom: 12px;
}

.dialog-scroll-body {
  max-height: 70vh;
  overflow-y: auto;
}

.selector-search {
  width: 100%;
}

.selector-body {
  min-height: 300px;
  max-height: 50vh;
  overflow-y: auto;
}

@media (max-width: 768px) {
  :deep(.el-dialog) {
    width: calc(100vw - 16px) !important;
    max-width: calc(100vw - 16px);
    margin: 8px auto;
  }
}

.selector-empty {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 250px;
}

.selector-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
  padding: 4px;
}

.selector-card {
  position: relative;
  border: 2px solid var(--el-border-color-light);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s;
  background: #fff;
}

.selector-card:hover {
  border-color: var(--el-color-primary-light-3);
}

.selector-card.is-selected {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px var(--el-color-primary-light-5);
}

.selector-card.is-bound {
  border-color: var(--el-color-success-light-3);
}

.selector-thumb {
  aspect-ratio: 1;
  background: var(--el-fill-color-lighter);
  overflow: hidden;
}

.selector-thumb-img {
  width: 100%;
  height: 100%;
}

.selector-thumb-img :deep(img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.selector-info {
  padding: 8px;
}

.selector-name {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.selector-meta {
  display: flex;
  align-items: center;
  gap: 4px;
}

.unbound-tag {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.bound-badge {
  position: absolute;
  top: 4px;
  right: 4px;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px 6px;
  background: var(--el-color-success);
  color: #fff;
  font-size: 11px;
  border-radius: 10px;
}

.section-hint {
  margin: -8px 0 16px 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}
</style>
