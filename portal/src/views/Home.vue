<script setup lang="ts">
/**
 * 登录页。只保留一件事：进入工作台。
 * 已登录时才显示示例问题，避免给未登录用户一排点不动的按钮。
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppHeader from '@/components/AppHeader.vue'
import ScopePanel from '@/components/ScopePanel.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

const username = ref('admin')
const password = ref('')
const error = ref('')
const busy = ref(false)

const prompts = ['找产品', '问资料', '查质量', '做比较']
const canSubmit = computed(() => Boolean(username.value.trim() && password.value) && !busy.value)

async function login() {
  if (!canSubmit.value) return
  error.value = ''
  busy.value = true
  try {
    await auth.signIn(username.value, password.value)
    await router.push('/chat')
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '登录失败'
  } finally {
    busy.value = false
  }
}

async function quickStart(prompt: string) {
  if (!auth.isAuthenticated) return
  await router.push({ path: '/chat', query: { q: prompt } })
}
</script>

<template>
  <AppHeader />

  <main class="auth-shell">
    <div class="auth-inner">
      <section class="auth-hero">
        <h1>RiChangPIM Portal</h1>
        <p>内部只读 AI 工作台。产品、资料和质量记录统一走 Knowledge Gateway，答案都带引用来源。</p>
      </section>

      <form class="auth-card" @submit.prevent="login">
        <h2>登录</h2>
        <label class="field">
          <span>账号</span>
          <input v-model="username" type="text" autocomplete="username" placeholder="admin" />
        </label>
        <label class="field">
          <span>密码</span>
          <input v-model="password" type="password" autocomplete="current-password" placeholder="请输入密码" />
        </label>
        <button type="submit" class="button button--primary button--block" :disabled="busy">进入 Portal</button>
        <p v-if="error" class="notice notice--error">{{ error }}</p>
        <p class="auth-card__hint">门户只做查询，写入类操作会先生成待确认动作，由你自己确认后才执行。</p>
      </form>

      <section v-if="auth.isAuthenticated" class="auth-hero">
        <p>也可以直接从一个常见问题开始</p>
        <ScopePanel :prompts="prompts" @pick="quickStart" />
      </section>
    </div>
  </main>
</template>
