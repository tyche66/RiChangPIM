<script setup lang="ts">
/**
 * 来源卡片。紧凑行式：类型说中文、编号对应正文角标、
 * 缺失的章节与正文不再渲染成 `section: -` / `无可展示正文` 这类噪音。
 */
import { computed, ref } from 'vue'
import type { KnowledgeSource } from '@/api'
import { formatDateTime, sourceTypeLabel } from '@/utils/format'

const props = withDefaults(defineProps<{ source: KnowledgeSource; index?: number }>(), { index: 0 })
const emit = defineEmits<{ open: [sourceId: string] }>()

const CLAMP_AT = 90

const clamped = ref(true)

const title = computed(() => props.source.title?.trim() || '未命名来源')
const quote = computed(() => props.source.quote?.trim() || '')
const canExpand = computed(() => quote.value.length > CLAMP_AT)

const metaText = computed(() => {
  const source = props.source
  const parts: string[] = []
  if (source.section?.trim()) parts.push(source.section.trim())
  if (typeof source.page === 'number') parts.push(`第 ${source.page} 页`)
  const observed = formatDateTime(source.observed_at)
  if (observed) parts.push(`数据时点 ${observed}`)
  return parts.join(' · ')
})
</script>

<template>
  <article class="source-card">
    <div class="source-card__main">
      <span v-if="index" class="source-card__index" :aria-label="`第 ${index} 条引用`">{{ index }}</span>
      <div class="source-card__text">
        <div class="source-card__head">
          <span class="type-chip">{{ sourceTypeLabel(source.source_type) }}</span>
          <span class="source-card__title">{{ title }}</span>
        </div>
        <p v-if="metaText" class="source-card__meta">{{ metaText }}</p>
        <p v-if="quote" class="source-card__quote" :class="{ 'is-clamped': canExpand && clamped }">{{ quote }}</p>
        <button
          v-if="canExpand"
          type="button"
          class="button button--ghost button--small source-card__toggle"
          @click="clamped = !clamped"
        >
          {{ clamped ? '展开原文' : '收起原文' }}
        </button>
      </div>
    </div>
    <button type="button" class="button button--secondary button--small" @click="emit('open', source.source_id)">
      打开
    </button>
  </article>
</template>
