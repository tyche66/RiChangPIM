<script setup lang="ts">
/**
 * 查询输入组件（composer）。
 *
 * 设计约束（AI-Docs/Furnispace-PLP-Design-Skill.md §6.2）：
 * 页面只有一个输入组件；产品类型胶囊只把关键词**预填**进输入框，
 * 不直接触发搜索，用户仍需自己按发送或 Enter。
 */
import { computed, nextTick, ref } from 'vue'

const props = defineProps<{ busy: boolean }>()
const emit = defineEmits<{ submit: [message: string]; stop: [] }>()

const PRODUCT_TYPES = ['办公桌', '会议桌', '办公椅', '文件柜']

const value = ref('')
const activeType = ref('')
const field = ref<HTMLTextAreaElement | null>(null)

const canSubmit = computed(() => Boolean(value.value.trim()) && !props.busy)

function autoGrow() {
  const el = field.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 220)}px`
}

async function focusField() {
  await nextTick()
  field.value?.focus()
  autoGrow()
}

/** 预填产品类型：再次点击同一个类型会撤销，换类型则替换旧关键词。 */
function pickType(type: string) {
  let text = value.value
  if (activeType.value) {
    text = text.replace(activeType.value, ' ')
  }
  if (activeType.value === type) {
    activeType.value = ''
  } else {
    text = `${type} ${text}`
    activeType.value = type
  }
  value.value = text.replace(/\s+/g, ' ').trimStart()
  void focusField()
}

function submit() {
  const message = value.value.trim()
  if (!message || props.busy) return
  emit('submit', message)
  value.value = ''
  activeType.value = ''
  void focusField()
}

function onKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  if (props.busy) {
    emit('stop')
    return
  }
  submit()
}
</script>

<template>
  <form class="composer" @submit.prevent="submit">
    <label class="sr-only" for="ai-query">查询内容</label>
    <textarea
      id="ai-query"
      ref="field"
      v-model="value"
      class="composer__field"
      rows="2"
      placeholder="输入产品搜索、问资料、查质量或做比较"
      @input="autoGrow"
      @keydown="onKeydown"
    />
    <div class="composer__toolbar">
      <div class="composer__chips" role="group" aria-label="产品类型快捷预填">
        <button
          v-for="type in PRODUCT_TYPES"
          :key="type"
          type="button"
          class="chip"
          :aria-pressed="activeType === type"
          @click="pickType(type)"
        >
          {{ type }}
        </button>
      </div>
      <div class="composer__actions">
        <span class="composer__hint">Enter 发送 · Shift + Enter 换行</span>
        <button v-if="busy" type="button" class="icon-button" aria-label="停止生成" @click="emit('stop')">
          <svg viewBox="0 0 18 18" aria-hidden="true">
            <rect x="5" y="5" width="8" height="8" rx="1.5" fill="currentColor" />
          </svg>
        </button>
        <button v-else type="submit" class="icon-button icon-button--send" aria-label="发送" :disabled="!canSubmit">
          <svg viewBox="0 0 18 18" fill="none" aria-hidden="true">
            <path d="M9 14.5V3.5M9 3.5 4.2 8.3M9 3.5l4.8 4.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  </form>
</template>
