<script setup lang="ts">
/**
 * 过程说明。原来这里直接把 10 条 SSE 的 JSON 摊在页面上，
 * 现在翻成一句一行的中文时间线，原始 JSON 折进二级折叠里给排障用。
 */
import { computed } from 'vue'
import type { StreamEvent } from '@/api'
import CollapseSection from './CollapseSection.vue'
import { eventSummary } from '@/utils/format'

const props = withDefaults(defineProps<{ events: StreamEvent[]; busy?: boolean }>(), { busy: false })

type Row = { key: string; label: string; detail: string }

const rows = computed<Row[]>(() => {
  const result: Row[] = []
  let deltaRow: Row | null = null
  let deltaCount = 0
  for (let position = 0; position < props.events.length; position += 1) {
    const item = props.events[position]
    if (item.event === 'answer_delta') {
      deltaCount += 1
      if (!deltaRow) {
        deltaRow = { key: `delta-${position}`, label: '逐字输出答案', detail: '' }
        result.push(deltaRow)
      }
      deltaRow.detail = `${deltaCount} 段`
      continue
    }
    const summary = eventSummary(item)
    if (!summary) continue
    const previous = result[result.length - 1]
    if (previous && previous.label === summary.label && previous.detail === summary.detail) continue
    result.push({ key: `${item.event}-${position}`, label: summary.label, detail: summary.detail })
  }
  return result
})
</script>

<template>
  <div class="timeline">
    <div
      v-for="(row, position) in rows"
      :key="row.key"
      class="timeline__row"
      :class="{ 'timeline__row--active': busy && position === rows.length - 1 }"
    >
      <span class="timeline__dot" aria-hidden="true" />
      <span class="timeline__label">{{ row.label }}</span>
      <span v-if="row.detail" class="timeline__detail">{{ row.detail }}</span>
    </div>
    <p v-if="!rows.length" class="muted-text">本次查询没有产生过程事件。</p>
  </div>
  <CollapseSection title="原始事件流" :hint="`${events.length} 条`" quiet>
    <div class="raw-json">
      <div v-for="(item, position) in events" :key="`${item.event}-${position}`" class="raw-json__row">
        <span class="raw-json__event">{{ item.event }}</span>
        {{ JSON.stringify(item.data) }}
      </div>
    </div>
  </CollapseSection>
</template>
