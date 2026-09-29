<template>
  <button
    class="theme-toggle"
    :class="{ 'is-dark': isDark }"
    :title="isDark ? '切换到浅色模式' : '切换到深色模式'"
    @click="toggleTheme"
  >
    <el-icon :size="18">
      <Sunny v-if="isDark" />
      <Moon v-else />
    </el-icon>
  </button>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { Sunny, Moon } from '@element-plus/icons-vue'

const isDark = ref(false)

const applyTheme = (dark: boolean) => {
  if (dark) {
    document.documentElement.classList.add('dark-mode')
  } else {
    document.documentElement.classList.remove('dark-mode')
  }
  localStorage.setItem('theme', dark ? 'dark' : 'light')
}

const toggleTheme = () => {
  isDark.value = !isDark.value
  applyTheme(isDark.value)
}

onMounted(() => {
  const saved = localStorage.getItem('theme')
  if (saved === 'dark') {
    isDark.value = true
  } else if (saved === 'light') {
    isDark.value = false
  } else {
    isDark.value = window.matchMedia('(prefers-color-scheme: dark)').matches
  }
  applyTheme(isDark.value)
})

watch(isDark, (val) => {
  applyTheme(val)
})
</script>

<style scoped>
.theme-toggle {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border: 1px solid rgba(var(--pim-brand), 0.12);
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

.theme-toggle.is-dark {
  color: var(--pim-accent);
}
</style>