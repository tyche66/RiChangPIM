import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './styles/design-system.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'
import { initTheme } from './composables/useTheme'

// 在 Vue 挂载前就按存储/系统偏好落好 <html> 的 dark-mode 类：
// 登录页、分享页没有 ThemeToggle，晚一步挂 class 会先闪一帧浅色。
initTheme()

const app = createApp(App)

const pinia = createPinia()
app.use(pinia)

// Initialize auth state (token validation + user info) before mounting.
const authStore = useAuthStore()
authStore.init().finally(() => {
  app.use(router)
  app.use(ElementPlus, { locale: zhCn })
  app.mount('#app')
})
