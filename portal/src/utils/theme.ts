/**
 * 门户主题（浅色 / 深色 / 跟随系统）。
 *
 * 门户是独立 SPA，但和后宫后台同源（都挂在 localhost:888 下）：
 * - 存/读同一个 localStorage 键 'theme'，与后台偏好一致；
 * - 额外监听 storage 事件：后台切主题时，被 iframe 嵌入聊天工作台的门户
 *   文档会同步换肤（iframe 文档各自持有自己的 <html> 类）；
 * - 监听系统偏好变化，'system' 下实时响应。
 *
 * 应用方式与后台相同：<html> 上加 class="dark-mode"，由 main.css 的
 * .dark-mode Token 块接管全部颜色。
 */
import { ref } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'theme'
const DARK_CLASS = 'dark-mode'

const prefersDark = () =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-color-scheme: dark)').matches

export const isDark = ref(false)
export const themeMode = ref<ThemeMode>('system')

export function applyTheme(mode: ThemeMode = themeMode.value) {
  themeMode.value = mode
  const dark = mode === 'dark' || (mode === 'system' && prefersDark())
  isDark.value = dark
  document.documentElement.classList.toggle(DARK_CLASS, dark)
  try {
    localStorage.setItem(STORAGE_KEY, mode)
  } catch {
    /* 隐私模式下忽略 */
  }
}

export function initTheme() {
  let saved: string | null = null
  try {
    saved = localStorage.getItem(STORAGE_KEY)
  } catch {
    /* 忽略 */
  }
  applyTheme(saved === 'dark' || saved === 'light' || saved === 'system' ? saved : 'system')

  // 系统主题变化
  if (typeof window.matchMedia === 'function') {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
      if (themeMode.value === 'system') applyTheme('system')
    })
  }
  // 后台（同源另一个文档）切了主题 → 这里跟着切，iframe 嵌入时尤其重要
  window.addEventListener('storage', (e) => {
    if (e.key !== STORAGE_KEY) return
    const v = e.newValue
    applyTheme(v === 'dark' || v === 'light' || v === 'system' ? v : 'system')
  })
}

export function toggleTheme() {
  applyTheme(isDark.value ? 'light' : 'dark')
}
