<template>
  <div class="login-page">
    <main class="login-shell">
      <section class="brand-panel">
        <div class="brand-lockup">
          <span class="brand-mark">AI</span>
          <span>AI-PIM</span>
        </div>
        <div class="hero-copy">
          <span class="hero-badge">PRODUCT INTELLIGENCE WORKSPACE</span>
          <h1>让产品数据，<br>成为增长语言。</h1>
          <p>统一管理产品、方案与知识资产，让每一次检索、选品和分享都更清晰。</p>
        </div>
        <div class="signal-card">
          <span class="signal-dot" />
          <div>
            <strong>业务与 AI 同步在线</strong>
            <small>Secure · Structured · Intelligent</small>
          </div>
        </div>
      </section>
      <el-card class="login-card">
        <div class="form-heading">
          <span class="form-kicker">WELCOME BACK</span>
          <h2>
            AI-PIM 产品信息管理平台
          </h2>
          <p>使用组织账号继续访问产品信息空间</p>
        </div>
        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          size="large"
          @keyup.enter="handleLogin"
        >
          <el-form-item prop="username">
            <el-input
              v-model="form.username"
              placeholder="用户名"
            />
          </el-form-item>
          <el-form-item prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="密码"
              show-password
            />
          </el-form-item>
          <el-form-item>
            <el-button
              type="primary"
              :loading="loading"
              style="width: 100%"
              @click="handleLogin"
            >
              登录
            </el-button>
          </el-form-item>
        </el-form>
        <p class="security-note">
          企业级权限控制 · 数据安全传输
        </p>
      </el-card>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const formRef = ref()
const loading = ref(false)

const form = reactive({
  username: '',
  password: '',
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const handleLogin = async () => {
  await formRef.value.validate()
  loading.value = true
  try {
    await authStore.login(form.username, form.password)
    ElMessage.success('登录成功')
    const redirect = route.query.redirect as string
    router.push(redirect || '/products')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail?.msg || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: clamp(12px, 2vw, 24px);
  background:
    radial-gradient(circle at 85% 12%, rgba(30, 50, 90, 0.12), transparent 26rem),
    #f0f0f0;
}

.login-shell {
  width: min(1180px, 100%);
  min-height: min(760px, calc(100vh - 48px));
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(360px, 0.65fr);
  border-radius: 44px;
  background: rgba(255, 255, 255, 0.18);
  box-shadow: 0 28px 90px rgba(30, 50, 90, 0.12);
  overflow: hidden;
}

.brand-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  padding: clamp(28px, 5vw, 68px);
  color: #fff;
  background:
    radial-gradient(circle at 78% 22%, rgba(255, 255, 255, 0.16), transparent 16rem),
    radial-gradient(circle at 24% 90%, rgba(255, 255, 255, 0.09), transparent 20rem),
    rgb(30, 50, 90);
}

.brand-lockup {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 15px;
  letter-spacing: 0.08em;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.14);
  font-size: 12px;
}

.hero-copy {
  margin: auto 0;
  max-width: 630px;
  animation: rise-in 700ms ease both;
}

.hero-badge,
.form-kicker {
  font-size: 10px;
  letter-spacing: 0.16em;
}

.hero-badge {
  display: inline-flex;
  padding: 9px 14px;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 999px;
  color: rgba(255, 255, 255, 0.68);
  background: rgba(255, 255, 255, 0.08);
}

.hero-copy h1 {
  margin: 28px 0 22px;
  font-size: clamp(46px, 5.3vw, 76px);
  font-weight: 400;
  line-height: 1.05;
  letter-spacing: -0.055em;
}

.hero-copy p {
  max-width: 500px;
  color: rgba(255, 255, 255, 0.62);
  font-size: 16px;
  line-height: 1.8;
}

.signal-card {
  width: fit-content;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(16px);
}

.signal-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #b9e4d2;
  box-shadow: 0 0 0 6px rgba(185, 228, 210, 0.1);
}

.signal-card div {
  display: grid;
  gap: 3px;
}

.signal-card strong {
  font-size: 12px;
  font-weight: 400;
}

.signal-card small {
  color: rgba(255, 255, 255, 0.42);
  font-size: 9px;
  letter-spacing: 0.08em;
}

.login-card {
  align-self: center;
  width: calc(100% - 48px);
  margin: 24px;
  padding: clamp(14px, 2vw, 28px);
  border-radius: 32px;
  animation: rise-in 700ms 180ms ease both;
}

.form-heading {
  margin-bottom: 34px;
}

.form-kicker {
  color: rgba(30, 50, 90, 0.45);
}

.form-heading h2 {
  margin: 12px 0 8px;
  color: rgba(30, 50, 90, 0.9);
  font-size: 32px;
  font-weight: 400;
  letter-spacing: -0.04em;
}

.form-heading p,
.security-note {
  color: rgba(30, 50, 90, 0.52);
}

.form-heading p {
  font-size: 13px;
  line-height: 1.7;
}

.login-card :deep(.el-form-item) {
  margin-bottom: 20px;
}

.login-card :deep(.el-input__wrapper) {
  min-height: 50px;
  padding: 0 16px;
  border-radius: 16px;
}

.login-card :deep(.el-button) {
  min-height: 50px;
  margin-top: 6px;
}

.security-note {
  margin-top: 6px;
  text-align: center;
  font-size: 10px;
  letter-spacing: 0.05em;
}

@keyframes rise-in {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 820px) {
  .login-shell {
    grid-template-columns: 1fr;
    min-height: auto;
    border-radius: 32px;
  }

  .brand-panel {
    min-height: 300px;
    padding: 28px;
  }

  .hero-copy {
    margin: 54px 0 22px;
  }

  .hero-copy h1 {
    margin: 18px 0 14px;
    font-size: clamp(38px, 10vw, 58px);
  }

  .signal-card {
    display: none;
  }

  .login-card {
    width: auto;
  }
}

@media (max-width: 480px) {
  .login-page {
    align-items: flex-start;
    padding: 8px;
  }

  .login-shell {
    border-radius: 26px;
  }

  .brand-panel {
    min-height: 270px;
    padding: 24px;
  }

  .hero-copy {
    margin-top: 42px;
  }

  .hero-copy p {
    font-size: 13px;
  }

  .login-card {
    margin: 10px;
    padding: 16px 10px;
    box-shadow: none;
  }

  .form-heading {
    margin-bottom: 24px;
  }
}
</style>
