<template>
  <div
    class="floor-plan-manager"
    :class="{ 'is-compact': compact }"
  >
    <div class="fp-toolbar">
      <el-button
        size="small"
        class="capsule-btn"
        :disabled="disabled || uploading || reachedLimit"
        :loading="uploading"
        @click="pickFiles"
      >
        上传平面图
      </el-button>
      <el-button
        size="small"
        class="capsule-btn"
        :disabled="disabled || uploading || reachedLimit"
        @click="pickerOpen = true"
      >
        从媒体库选择
      </el-button>
      <span class="fp-hint">
        {{ items.length }} / {{ MAX_COUNT }} 张 · 支持 JPG / PNG / WebP
      </span>
    </div>

    <input
      ref="fileInput"
      type="file"
      accept="image/jpeg,image/png,image/webp"
      multiple
      class="fp-file-input"
      @change="onFilesPicked"
    >

    <div
      v-loading="loading"
      class="fp-list"
    >
      <div
        v-if="!items.length"
        class="fp-empty"
      >
        还没有平面图。上传或从媒体库选用后，会显示在方案分享页「方案信息」右侧。
      </div>

      <div
        v-else
        class="fp-grid"
      >
        <div
          v-for="(item, index) in items"
          :key="item.id || item.attachment_id"
          class="fp-card"
        >
          <button
            type="button"
            class="fp-thumb"
            :title="`预览：${item.name}`"
            @click="openViewer(index)"
          >
            <img
              v-if="item.image_url"
              :src="item.image_url"
              :alt="item.name"
              loading="lazy"
            >
            <span
              v-else
              class="fp-thumb-placeholder"
            >无预览</span>
          </button>

          <div class="fp-body">
            <el-input
              v-if="renamingKey === keyOf(item)"
              v-model="renameDraft"
              size="small"
              maxlength="128"
              class="fp-rename"
              @keyup.enter="commitRename(item)"
              @blur="commitRename(item)"
            />
            <button
              v-else
              type="button"
              class="fp-name"
              :title="item.name"
              :disabled="disabled"
              @click="startRename(item)"
            >
              {{ item.name }}
            </button>

            <div class="fp-actions">
              <span class="fp-index">第 {{ index + 1 }} 张</span>
              <button
                type="button"
                class="fp-action"
                :disabled="disabled || index === 0"
                @click="move(index, -1)"
              >
                上移
              </button>
              <button
                type="button"
                class="fp-action"
                :disabled="disabled || index === items.length - 1"
                @click="move(index, 1)"
              >
                下移
              </button>
              <button
                type="button"
                class="fp-action fp-action--danger"
                :disabled="disabled"
                @click="remove(item)"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <MediaPicker
      v-model="pickerOpen"
      type-filter="image"
      multiple
      @select="onPicked"
    />

    <el-image-viewer
      v-if="viewerOpen"
      :url-list="viewerUrls"
      :initial-index="viewerIndex"
      hide-on-click-modal
      @close="viewerOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElImageViewer, ElMessage, ElMessageBox } from 'element-plus'
import MediaPicker from '@/components/MediaPicker.vue'
import { mediaApi } from '@/api/media'
import type { MediaItem } from '@/api/media'
import { proposalFloorPlanApi } from '@/api/proposalFloorPlans'
import type { ProposalFloorPlan, FloorPlanDraft } from '@/types/sales'

const MAX_COUNT = 20

