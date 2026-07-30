<script setup lang="ts">
/**
 * 待确认动作卡。只读门户不会自己写库，确认按钮是唯一的写入触发点，
 * 所以状态、方案名和过期时间必须用业务语言说清楚。
 */
import { computed } from 'vue'
import type { PendingAction } from '@/api'
import CollapseSection from './CollapseSection.vue'
import { actionStatusLabel, actionTypeLabel, formatDateTime } from '@/utils/format'

const props = withDefaults(defineProps<{ action: PendingAction; busy?: boolean }>(), { busy: false })
defineEmits<{ confirm: [action: PendingAction] }>()

const CONFIRMABLE = ['pending', 'proposed']

const proposalName = computed(() => String(props.action.payload.proposal_name || 'AI 方案草稿'))
const itemCount = computed(() => {
  const items = props.action.payload.items
  return Array.isArray(items) ? items.length : 0
})
const expiresAt = computed(() => formatDateTime(props.action.expires_at) || '未设置有效期')
const canConfirm = computed(() => CONFIRMABLE.includes(props.action.status))
const statusTone = computed(() => {
  if (props.action.status === 'succeeded' || props.action.status === 'confirmed') return 'status-pill--ok'
  if (canConfirm.value || props.action.status === 'executing') return 'status-pill--warn'
  return ''
})
</script>

<template>
  <article class="pending-action">
    <div class="panel__header">
      <div class="panel__title">
        <h2>{{ actionTypeLabel(action.action_type) }}</h2>
        <span class="status-pill" :class="statusTone">{{ actionStatusLabel(action.status) }}</span>
      </div>
      <button
        type="button"
        class="button button--primary"
        :disabled="busy || !canConfirm"
        @click="$emit('confirm', action)"
      >
        确认执行
      </button>
    </div>
    <div class="kv-grid">
      <span>方案名称</span>
      <strong>{{ proposalName }}</strong>
      <span>包含产品</span>
      <strong>{{ itemCount }} 个</strong>
      <span>有效期至</span>
      <strong>{{ expiresAt }}</strong>
    </div>
    <CollapseSection v-if="action.result" title="执行结果" quiet>
      <div class="raw-json">
        <div class="raw-json__row">{{ JSON.stringify(action.result) }}</div>
      </div>
    </CollapseSection>
  </article>
</template>
