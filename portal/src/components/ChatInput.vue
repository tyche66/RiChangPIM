<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{ busy: boolean }>()
const emit = defineEmits<{ submit: [message: string]; stop: [] }>()

const value = ref('')
const promptChips = ['办公桌', '会议桌', '安装资料', '质量记录']
const canSubmit = computed(() => Boolean(value.value.trim()) && !props.busy)

function pickPrompt(prompt: string) {
  value.value = value.value.trim() ? `${value.value.trim()} ${prompt}` : prompt
}

function submit() {
  const message = value.value.trim()
  if (!message || props.busy) return
  emit('submit', message)
  value.value = ''
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    if (props.busy) {
      emit('stop')
      return
    }
    submit()
  }
}
</script>

<template>
  <div class="chat-input">
    <label class="sr-only" for="ai-query">AI 查询</label>
    <textarea id="ai-query" v-model="value" rows="3" placeholder="输入产品搜索、问资料、查质量或做比较" @keydown="onKeydown" />
    <div class="chat-input__actions">
      <div class="composer-chips" aria-label="快捷产品类型">
        <button v-for="prompt in promptChips" :key="prompt" type="button" class="chip" @click="pickPrompt(prompt)">
          {{ prompt }}
        </button>
      </div>
      <button v-if="busy" type="button" class="button button--secondary" @click="$emit('stop')">停止</button>
      <button v-else type="button" class="button button--primary" :disabled="!canSubmit" @click="submit">发送</button>
    </div>
  </div>
</template>
