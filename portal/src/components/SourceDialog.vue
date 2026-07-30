<script setup lang="ts">
/**
 * 来源详情弹层。替换原来的 window.alert：
 * 原生 dialog 自带焦点陷阱、Escape 关闭和背景遮罩。
 */
import { computed, ref, watch } from 'vue'
import type { KnowledgeSource } from '@/api'
import { MISSING_TEXT, formatDateTime, shortId, sourceTypeLabel } from '@/utils/format'

const props = defineProps<{ source: KnowledgeSource | null }>()
const emit = defineEmits<{ close: [] }>()

const dialog = ref<HTMLDialogElement | null>(null)

const quote = computed(() => props.source?.quote?.trim() || '')
const rows = computed<Array<[string, string]>>(() => {
  const source = props.source
  if (!source) return []
  const items: Array<[string, string]> = [['来源类型', sourceTypeLabel(source.source_type)]]
  if (source.section?.trim()) items.push(['章节', source.section.trim()])
  if (typeof source.page === 'number') items.push(['页码', `第 ${source.page} 页`])
  const observed = formatDateTime(source.observed_at)
  if (observed) items.push(['数据时点', observed])
  items.push(['来源编号', shortId(source.source_id, 14) || MISSING_TEXT])
  return items
})

watch(
  () => props.source,
  (value) => {
    const el = dialog.value
    if (!el) return
    if (value && !el.open) el.showModal()
    if (!value && el.open) el.close()
  },
)
</script>

<template>
  <dialog ref="dialog" class="source-dialog" aria-label="来源详情" @close="emit('close')">
    <div v-if="source" class="source-dialog__header">
      <div>
        <span class="type-chip">{{ sourceTypeLabel(source.source_type) }}</span>
        <h2>{{ source.title || '未命名来源' }}</h2>
      </div>
      <button type="button" class="icon-button icon-button--quiet" aria-label="关闭来源详情" @click="emit('close')">
        <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
        </svg>
      </button>
    </div>
    <div v-if="source" class="source-dialog__body">
      <div class="kv-grid">
        <template v-for="row in rows" :key="row[0]">
          <span>{{ row[0] }}</span>
          <strong>{{ row[1] }}</strong>
        </template>
      </div>
      <p v-if="quote" class="source-dialog__quote">{{ quote }}</p>
      <p v-else class="muted-text">这条来源没有提供可展示的原文片段。</p>
      <div class="source-dialog__footer">
        <a
          v-if="source.open_url"
          class="button button--secondary button--small"
          :href="source.open_url"
          target="_blank"
          rel="noopener noreferrer"
        >
          在新标签页查看原件
        </a>
        <button type="button" class="button button--secondary button--small" @click="emit('close')">关闭</button>
      </div>
    </div>
  </dialog>
</template>
