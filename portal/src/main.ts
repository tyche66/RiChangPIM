import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { adoptParentSession, applyEmbedChrome } from './utils/embed'
import './styles/main.css'

// 被后台 iframe 嵌入时先把登录态接过来再挂载，否则路由守卫会先判定未登录。
adoptParentSession().then(() => {
  applyEmbedChrome()
  const app = createApp(App)
  app.use(createPinia())
  app.use(router)
  app.mount('#app')
})
