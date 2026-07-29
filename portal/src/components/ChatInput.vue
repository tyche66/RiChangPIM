<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{ busy: boolean }>()
const emit = defineEmits<{ submit: [message: string]; stop: [] }>()

const value = ref('')
const canSubmit = computed(() => Boolean(value.value.trim()) && !props.busy)

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
    <textarea id="ai-query" v-model="value" rows="2" placeholder="输入产品搜索、问资料、查质量或做比较" @keydown="onKeydown" />
    <div class="chat-input__actions">
      <button v-if="busy" type="button" class="button button--secondary" @click="$emit('stop')">停止</button>
      <button v-else type="button" class="button button--primary" :disabled="!canSubmit" @click="submit">发送</button>
    </div>
  </div>
</template>
