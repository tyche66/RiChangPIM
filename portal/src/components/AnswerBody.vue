<script setup lang="ts">
/**
 * 答案正文。两件事：
 * 1. Markdown 可视化渲染——标题、粗斜体、列表、表格、引用、分隔线、链接、
 *    行内代码与代码块全部由 utils/markdown 渲染成真实元素，不再直接吐
 *    `##` / `---` / `**文字**` / 原始表格分隔符。markdown.ts 对输入先做
 *    HTML 转义、再只输出白名单标签，答案里的 HTML 没有注入面。
 * 2. 引用角标——`[chunk:uuid]` 已被 utils/citations 折叠成私有区占位符，
 *    markdown.ts 在这里还原成 `<button class="citation">`，点击通过事件
 *    委托派发给来源弹层，引用关系不丢。
 */
import { computed } from 'vue'
import type { AnswerSegment } from '@/utils/citations'
import { answerSource, citationInfoOf } from '@/utils/citations'
import { renderMarkdown } from '@/utils/markdown'

const props = withDefaults(
  defineProps<{ segments: AnswerSegment[]; placeholder?: string }>(),
  { placeholder: '' },
)
const emit = defineEmits<{ open: [sourceId: string] }>()

const html = computed(() => renderMarkdown(answerSource(props.segments), citationInfoOf(props.segments)))

/** 事件委托：角标是 v-html 生成的按钮，统一在容器上接一次点击。 */
function onClick(event: MouseEvent) {
  const target = event.target
  if (!(target instanceof Element)) return
  const button = target.closest('button.citation')
  if (!(button instanceof HTMLButtonElement)) return
  const sourceId = button.dataset.source
  if (sourceId) emit('open', sourceId)
}
</script>

<template>
  <div class="answer-body" @click="onClick">
    <div v-if="html" class="answer-body__markdown" v-html="html" />
    <span v-else-if="placeholder" class="answer-body__placeholder">{{ placeholder }}</span>
  </div>
</template>
