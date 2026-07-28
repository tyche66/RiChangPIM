<script setup lang="ts">
import type { PendingAction } from '@/api'

defineProps<{ action: PendingAction; busy?: boolean }>()
defineEmits<{ confirm: [action: PendingAction] }>()

function actionLabel(type: string) {
  if (type === 'proposal.create_draft') return '创建方案草稿'
  if (type === 'proposal.update_draft') return '更新方案草稿'
  return type
}

function itemCount(action: PendingAction) {
  const items = action.payload.items
  return Array.isArray(items) ? items.length : 0
}
</script>

<template>
  <article class="pending-action">
    <div class="panel__header">
      <div>
        <p class="eyebrow">Pending action</p>
        <h2>{{ actionLabel(action.action_type) }}</h2>
        <span class="status-pill">{{ action.status }}</span>
      </div>
      <button type="button" class="button button--primary" :disabled="busy || action.status !== 'pending'" @click="$emit('confirm', action)">
        确认
      </button>
    </div>
    <div class="kv-grid">
      <span>方案</span>
      <strong>{{ String(action.payload.proposal_name || 'AI 方案草稿') }}</strong>
      <span>产品数</span>
      <strong>{{ itemCount(action) }}</strong>
      <span>过期</span>
      <strong>{{ action.expires_at || '-' }}</strong>
    </div>
    <p v-if="action.result" class="muted-text">{{ JSON.stringify(action.result) }}</p>
  </article>
</template>