const props = withDefaults(
  defineProps<{
    /** 已存在的方案：组件直接读写后端。为空时进入暂存模式，通过 v-model 交给父组件。 */
    proposalId?: string | null
    modelValue?: FloorPlanDraft[]
    disabled?: boolean
    compact?: boolean
  }>(),
  {
    proposalId: null,
    modelValue: () => [],
    disabled: false,
    compact: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [items: FloorPlanDraft[]]
}>()

const items = ref<FloorPlanDraft[]>([])
const loading = ref(false)
const uploading = ref(false)
const pickerOpen = ref(false)
const fileInput = ref<HTMLInputElement>()
const renamingKey = ref('')
const renameDraft = ref('')
const viewerOpen = ref(false)
const viewerIndex = ref(0)
const hydrated = ref(false)

const bound = computed(() => Boolean(props.proposalId))
const reachedLimit = computed(() => items.value.length >= MAX_COUNT)
const viewerUrls = computed(() =>
  items.value.map((item) => item.image_url || '').filter((url) => Boolean(url)),
)

function keyOf(item: FloorPlanDraft): string {
  return item.id || item.attachment_id
}

function stripExtension(fileName: string): string {
  const trimmed = (fileName || '').trim()
  if (!trimmed) return '平面图'
  const dot = trimmed.lastIndexOf('.')
  const base = dot > 0 ? trimmed.slice(0, dot) : trimmed
  return base.slice(0, 128) || '平面图'
}

function toDraft(row: ProposalFloorPlan): FloorPlanDraft {
  return {
    id: row.id,
    attachment_id: row.attachment_id,
    name: row.name,
    image_url: row.image_url,
    sort: row.sort,
  }
}

function syncToParent() {
  emit('update:modelValue', items.value.map((item) => ({ ...item })))
}

async function load() {
  if (!bound.value || !props.proposalId) return
  loading.value = true
  try {
    const res = await proposalFloorPlanApi.list(props.proposalId)
    items.value = (res.data?.list || []).map(toDraft)
  } catch {
    // 接口失败时留空，不用旧数据冒充当前方案（拦截器已提示）
    items.value = []
  } finally {
    loading.value = false
  }
}

// 暂存模式下父组件重置表单时同步回来；绑定模式只由接口驱动，避免把预检结果覆盖掉。
watch(
  () => props.modelValue,
  (value) => {
    if (bound.value || hydrated.value === false) return
    items.value = (value || []).map((item) => ({ ...item }))
  },
  { deep: true },
)

watch(
  () => props.proposalId,
  (value) => {
    hydrated.value = true
    if (value) {
      load()
    } else {
      items.value = (props.modelValue || []).map((item) => ({ ...item }))
    }
  },
  { immediate: true },
)

function pickFiles() {
  fileInput.value?.click()
}

async function onFilesPicked(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (!files.length) return
  if (reachedLimit.value) {
    ElMessage.warning(`每个方案最多 ${MAX_COUNT} 张平面图`)
    return
  }

  uploading.value = true
  try {
    for (const file of files.slice(0, MAX_COUNT - items.value.length)) {
      if (!file.type.startsWith('image/')) {
        ElMessage.warning(`${file.name} 不是图片，已跳过`)
        continue
      }
      const media = await mediaApi.upload(file)
      const name = stripExtension(file.name)
      if (bound.value && props.proposalId) {
        await proposalFloorPlanApi.create(props.proposalId, {
          attachment_id: media.id,
          name,
          sort: items.value.length,
        })
      } else {
        items.value.push({
          attachment_id: media.id,
          name,
          image_url: media.url,
          sort: items.value.length,
        })
      }
    }
    if (bound.value) await load()
    else syncToParent()
  } catch {
    // 统一错误提示由 axios 拦截器给出
  } finally {
    uploading.value = false
  }
}

async function onPicked(picked: MediaItem | MediaItem[]) {
  const list = Array.isArray(picked) ? picked : [picked]
  const room = MAX_COUNT - items.value.length
  if (room <= 0) {
    ElMessage.warning(`每个方案最多 ${MAX_COUNT} 张平面图`)
    return
  }

  uploading.value = true
  try {
    for (const media of list.slice(0, room)) {
      if (media.type !== 'image') {
        ElMessage.warning(`${media.name} 不是图片，已跳过`)
        continue
      }
      const name = stripExtension(media.name)
      if (bound.value && props.proposalId) {
        await proposalFloorPlanApi.create(props.proposalId, {
          attachment_id: media.id,
          name,
          sort: items.value.length,
        })
      } else {
        items.value.push({
          attachment_id: media.id,
          name,
          image_url: media.url,
          sort: items.value.length,
        })
      }
    }
    if (bound.value) await load()
    else syncToParent()
  } catch {
    // 统一错误提示由 axios 拦截器给出
  } finally {
    uploading.value = false
  }
}

function startRename(item: FloorPlanDraft) {
  if (props.disabled) return
  renamingKey.value = keyOf(item)
  renameDraft.value = item.name
}

async function commitRename(item: FloorPlanDraft) {
  if (renamingKey.value !== keyOf(item)) return
  const next = renameDraft.value.trim()
  renamingKey.value = ''
  if (!next || next === item.name) return

  item.name = next
  if (bound.value && props.proposalId && item.id) {
    try {
      await proposalFloorPlanApi.update(props.proposalId, item.id, { name: next })
    } catch {
      // 失败时回读后端，避免界面显示一个没保存成功的名字
      await load()
      return
    }
  }
  if (!bound.value) syncToParent()
}

async function move(index: number, delta: number) {
  if (props.disabled) return
  const target = index + delta
  if (target < 0 || target >= items.value.length) return
  const next = [...items.value]
  ;[next[index], next[target]] = [next[target], next[index]]
  items.value = next
  items.value.forEach((item, position) => {
    item.sort = position
  })

  if (bound.value && props.proposalId) {
    const moved = [items.value[index], items.value[target]].filter((item) => item.id)
    try {
      await Promise.all(
        moved.map((item) =>
          proposalFloorPlanApi.update(props.proposalId as string, item.id as string, {
            sort: item.sort,
          }),
        ),
      )
    } catch {
      await load()
      return
    }
  } else {
    syncToParent()
  }
}

async function remove(item: FloorPlanDraft) {
  if (props.disabled) return
  try {
    await ElMessageBox.confirm(`确定移除平面图「${item.name}」吗？`, '移除平面图', {
      type: 'warning',
      confirmButtonText: '移除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  if (bound.value && props.proposalId && item.id) {
    try {
      await proposalFloorPlanApi.remove(props.proposalId, item.id)
      await load()
    } catch {
      // 拦截器已提示；保持列表不动，用户可重试
    }
  } else {
    items.value = items.value.filter((row) => keyOf(row) !== keyOf(item))
    items.value.forEach((row, position) => {
      row.sort = position
    })
    syncToParent()
  }
  // 媒体库文件保留，不做物理删除：它可能还被别的方案引用
}

function openViewer(index: number) {
  if (!viewerUrls.value.length) return
  const url = items.value[index]?.image_url
  viewerIndex.value = Math.max(0, url ? viewerUrls.value.indexOf(url) : 0)
  viewerOpen.value = true
}

defineExpose({ reload: load, items })
</script>

<style scoped>
.floor-plan-manager {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.fp-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.fp-hint {
  color: var(--pim-text-soft);
  font-size: 12px;
}

.fp-file-input {
  display: none;
}

.fp-list {
  min-height: 64px;
}

.fp-empty {
  padding: 16px;
  border: 1px dashed var(--pim-line-strong);
  border-radius: var(--pim-radius-sm);
  color: var(--pim-text-soft);
  font-size: 13px;
  line-height: 1.6;
  background: var(--pim-surface-soft);
}

.fp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
  gap: 12px;
}

.is-compact .fp-grid {
  grid-template-columns: repeat(auto-fill, minmax(148px, 1fr));
}

.fp-card {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--pim-line-strong);
  border-radius: var(--pim-radius-sm);
  background: var(--pim-surface-strong);
  overflow: hidden;
}

.fp-thumb {
  display: grid;
  place-items: center;
  width: 100%;
  aspect-ratio: 4 / 3;
  padding: 0;
  border: none;
  background: var(--pim-media-bg);
  cursor: zoom-in;
}

.fp-thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.fp-thumb-placeholder {
  color: var(--pim-text-faint);
  font-size: 12px;
}

.fp-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px 10px;
}

.fp-name {
  padding: 0;
  border: none;
  background: none;
  color: var(--pim-text-strong);
  font-size: 13px;
  font-weight: 600;
  text-align: left;
  cursor: text;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fp-name:hover {
  color: var(--pim-accent-deep);
}

.fp-rename {
  width: 100%;
}

.fp-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.fp-index {
  color: var(--pim-text-faint);
  font-size: 11.5px;
  margin-right: auto;
}

.fp-action {
  padding: 0;
  border: none;
  background: none;
  color: var(--pim-text-soft);
  font-size: 12px;
  cursor: pointer;
}

.fp-action:hover:not(:disabled) {
  color: var(--pim-text-strong);
}

.fp-action:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.fp-action--danger:hover:not(:disabled) {
  color: var(--pim-danger);
}
</style>
