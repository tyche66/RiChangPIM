import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { adoptParentSession, applyEmbedChrome } from './utils/embed'
import { initTheme } from './utils/theme'
import './styles/main.css'

// 挂载前先按存储/系统偏好落好 <html> 的 dark-mode 类，避免首帧浅色闪烁。
initTheme()

// 被后台 iframe 嵌入时先把登录态接过来再挂载，否则路由守卫会先判定未登录。
adoptParentSession().then(() => {
  applyEmbedChrome()
  const app = createApp(App)
  app.use(createPinia())
  app.use(router)
  app.mount('#app')
})
