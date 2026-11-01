import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { useSettingsStore } from './stores/settings'
import { adoptParentSession, applyEmbedChrome } from './utils/embed'
import { initTheme } from './utils/theme'
import './styles/main.css'

// 挂载前先按存储/系统偏好落好 <html> 的 dark-mode 类，避免首帧浅色闪烁。
initTheme()

// 被后台 iframe 嵌入时先把登录态接过来再挂载，否则路由守卫会先判定未登录。
adoptParentSession().then(() => {
  applyEmbedChrome()
  const app = createApp(App)
  const pinia = createPinia()
  app.use(pinia)
  app.use(router)
  app.mount('#app')
  // 公共品牌设置（FR-3）：只加载一次、不 await——失败回落硬编码文案，
  // 绝不阻塞挂载或白屏。store 成功后会顺带更新浏览器标题。
  useSettingsStore().load()
})
