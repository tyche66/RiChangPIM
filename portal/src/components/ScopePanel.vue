<script setup lang="ts">
/**
 * 登录页的示例问题。只是把问句预填到查询页，不代表任何筛选状态。
 */
defineProps<{ prompts: string[] }>()
const emit = defineEmits<{ pick: [prompt: string] }>()
</script>

<template>
  <div class="scope-panel" role="group" aria-label="示例问题">
    <button v-for="prompt in prompts" :key="prompt" type="button" class="chip" @click="emit('pick', prompt)">
      {{ prompt }}
    </button>
  </div>
</template>
