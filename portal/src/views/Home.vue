<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import ScopePanel from '@/components/ScopePanel.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const username = ref('admin')
const password = ref('')
const error = ref('')

const prompts = ['找产品', '问资料', '查质量', '做比较']

async function login() {
  error.value = ''
  try {
    await auth.signIn(username.value, password.value)
    await router.push('/chat')
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '登录失败'
  }
}

async function quickStart(prompt: string) {
  if (!auth.isAuthenticated) return
  await router.push({ path: '/chat', query: { q: prompt } })
}
</script>

<template>
  <main class="home-shell">
    <section class="hero-band">
      <div>
        <h1>RiChangPIM Portal</h1>
        <p>内部只读 AI 工作台。统一走 Knowledge Gateway。</p>
      </div>
      <ScopePanel :prompts="prompts" @pick="quickStart" />
    </section>

    <section class="home-grid">
      <div class="login-panel">
        <h2>登录</h2>
        <label>
          <span>账号</span>
          <input v-model="username" type="text" placeholder="admin" />
        </label>
        <label>
          <span>密码</span>
          <input v-model="password" type="password" placeholder="请输入密码" @keydown.enter="login" />
        </label>
        <button type="button" class="button button--primary" @click="login">进入 Portal</button>
        <p v-if="error" class="error-text">{{ error }}</p>
      </div>
    </section>
  </main>
</template>
