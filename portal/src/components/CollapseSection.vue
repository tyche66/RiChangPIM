<script setup lang="ts">
/**
 * 可折叠区块。用原生 details/summary，键盘与辅助技术行为不需要自己实现。
 * 默认收起：只有确实需要排障的人才会展开。
 */
withDefaults(
  defineProps<{
    title: string
    hint?: string
    open?: boolean
    quiet?: boolean
  }>(),
  { hint: '', open: false, quiet: false },
)
</script>

<template>
  <details class="collapse" :class="{ 'collapse--quiet': quiet }" :open="open">
    <summary class="collapse__summary">
      <span class="collapse__chevron" aria-hidden="true">
        <svg viewBox="0 0 16 16" fill="none">
          <path d="M6 3.5 10.5 8 6 12.5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </span>
      <span>{{ title }}</span>
      <span v-if="hint" class="collapse__hint">{{ hint }}</span>
    </summary>
    <div class="collapse__body">
      <slot />
    </div>
  </details>
</template>
