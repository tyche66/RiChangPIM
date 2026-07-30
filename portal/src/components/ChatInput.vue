<script setup lang="ts">
/**
 * 查询输入组件（composer）。
 *
 * 外形对齐 reeoo.com 首屏那条胶囊搜索框：左侧放大镜、中间输入、
 * 右侧黑色圆形箭头按钮；类型胶囊移到胶囊下方，保持搜索框本身干净。
 *
 * 设计约束（AI-Docs/Furnispace-PLP-Design-Skill.md §6.2）：
 * 页面只有一个输入组件；类型胶囊和能力入口都只把关键词**预填**进输入框，
 * 不直接触发搜索，用户仍需自己按发送或 Enter。
 */
import { computed, nextTick, ref } from 'vue'

const props = defineProps<{ busy: boolean }>()
const emit = defineEmits<{ submit: [message: string]; stop: [] }>()

const PRODUCT_TYPES = ['办公桌', '会议桌', '办公椅', '文件柜']
/** 胶囊形状下输入框最多长到这么高，再长就内部滚动，避免撑破圆角。 */
const FIELD_MAX_HEIGHT = 132

const value = ref('')
const activeType = ref('')
const field = ref<HTMLTextAreaElement | null>(null)

const canSubmit = computed(() => Boolean(value.value.trim()) && !props.busy)

function autoGrow() {
  const el = field.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, FIELD_MAX_HEIGHT)}px`
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

/**
 * 能力入口的预填：动作词放最前面，已经写好的内容保留在后面，
 * 重复点击同一个入口不会把词叠加两遍。
 */
function prefill(text: string) {
  const phrase = text.trim()
  if (!phrase) return
  const rest = value.value.replace(phrase, ' ').replace(/\s+/g, ' ').trim()
  value.value = rest ? `${phrase} ${rest}` : `${phrase} `
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

defineExpose({ prefill })
</script>

<template>
  <form class="composer-form" @submit.prevent="submit">
    <div class="composer">
      <span class="composer__icon" aria-hidden="true">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M17 17l4 4M11 19a8 8 0 1 1 0-16a8 8 0 0 1 0 16" />
        </svg>
      </span>
      <label class="sr-only" for="ai-query">查询内容</label>
      <textarea
        id="ai-query"
        ref="field"
        v-model="value"
        class="composer__field"
        rows="1"
        placeholder="输入产品搜索、问资料、查质量或做比较"
        @input="autoGrow"
        @keydown="onKeydown"
      />
      <button v-if="busy" type="button" class="icon-button" aria-label="停止生成" @click="emit('stop')">
        <svg viewBox="0 0 18 18" aria-hidden="true">
          <rect x="5" y="5" width="8" height="8" rx="1.5" fill="currentColor" />
        </svg>
      </button>
      <button v-else type="submit" class="icon-button icon-button--send" aria-label="发送" :disabled="!canSubmit">
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M5 12h14m-7-7l7 7l-7 7"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
    </div>
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
      <span class="composer__hint">Enter 发送 · Shift + Enter 换行</span>
    </div>
  </form>
</template>
