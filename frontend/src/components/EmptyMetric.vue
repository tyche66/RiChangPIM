<template>
  <span
    class="empty-metric"
    :class="{ 'is-empty': isEmpty }"
  >
    <template v-if="!isEmpty">{{ display }}</template>
    <span
      v-else
      class="empty-metric__hint"
    >{{ hint }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/**
 * 指标空态统一渲染（HLD §11.3）。
 * 无数据 / 无权限 / 未启用一律显示文案，绝不用 0 占位。
 */
const props = withDefaults(
  defineProps<{
    value?: number | string | null
    reason?: string | null
    unit?: string
    currency?: boolean
  }>(),
  {
    value: null,
    reason: null,
    unit: '',
    currency: false,
  },
)

const isEmpty = computed(
  () => props.value === null || props.value === undefined || props.value === '',
)

const hint = computed(() => {
  switch (props.reason) {
    case 'no_permission':
      return '无权限'
    case 'module_disabled':
      return '未启用'
    case 'no_data':
      return '待录入'
    default:
      return '待录入'
  }
})

const display = computed(() => {
  const raw = props.value
  if (props.currency && typeof raw === 'number') {
    return `¥${raw.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }
  return `${raw}${props.unit}`
})
</script>

<style scoped>
.empty-metric {
  font-variant-numeric: tabular-nums;
}

.empty-metric__hint {
  color: var(--pim-text-secondary);
  font-size: 0.85em;
  font-weight: 400;
  letter-spacing: 0.02em;
}
</style>
