<script setup lang="ts">
defineProps<{ prompts: string[] }>()
const emit = defineEmits<{ pick: [prompt: string] }>()
</script>

<template>
  <div class="scope-panel">
    <button v-for="prompt in prompts" :key="prompt" type="button" class="button button--secondary" @click="emit('pick', prompt)">
      {{ prompt }}
    </button>
  </div>
</template>
