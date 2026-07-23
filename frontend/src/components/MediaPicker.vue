<template>
  <el-dialog
    :model-value="modelValue"
    title="选择媒体文件"
    width="65%"
    append-to-body
    lock-scroll
    destroy-on-close
    top="5vh"
    class="media-picker-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="picker-body">
      <div class="picker-toolbar">
        <el-input
          v-model="searchQuery"
          placeholder="搜索文件名..."
          clearable
          :prefix-icon="Search"
          class="picker-search"
        />
        <el-select
          v-model="typeFilter"
          placeholder="类型筛选"
          class="picker-filter"
        >
          <el-option
            label="全部"
            value="all"
          />
          <el-option
            label="图片"
            value="image"
          />
          <el-option
            label="PDF"
            value="pdf"
          />
        </el-select>
      </div>

      <div
        v-if="loading"
        class="picker-loading"
      >
        <el-icon
          class="is-loading"
          :size="32"
        >
          <Loading />
        </el-icon>
      </div>

      <div
        v-else-if="filteredItems.length === 0"
        class="picker-empty"
      >
        <el-empty description="暂无媒体文件" />
      </div>

      <div
        v-else
        class="picker-grid"
      >
        <div
          v-for="item in filteredItems"
          :key="item.id"
          class="picker-card"
          :class="{ 'is-selected': selectedIds.includes(item.id) }"
          @click="toggleSelect(item.id)"
          @dblclick="confirm"
        >
          <div class="picker-thumb">
            <img
              v-if="item.type === 'image'"
              :src="item.thumbnailUrl || item.url"
              :alt="item.name"
              loading="lazy"
            >
            <el-icon
              v-else
              :size="36"
            >
              <Document />
            </el-icon>
          </div>
          <div class="picker-mask">
            <p class="picker-name">
              {{ item.name }}
            </p>
            <p class="picker-size">
              {{ formatSize(item.size) }}
            </p>
          </div>
          <div
            v-if="selectedIds.includes(item.id)"
            class="picker-check"
          >
            <el-icon
              color="#fff"
              :size="16"
            >
              <Check />
            </el-icon>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <span class="picker-selection-count">已选择 {{ selectedIds.length }} 项</span>
      <el-button @click="emit('update:modelValue', false)">
        取消
      </el-button>
      <el-button
        type="primary"
        :disabled="selectedIds.length === 0"
        @click="confirm"
      >
        确认选择
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Search, Loading, Document, Check } from '@element-plus/icons-vue'
import { mediaApi, formatSize } from '@/api/media'
import type { MediaItem } from '@/api/media'

const props = defineProps<{
  modelValue: boolean
  typeFilter?: string
  multiple?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  select: [item: MediaItem | MediaItem[]]
}>()

const searchQuery = ref('')
const typeFilter = ref('all')
const loading = ref(false)
const items = ref<MediaItem[]>([])
const selectedIds = ref<string[]>([])

watch(
  () => props.typeFilter,
  (val) => {
    if (val) typeFilter.value = val
  },
  { immediate: true }
)

const filteredItems = computed(() =>
  items.value.filter((item) => {
    const matchSearch = item.name.toLowerCase().includes(searchQuery.value.toLowerCase())
    const matchType = typeFilter.value === 'all' || item.type === typeFilter.value
    return matchSearch && matchType
  })
)

async function fetchItems() {
  loading.value = true
  try {
    items.value = await mediaApi.list({ search: searchQuery.value, type: typeFilter.value })
  } finally {
    loading.value = false
  }
}

watch([searchQuery, typeFilter], fetchItems)

watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      selectedIds.value = []
      fetchItems()
    }
  }
)

function toggleSelect(id: string) {
  if (!props.multiple) {
    selectedIds.value = [id]
    return
  }
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) selectedIds.value.splice(idx, 1)
  else selectedIds.value.push(id)
}

function confirm() {
  const selectedItems = items.value.filter((i) => selectedIds.value.includes(i.id))
  if (selectedItems.length > 0) {
    emit('select', props.multiple ? selectedItems : selectedItems[0])
    emit('update:modelValue', false)
  }
}

defineExpose({ items, selectedIds, confirm })
</script>

<style scoped>
.picker-body {
  min-height: 300px;
  max-height: 75vh;
  overflow-y: auto;
}
.picker-toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
.picker-search {
  flex: 1;
}
.picker-filter {
  width: 140px;
}
.picker-selection-count {
  margin-right: auto;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.picker-loading,
.picker-empty {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}
.picker-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 12px;
  max-height: 50vh;
  overflow-y: auto;
  padding: 4px;
}
.picker-card {
  position: relative;
  aspect-ratio: 1;
  border: 2px solid var(--el-border-color-light);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s;
}
.picker-card:hover {
  border-color: var(--el-color-primary-light-3);
}
.picker-card.is-selected {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px var(--el-color-primary-light-5);
}
.picker-thumb {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-lighter);
}
.picker-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.picker-mask {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  opacity: 0;
  transition: opacity 0.2s;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  padding: 6px 8px;
}
.picker-card:hover .picker-mask {
  opacity: 1;
}
.picker-name {
  color: #fff;
  font-size: 12px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin: 0;
}
.picker-size {
  color: rgba(255, 255, 255, 0.7);
  font-size: 11px;
  margin: 0;
}
.picker-check {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--el-color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
}

@media (max-width: 768px) {
  :deep(.el-dialog) {
    width: calc(100vw - 16px) !important;
    max-width: calc(100vw - 16px);
    margin: 8px auto;
  }

  .picker-toolbar {
    flex-direction: column;
  }

  .picker-filter {
    width: 100%;
  }
}
</style>
