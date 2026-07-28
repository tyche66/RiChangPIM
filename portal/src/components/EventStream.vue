<script setup lang="ts">
defineProps<{ events: Array<{ event: string; data: Record<string, unknown> }> }>()
</script>

<template>
  <div class="event-stream" aria-live="polite">
    <div v-for="item in events" :key="`${item.event}-${JSON.stringify(item.data)}`" class="event-stream__row">
      <span>{{ item.event }}</span>
      <span>{{ JSON.stringify(item.data) }}</span>
    </div>
  </div>
</template>
