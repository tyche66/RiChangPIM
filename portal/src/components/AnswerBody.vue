<script setup lang="ts">
/**
 * 答案正文。原始 `[chunk:uuid]` 标记已在 utils/citations 折叠成脚注角标，
 * 点角标可以打开对应来源，引用关系不丢。
 */
import { computed } from 'vue'
import type { AnswerSegment } from '@/utils/citations'

const props = withDefaults(
  defineProps<{ segments: AnswerSegment[]; placeholder?: string }>(),
  { placeholder: '' },
)
const emit = defineEmits<{ open: [sourceId: string] }>()

type Piece = {
  key: string
  isCitation: boolean
  text: string
  index: number
  sourceId: string
  token: string
}

const pieces = computed<Piece[]>(() =>
  props.segments.map((segment, position) => {
    if (segment.kind === 'text') {
      return { key: `t${position}`, isCitation: false, text: segment.text, index: 0, sourceId: '', token: '' }
    }
    return {
      key: `c${position}`,
      isCitation: true,
      text: String(segment.index),
      index: segment.index,
      sourceId: segment.sourceId || '',
      token: segment.token,
    }
  }),
)
</script>

<template>
  <div class="answer-body">
    <template v-for="piece in pieces" :key="piece.key">
      <span v-if="!piece.isCitation">{{ piece.text }}</span>
      <button
        v-else-if="piece.sourceId"
        type="button"
        class="citation"
        :aria-label="`查看第 ${piece.index} 条引用来源`"
        @click="emit('open', piece.sourceId)"
      >
        {{ piece.index }}
      </button>
      <span v-else class="citation citation--unresolved" :title="`引用标记 ${piece.token} 未匹配到来源`">
        {{ piece.index }}
      </span>
    </template>
    <span v-if="!pieces.length && placeholder" class="answer-body__placeholder">{{ placeholder }}</span>
  </div>
</template>
