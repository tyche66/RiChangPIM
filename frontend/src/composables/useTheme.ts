/**
 * 主题状态（浅色 / 深色 / 跟随系统）。
 *
 * 与旧实现的区别：
 * - 不再由 ThemeToggle 在 onMounted 里补挂 class：main.ts 在挂载 Vue 前就
 *   调用 applyTheme()，登录页、分享页这些没有 ThemeToggle 的界面也能第一帧
 *   就是正确的主题，不会出现「先浅后深」的闪烁；
 * - 'system' 时注册 matchMedia 监听，系统主题变化会实时改写 html 类；
 * - 主题是全局单例（模块级 ref），侧边栏开关、门户 iframe（同源共享
 *   localStorage + storage 事件）看到的都是同一份状态。
 *
 * 持久化键沿用 localStorage 的 'theme'，值：'light' | 'dark' | 'system'。
 */
import { ref, type Ref } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'theme'
const DARK_CLASS = 'dark-mode'

const prefersDark = () =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-color-scheme: dark)').matches

/** 读取存储的偏好；没有记录时返回 'system'（跟随系统）。 */
const readStored = (): ThemeMode => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'dark' || saved === 'light' || saved === 'system') return saved
  } catch {
    /* 隐私模式下 localStorage 可能抛错，忽略即可 */
  }
  return 'system'
}

const mode: Ref<ThemeMode> = ref<ThemeMode>('system')
const isDark: Ref<boolean> = ref(false)

/** 把当前偏好落到 <html> 类与 localStorage。 */
export const applyTheme = (next: ThemeMode = mode.value) => {
  mode.value = next
  const dark = next === 'dark' || (next === 'system' && prefersDark())
  isDark.value = dark
  const root = document.documentElement
  root.classList.toggle(DARK_CLASS, dark)
  try {
    localStorage.setItem(STORAGE_KEY, next)
  } catch {
    /* 忽略写入失败 */
  }
}

/** 在系统主题变化且当前处于 'system' 时同步界面。 */
const watchSystem = () => {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
  const mq = window.matchMedia('(prefers-color-scheme: dark)')
  mq.addEventListener('change', () => {
    if (mode.value === 'system') applyTheme('system')
  })
}

/** 供 useTheme() 使用的响应式主题状态。 */
export function useTheme() {
  return { mode, isDark }
}

/** 初始化：读偏好 → 落 class → 监听系统变化。main.ts 挂载前调用一次。 */
export function initTheme() {
  applyTheme(readStored())
  watchSystem()
}

/** 供侧边栏开关调用：light ↔ dark 直接切换。 */
export const toggleTheme = () => applyTheme(isDark.value ? 'light' : 'dark')
