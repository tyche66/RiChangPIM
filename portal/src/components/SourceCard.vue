<script setup lang="ts">
import type { KnowledgeSource } from '@/api'

defineProps<{ source: KnowledgeSource }>()
const emit = defineEmits<{ open: [sourceId: string] }>()
</script>

<template>
  <article class="source-card">
    <div class="source-card__header">
      <div>
        <p class="source-card__type">{{ source.source_type }}</p>
        <h3>{{ source.title }}</h3>
      </div>
      <button type="button" class="button button--secondary" @click="emit('open', source.source_id)">打开</button>
    </div>
    <p class="muted-text">{{ source.section || 'section: -' }} <span v-if="source.page">p.{{ source.page }}</span></p>
    <p class="source-card__quote">{{ source.quote || '无可展示正文' }}</p>
  </article>
</template>
