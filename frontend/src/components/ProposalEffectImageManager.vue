<template>
  <div
    class="effect-image-manager"
    :class="{ 'is-compact': compact }"
  >
    <div class="ei-toolbar">
      <el-button
        size="small"
        class="capsule-btn"
        :disabled="disabled || uploading || reachedLimit"
        :loading="uploading"
        @click="pickFiles"
      >
        上传效果图
      </el-button>
      <el-button
        size="small"
        class="capsule-btn"
        :disabled="disabled || uploading || reachedLimit"
        @click="pickerOpen = true"
      >
        从媒体库选择
      </el-button>
      <span class="ei-hint">
        {{ items.length }} / {{ MAX_COUNT }} 张 · 效果图优先展示在方案分享页，
        绑定产品后同步出现在该产品的「搭配案例」
      </span>
    </div>

    <input
      ref="fileInput"
      type="file"
      accept="image/jpeg,image/png,image/webp"
      multiple
      class="ei-file-input"
      @change="onFilesPicked"
    >

    <div
      v-loading="loading"
      class="ei-list"
    >
      <div
        v-if="!items.length"
        class="ei-empty"
      >
        还没有效果图。上传或从媒体库选用后，会显示在方案分享页「效果图」板块；
        绑定产品后还会出现在该产品的详情页「搭配案例」。
      </div>

      <div
        v-else
        class="ei-grid"
      >
        <div
          v-for="(item, index) in items"
          :key="item.id || item.attachment_id"
          class="ei-card"
        >
          <button
            type="button"
            class="ei-thumb"
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
              class="ei-thumb-placeholder"
            >无预览</span>
          </button>

          <div class="ei-body">
            <el-input
              v-if="renamingKey === keyOf(item)"
              v-model="renameDraft"
              size="small"
              maxlength="128"
              class="ei-rename"
              @keyup.enter="commitRename(item)"
              @blur="commitRename(item)"
            />
            <button
              v-else
              type="button"
              class="ei-name"
              :title="item.name"
              :disabled="disabled"
              @click="startRename(item)"
            >
              {{ item.name }}
            </button>

            <div class="ei-bindings">
              <label class="ei-bind-label">绑定产品</label>
              <el-select
                :model-value="item.product_id || ''"
                size="small"
                clearable
                filterable
                :disabled="disabled"
                placeholder="不绑定"
                class="ei-bind-select"
                @update:model-value="(val: string) => bindProduct(item, val || null)"
              >
                <el-option
                  v-for="opt in productOptions"
                  :key="opt.id"
                  :label="`${opt.product_name}（${opt.product_no}）`"
                  :value="opt.id"
                />
              </el-select>

              <label class="ei-bind-label">绑定空间</label>
              <el-select
                :model-value="spaceKeyOf(item)"
                size="small"
                clearable
                :disabled="disabled"
                placeholder="不绑定"
                class="ei-bind-select"
                @update:model-value="(val: string) => bindSpace(item, val || '')"
              >
                <el-option
                  v-for="opt in spaceOptions"
                  :key="opt.key"
                  :label="opt.label || '未指定位置'"
                  :value="opt.key"
                />
              </el-select>
            </div>

            <div class="ei-actions">
              <span class="ei-index">第 {{ index + 1 }} 张</span>
              <button
                type="button"
                class="ei-action"
                :disabled="disabled || index === 0"
                @click="move(index, -1)"
              >
                上移
              </button>
              <button
                type="button"
                class="ei-action"
                :disabled="disabled || index === items.length - 1"
                @click="move(index, 1)"
              >
                下移
              </button>
              <button
                type="button"
                class="ei-action ei-action--danger"
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
import { proposalEffectImageApi } from '@/api/proposalEffectImages'
import type { EffectImageDraft, ProposalEffectImage, ProposalItem } from '@/types/sales'

const MAX_COUNT = 20

