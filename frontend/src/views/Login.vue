<!-- 与另一端登录页保持同步。 -->
<template>
  <div class="login-page">
    <main class="login-layout">
      <section class="brand-panel" aria-labelledby="brand-title">
        <video
          class="brand-video"
          autoplay
          muted
          loop
          playsinline
          preload="metadata"
          aria-hidden="true"
        >
          <source src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260813_052122_e77a27e6-17f1-4794-889b-3ceaa0e9e8cb.mp4" type="video/mp4" />
        </video>
        <div class="brand-scrim" aria-hidden="true" />
        <div class="hero-copy">
          <span class="hero-badge">为高效团队而生</span>
          <h2 id="brand-title">从灵感，到行动<br />即刻开始</h2>
          <p>统一管理产品、方案与知识资产，让每一次检索、选品和分享都更清晰。</p>
        </div>
        <div class="brand-caption" aria-hidden="true">
          <span class="caption-mark">PIM</span>
          <span>让每一次决策，都有清晰依据</span>
        </div>
      </section>

      <section class="login-side" aria-label="登录区域">
        <el-card class="login-card" shadow="never">
          <div class="form-heading">
            <img class="login-logo" :src="logoUrl" alt="RiChangPIM" />
            <h1>欢迎回来</h1>
            <p>工作辛苦了！欢迎再次登录到 AI选品/资料库后台</p>
          </div>

          <el-form
            ref="formRef"
            class="login-form"
            :model="form"
            :rules="rules"
            size="large"
            @keyup.enter="handleLogin"
          >
            <el-form-item prop="username">
              <label class="sr-only" for="admin-username">账号</label>
              <el-input
                id="admin-username"
                v-model="form.username"
                placeholder="请输入账号"
                autocomplete="username"
                type="text"
              />
            </el-form-item>
            <el-form-item prop="password">
              <label class="sr-only" for="admin-password">密码</label>
              <el-input
                id="admin-password"
                v-model="form.password"
                :type="showPassword ? 'text' : 'password'"
                placeholder="请输入密码"
                autocomplete="current-password"
              >
                <template #suffix>
                  <button
                    class="password-toggle"
                    type="button"
                    :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                    :aria-pressed="showPassword"
                    @click="showPassword = !showPassword"
                  >
                    <svg v-if="showPassword" viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M3 3l18 18M10.58 10.58A2 2 0 0 0 13.42 13.42M9.88 4.24A10.8 10.8 0 0 1 12 4c5 0 8.5 4 9.5 6a15.7 15.7 0 0 1-3.15 3.87M6.1 6.1C3.83 7.42 2.54 9.33 2.5 10c1 2 4.5 6 9.5 6 1.06 0 2.04-.16 2.94-.43" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7" />
                    </svg>
                    <svg v-else viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M2.5 12S6 6 12 6s9.5 6 9.5 6S18 18 12 18 2.5 12 2.5 12Z" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="1.7" />
                      <circle cx="12" cy="12" r="2.5" fill="none" stroke="currentColor" stroke-width="1.7" />
                    </svg>
                  </button>
                </template>
              </el-input>
            </el-form-item>
            <el-form-item class="submit-item">
              <el-button
                class="login-button"
                type="primary"
                native-type="button"
                :loading="loading"
                @click="handleLogin"
              >
                <span>登录</span>
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M5 12h13M13 6l6 6-6 6" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" />
                </svg>
              </el-button>
            </el-form-item>
          </el-form>

          <p v-if="loginError" class="login-error" role="alert" aria-live="polite">{{ loginError }}</p>
          <p class="register-prompt">
            <span>还没有账号？</span>
            <button type="button" @click="handleRegister">注册新账号</button>
          </p>
          <p class="security-note">企业级权限控制 · 数据安全传输</p>
        </el-card>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
/** 与门户端登录页保持同步。 */
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import logoUrl from '../../../logo/RiChangPIM.png'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const formRef = ref()
const loading = ref(false)
const showPassword = ref(false)
const loginError = ref('')

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
  loginError.value = ''
  loading.value = true
  try {
    await authStore.login(form.username, form.password)
    ElMessage.success('登录成功')
    const redirect = route.query.redirect as string
    router.push(redirect || '/products')
  } catch (e: any) {
    loginError.value = e.response?.data?.detail?.msg || '登录失败'
    ElMessage.error(loginError.value)
  } finally {
    loading.value = false
  }
}

