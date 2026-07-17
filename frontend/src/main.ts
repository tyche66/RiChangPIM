import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './styles/design-system.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'

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