const props = withDefaults(
  defineProps<{
    /** 已存在的方案：组件直接读写后端。为空时进入暂存模式，通过 v-model 交给父组件。 */
    proposalId?: string | null
    modelValue?: EffectImageDraft[]
    /** 方案明细（用于绑定产品/空间的下拉选项；暂存模式由父组件传入当前草稿） */
    items?: ProposalItem[]
    disabled?: boolean
    compact?: boolean
  }>(),
  {
    proposalId: null,
    modelValue: () => [],
    items: () => [],
    disabled: false,
    compact: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [items: EffectImageDraft[]]
}>()

const items = ref<EffectImageDraft[]>([])
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

/** 绑定产品下拉：只列产品库产品（方案明细里的）。 */
const productOptions = computed(() =>
  props.items
    .filter((it) => !it.is_custom && it.product_id)
    .map((it) => ({
      id: it.product_id as string,
      product_name: it.display_name || it.product_name || it.custom_product?.name || '',
      product_no: it.product_no || '',
    }))
    .filter((opt) => opt.product_name),
)

/** 绑定空间下拉：方案明细已用的 楼层/空间 组合（与分享页分组同口径）。 */
const spaceOptions = computed(() => {
  const map = new Map<string, { key: string; label: string; floor: string; space: string }>()
  props.items.forEach((it) => {
    const floor = (it.floor_label || '').trim()
    const space = (it.space_label || '').trim()
    const key = `${floor}||${space}`
    if (!map.has(key)) {
      map.set(key, {
        key,
        label: [floor, space].filter(Boolean).join(' / ') || '',
        floor,
        space,
      })
    }
  })
  return [...map.values()]
})

function keyOf(item: EffectImageDraft): string {
  return item.id || item.attachment_id
}

function spaceKeyOf(item: EffectImageDraft): string {
  return `${(item.floor_label || '').trim()}||${(item.space_label || '').trim()}`
}

function stripExtension(fileName: string): string {
  const trimmed = (fileName || '').trim()
  if (!trimmed) return '效果图'
  const dot = trimmed.lastIndexOf('.')
  const base = dot > 0 ? trimmed.slice(0, dot) : trimmed
  return base.slice(0, 128) || '效果图'
}

function toDraft(row: ProposalEffectImage): EffectImageDraft {
  return {
    id: row.id,
    attachment_id: row.attachment_id,
    name: row.name,
    image_url: row.image_url,
    product_id: row.product_id,
    project_space_id: row.project_space_id,
    floor_label: row.floor_label,
    space_label: row.space_label,
    product_name: row.product_name,
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
    const res = await proposalEffectImageApi.list(props.proposalId)
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

function persistDraft(draft: EffectImageDraft) {
  if (bound.value && props.proposalId && draft.id) {
    return proposalEffectImageApi
      .update(props.proposalId, draft.id, {
        name: draft.name,
        sort: draft.sort,
        product_id: draft.product_id || null,
        project_space_id: draft.project_space_id || null,
        floor_label: draft.floor_label || null,
        space_label: draft.space_label || null,
      })
      .catch(async () => {
        await load()
      })
  }
  return Promise.resolve()
}

async function onFilesPicked(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (!files.length) return
  if (reachedLimit.value) {
    ElMessage.warning(`每个方案最多 ${MAX_COUNT} 张效果图`)
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
        await proposalEffectImageApi.create(props.proposalId, {
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
    ElMessage.warning(`每个方案最多 ${MAX_COUNT} 张效果图`)
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
        await proposalEffectImageApi.create(props.proposalId, {
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

function bindProduct(item: EffectImageDraft, productId: string | null) {
  item.product_id = productId || null
  const opt = productOptions.value.find((o) => o.id === productId)
  item.product_name = opt?.product_name || null
  if (bound.value) {
    persistDraft(item)
  } else {
    syncToParent()
  }
}

function bindSpace(item: EffectImageDraft, key: string) {
  const opt = spaceOptions.value.find((o) => o.key === key)
  if (opt) {
    item.floor_label = opt.floor || null
    item.space_label = opt.space || null
  } else {
    item.floor_label = null
    item.space_label = null
  }
  if (bound.value) {
    persistDraft(item)
  } else {
    syncToParent()
  }
}

function startRename(item: EffectImageDraft) {
  if (props.disabled) return
  renamingKey.value = keyOf(item)
  renameDraft.value = item.name
}

async function commitRename(item: EffectImageDraft) {
  if (renamingKey.value !== keyOf(item)) return
  const next = renameDraft.value.trim()
  renamingKey.value = ''
  if (!next || next === item.name) return

  item.name = next
  if (bound.value) {
    try {
      await persistDraft(item)
    } catch {
      await load()
    }
    return
  }
  syncToParent()
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
          proposalEffectImageApi.update(props.proposalId as string, item.id as string, {
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

async function remove(item: EffectImageDraft) {
  if (props.disabled) return
  try {
    await ElMessageBox.confirm(`确定移除效果图「${item.name}」吗？`, '移除效果图', {
      type: 'warning',
      confirmButtonText: '移除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  if (bound.value && props.proposalId && item.id) {
    try {
      await proposalEffectImageApi.remove(props.proposalId, item.id)
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
.effect-image-manager {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.ei-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.ei-hint {
  color: var(--pim-text-soft);
  font-size: 12px;
}

.ei-file-input {
  display: none;
}

.ei-list {
  min-height: 64px;
}

.ei-empty {
  padding: 16px;
  border: 1px dashed var(--pim-line-strong);
  border-radius: var(--pim-radius-sm);
  color: var(--pim-text-soft);
  font-size: 13px;
  line-height: 1.6;
  background: var(--pim-surface-soft);
}

.ei-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.is-compact .ei-grid {
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
}

.ei-card {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--pim-line-strong);
  border-radius: var(--pim-radius-sm);
  background: var(--pim-surface-strong);
  overflow: hidden;
}

.ei-thumb {
  display: grid;
  place-items: center;
  width: 100%;
  aspect-ratio: 4 / 3;
  padding: 0;
  border: none;
  background: var(--pim-media-bg);
  cursor: zoom-in;
}

.ei-thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.ei-thumb-placeholder {
  color: var(--pim-text-faint);
  font-size: 12px;
}

.ei-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 10px 10px;
}

.ei-name {
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

.ei-name:hover {
  color: var(--pim-accent-deep);
}

.ei-rename {
  width: 100%;
}

.ei-bindings {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ei-bind-label {
  color: var(--pim-text-faint);
  font-size: 11.5px;
  line-height: 1.2;
}

.ei-bind-select {
  width: 100%;
}

.ei-bind-select :deep(.el-select__wrapper) {
  min-height: 28px;
}

.ei-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.ei-index {
  color: var(--pim-text-faint);
  font-size: 11.5px;
  margin-right: auto;
}

.ei-action {
  padding: 0;
  border: none;
  background: none;
  color: var(--pim-text-soft);
  font-size: 12px;
  cursor: pointer;
}

.ei-action:hover:not(:disabled) {
  color: var(--pim-text-strong);
}

.ei-action:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.ei-action--danger:hover:not(:disabled) {
  color: var(--pim-danger);
}
</style>