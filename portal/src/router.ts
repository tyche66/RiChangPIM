import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', component: () => import('@/views/Home.vue') },
    { path: '/chat', component: () => import('@/views/Conversation.vue') },
    // 公开分享页。后端生成的链接形如 /share/{token}（backend/app/api/v1/shares.py），
    // 由 nginx 的 location /（门户）接住，不能落到后台的 /admin/ 里。
    {
      path: '/share/:token',
      name: 'SharePage',
      component: () => import('@/views/SharePage.vue'),
      meta: { public: true },
    },
    // 有人只贴了 /share 而没带 token 时给一个说明页，而不是白屏。
    {
      path: '/share',
      name: 'ShareMissingToken',
      component: () => import('@/views/SharePage.vue'),
      meta: { public: true },
    },
  ],
})

router.beforeEach(async (to, _from, next) => {
  // 公开页（分享链接）不碰登录态：访客天然没有后台账号，
  // 这里跑 auth.init() 只会为一个过期 token 白发一次 refresh 请求。
  if (to.meta.public) {
    next()
    return
  }
  const auth = useAuthStore()
  if (!auth.initialized) {
    await auth.init()
  }
  if (to.path === '/chat' && !auth.isAuthenticated) {
    next('/')
    return
  }
  next()
})

export default router