const handleRegister = () => {
  // Registration is intentionally not part of this login-only flow.
}
</script>

<style scoped>
/* 与门户端登录页保持同步。 */
.login-page {
  min-height: 100vh;
  overflow-x: hidden;
  background: #f0f1f3;
  color: #252d3b;
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
}

.login-layout {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 57% 43%;
}

.brand-panel {
  position: relative;
  isolation: isolate;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  overflow: hidden;
  padding: clamp(36px, 6vw, 88px);
  color: #fff;
  background: linear-gradient(135deg, #102348 0%, #1e325a 54%, #0b1834 100%);
}

.brand-video,
.brand-scrim {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.brand-video {
  z-index: -2;
  display: block;
  object-fit: cover;
  object-position: center;
  background: linear-gradient(135deg, #102348 0%, #1e325a 54%, #0b1834 100%);
}

.brand-scrim {
  z-index: -1;
  background:
    linear-gradient(180deg, rgba(8, 20, 47, 0.12) 4%, rgba(7, 18, 42, 0.38) 58%, rgba(5, 15, 35, 0.82) 100%),
    linear-gradient(90deg, rgba(7, 19, 43, 0.32), transparent 72%);
}

.hero-copy {
  max-width: 650px;
  margin-top: auto;
  animation: login-rise 650ms ease both;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  padding: 8px 14px;
  border: 1px solid rgba(255, 255, 255, 0.24);
  border-radius: 999px;
  color: rgba(255, 255, 255, 0.88);
  background: rgba(255, 255, 255, 0.1);
  font-size: 13px;
  line-height: 1.4;
  backdrop-filter: blur(10px);
}

.hero-copy h2 {
  margin: 26px 0 20px;
  color: #fff;
  font-size: clamp(42px, 5.2vw, 76px);
  font-weight: 600;
  line-height: 1.16;
  letter-spacing: -0.055em;
}

.hero-copy p {
  max-width: 510px;
  color: rgba(255, 255, 255, 0.72);
  font-size: clamp(14px, 1.25vw, 17px);
  line-height: 1.85;
}

.brand-caption {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: clamp(60px, 12vh, 132px);
  color: rgba(255, 255, 255, 0.58);
  font-size: 12px;
  letter-spacing: 0.05em;
}

.caption-mark {
  display: inline-grid;
  place-items: center;
  min-width: 34px;
  height: 24px;
  padding: 0 7px;
  border: 1px solid rgba(255, 255, 255, 0.32);
  border-radius: 6px;
  color: rgba(255, 255, 255, 0.86);
  font-size: 10px;
  letter-spacing: 0.08em;
}

.login-side {
  min-width: 0;
  display: grid;
  place-items: center;
  padding: 32px clamp(22px, 4vw, 64px);
  background: #f0f1f3;
}

.login-card {
  width: min(520px, 100%);
  padding: clamp(30px, 4.2vw, 58px) clamp(26px, 4.4vw, 64px);
  border: 0;
  border-radius: 24px;
  background: #fff;
  box-shadow: 0 20px 56px rgba(30, 50, 90, 0.09);
  animation: login-rise 650ms 100ms ease both;
}

.login-card :deep(.el-card__body) {
  padding: 0;
}

.form-heading {
  margin-bottom: 32px;
}

.login-logo {
  display: block;
  width: 132px;
  height: auto;
  margin: 0 auto 22px;
  object-fit: contain;
}

.form-heading h1 {
  margin: 0;
  color: #1e325a;
  font-size: clamp(28px, 3vw, 36px);
  font-weight: 650;
  line-height: 1.25;
  letter-spacing: -0.045em;
  text-align: center;
}

.form-heading p {
  margin: 12px auto 0;
  max-width: 330px;
  color: #7a8290;
  font-size: 13px;
  line-height: 1.75;
  text-align: center;
}

.login-card :deep(.el-form-item) {
  margin-bottom: 18px;
}

.login-card :deep(.el-form-item__error) {
  padding-top: 5px;
  color: #b34b4b;
  font-size: 12px;
}

.login-card :deep(.el-input__wrapper) {
  min-height: 52px;
  padding: 0 16px;
  border: 1px solid #dfe3e9;
  border-radius: 12px;
  background: #fafbfc;
  box-shadow: none;
  transition: border-color 160ms ease, box-shadow 160ms ease, background-color 160ms ease;
}

.login-card :deep(.el-input__wrapper:hover) {
  border-color: #b9c4d3;
}

.login-card :deep(.el-input__wrapper.is-focus) {
  border-color: #1e325a;
  background: #fff;
  box-shadow: 0 0 0 3px rgba(30, 50, 90, 0.16);
}

.login-card :deep(.el-input__inner) {
  color: #252d3b;
  font-size: 15px;
}

.login-card :deep(.el-input__inner::placeholder) {
  color: #a2a9b3;
}

.password-toggle {
  display: inline-grid;
  place-items: center;
  width: 30px;
  height: 30px;
  padding: 4px;
  border-radius: 7px;
  color: #8b94a2;
  cursor: pointer;
}

.password-toggle:hover {
  color: #1e325a;
  background: #eef1f5;
}

.password-toggle:focus-visible,
.register-prompt button:focus-visible,
.login-button:focus-visible {
  outline: 3px solid rgba(30, 50, 90, 0.24);
  outline-offset: 2px;
}

.password-toggle svg,
.login-button svg {
  width: 19px;
  height: 19px;
}

.submit-item {
  margin-top: 8px;
}

.login-card :deep(.login-button) {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 100%;
  min-height: 52px;
  margin: 0;
  border: 0;
  border-radius: 12px;
  background: linear-gradient(110deg, #1e325a, #294575);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  box-shadow: 0 8px 18px rgba(30, 50, 90, 0.18);
  transition: background 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}

.login-card :deep(.login-button:hover) {
  border-color: transparent;
  background: linear-gradient(110deg, #172845, #213b68);
  box-shadow: 0 10px 22px rgba(30, 50, 90, 0.24);
}

.login-card :deep(.login-button:active) {
  transform: translateY(1px);
}

.register-prompt {
  display: flex;
  justify-content: center;
  gap: 5px;
  margin: 22px 0 0;
  color: #7a8290;
  font-size: 13px;
}

.login-error {
  margin: 13px 0 0;
  color: #b34b4b;
  font-size: 13px;
  line-height: 1.6;
  text-align: center;
}

.register-prompt button {
  padding: 0;
  color: #1e325a;
  font-weight: 600;
  cursor: pointer;
}

.register-prompt button:hover {
  color: #172845;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.security-note {
  margin: 30px 0 0;
  color: #a0a7b1;
  font-size: 11px;
  letter-spacing: 0.05em;
  text-align: center;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

@keyframes login-rise {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 959px) {
  .login-layout {
    display: block;
    min-height: 100vh;
  }

  .brand-panel {
    min-height: 300px;
    padding: 38px clamp(26px, 7vw, 72px) 48px;
  }

  .hero-copy h2 {
    margin: 18px 0 12px;
    font-size: clamp(38px, 7vw, 58px);
  }

  .brand-caption {
    display: none;
  }

  .login-side {
    position: relative;
    z-index: 1;
    width: min(680px, calc(100% - 48px));
    margin: -28px auto 0;
    padding: 0 0 42px;
  }

  .login-card {
    width: 100%;
  }
}

@media (max-width: 699px) {
  .brand-panel {
    min-height: 240px;
    padding: 28px 22px 34px;
  }

  .hero-badge {
    padding: 7px 11px;
    font-size: 12px;
  }

  .hero-copy h1 {
    margin: 15px 0 9px;
    font-size: clamp(32px, 10vw, 48px);
  }

  .hero-copy p {
    max-width: 440px;
    font-size: 13px;
    line-height: 1.65;
  }

  .login-side {
    width: 100%;
    margin-top: -18px;
    padding: 0 12px 28px;
  }

  .login-card {
    padding: 30px 20px 26px;
    border-radius: 18px;
  }

  .login-logo {
    width: 112px;
    height: auto;
    margin-bottom: 18px;
  }

  .form-heading {
    margin-bottom: 26px;
  }

  .form-heading h1 {
    font-size: 29px;
  }

  .form-heading p {
    font-size: 13px;
  }

  .login-card :deep(.el-input__wrapper),
  .login-card :deep(.login-button) {
    min-height: 48px;
  }

  .login-card :deep(.el-input__inner) {
    font-size: 16px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .hero-copy,
  .login-card {
    animation: none;
  }

  .login-card :deep(.el-input__wrapper),
  .login-card :deep(.login-button) {
    transition: none;
  }
}
</style>
