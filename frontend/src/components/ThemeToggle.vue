<template>
  <button
    class="theme-toggle"
    :class="{ 'is-dark': isDark }"
    :title="isDark ? '切换到浅色模式' : '切换到深色模式'"
    :aria-pressed="isDark"
    @click="toggleTheme"
  >
    <el-icon :size="18">
      <Sunny v-if="isDark" />
      <Moon v-else />
    </el-icon>
  </button>
</template>

<script setup lang="ts">
import { Sunny, Moon } from '@element-plus/icons-vue'
import { useTheme, toggleTheme } from '@/composables/useTheme'

// 状态来自全局单例（useTheme.ts），切换即时生效并写入 localStorage。
const { isDark } = useTheme()
</script>

<style scoped>
.theme-toggle {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--pim-line-strong);
  border-radius: 10px;
  background: transparent;
  color: var(--pim-text-soft);
  cursor: pointer;
  transition: background-color 180ms ease, color 180ms ease;
}

.theme-toggle:hover {
  background: rgba(var(--pim-brand), 0.08);
  color: var(--pim-text-strong);
}

.theme-toggle:focus-visible {
  outline: 2px solid var(--pim-focus-ring);
  outline-offset: 1px;
}

.theme-toggle.is-dark {
  color: var(--pim-accent);
}
</style>
