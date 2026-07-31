<template>
  <section class="version-page">
    <header class="version-hero">
      <div>
        <span class="eyebrow">DEPLOYMENT FINGERPRINT</span>
        <h2>版本信息</h2>
        <p>核对浏览器中的前端构建与当前运行的后台服务。</p>
      </div>
      <el-button
        type="primary"
        :loading="loading"
        class="check-button"
        @click="checkVersion"
      >
        重新检查
      </el-button>
    </header>

    <el-card
      v-if="error"
      class="status-card error-card"
      shadow="never"
    >
      <el-result
        icon="error"
        title="无法获取后台版本"
        sub-title="版本服务暂时不可用，请稍后重试"
      >
        <template #extra>
          <el-button
            type="primary"
            :loading="loading"
            @click="checkVersion"
          >
            重试
          </el-button>
        </template>
      </el-result>
    </el-card>

    <template v-else>
      <el-card
        v-loading="loading"
        class="status-card"
        shadow="never"
      >
        <div class="status-line">
          <div>
            <span class="status-kicker">一致性检查</span>
            <strong>{{ statusCopy.title }}</strong>
            <small>{{ statusCopy.detail }}</small>
          </div>
          <el-tag
            :type="statusCopy.type"
            size="large"
            effect="dark"
          >
            {{ statusCopy.title }}
          </el-tag>
        </div>
      </el-card>

      <div class="build-grid">
        <el-card
          class="build-card frontend"
          shadow="never"
        >
          <template #header>
            <span>FRONTEND</span><strong>前端构建</strong>
          </template>
          <dl>
            <div><dt>版本</dt><dd>{{ formatValue(frontendBuild.version) }}</dd></div>
            <div><dt>构建 ID</dt><dd>{{ formatValue(frontendBuild.buildId) }}</dd></div>
            <div><dt>Git commit</dt><dd>{{ formatValue(frontendBuild.gitCommit) }}</dd></div>
            <div><dt>构建时间</dt><dd>{{ formatValue(frontendBuild.buildTime) }}</dd></div>
          </dl>
        </el-card>
        <el-card
          class="build-card backend"
          shadow="never"
        >
          <template #header>
            <span>BACKEND</span><strong>后台运行实例</strong>
          </template>
          <dl>
            <div><dt>版本</dt><dd>{{ formatValue(backend?.backend_version) }}</dd></div>
            <div><dt>构建 ID</dt><dd>{{ formatValue(backend?.build_id) }}</dd></div>
            <div><dt>Git commit</dt><dd>{{ formatValue(backend?.git_commit) }}</dd></div>
            <div><dt>构建时间</dt><dd>{{ formatValue(backend?.build_time) }}</dd></div>
            <div><dt>环境</dt><dd>{{ formatValue(backend?.environment) }}</dd></div>
            <div><dt>API</dt><dd>{{ formatValue(backend?.api_version) }}</dd></div>
          </dl>
        </el-card>
      </div>
      <p class="checked-at">
        最后检查时间：{{ lastChecked || '尚未完成检查' }}
      </p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { versionApi } from '@/api'
import { compareBuilds, frontendBuild } from '@/config/version'

type BackendVersion = {
  backend_version: string
  build_id: string
  git_commit: string
  build_time: string
  environment: string
  api_version: string
}

const backend = ref<BackendVersion | null>(null)
const loading = ref(false)
const error = ref(false)
const lastChecked = ref('')

function formatValue(value: string | undefined | null): string {
  if (!value || value === 'unknown' || value === 'undefined' || value === 'dev' || value === 'dev-local') {
    return '—'
  }
  return value
}

const comparison = computed<'match' | 'mismatch' | 'unknown'>(() => {
  if (!backend.value) return 'unknown'
  return compareBuilds(frontendBuild, backend.value)
})

const statusCopy = computed(() => {
  if (comparison.value === 'match') return { title: '版本一致', detail: '前端与后台来自同一构建。', type: 'success' as const }
  if (comparison.value === 'mismatch') return { title: '前后端版本不一致', detail: '请核对双方构建值并重新部署旧的一端。', type: 'danger' as const }
  return { title: '缺少构建信息，无法确认', detail: '请在构建流程中注入版本、构建 ID 或 Git commit。', type: 'warning' as const }
})

async function checkVersion() {
  loading.value = true
  error.value = false
  try {
    const response = await versionApi.get() as any
    backend.value = response.data
    lastChecked.value = new Date().toLocaleString('zh-CN')
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

onMounted(checkVersion)
</script>

<style scoped>
/*
 * 颜色和字体一律走 design-system.css 的设计变量：品牌蓝 --pim-primary / --pim-brand-lift，
 * 铜色副色 --pim-accent* （版本页是全站唯一用铜色的地方），文字层级 --pim-text-strong /
 * --pim-text-soft，描线 --pim-line。等宽字体走 --pim-font-mono（鸿蒙优先），
 * 原先的 ui-monospace 链在 Windows 上会掉成 Courier New，跟正文字体对不上。
 */
.version-page { display: grid; gap: 20px; max-width: 1180px; margin: 0 auto; }
.version-hero { display: flex; align-items: end; justify-content: space-between; padding: 30px 34px; border-radius: 28px; color: white; background: linear-gradient(125deg, var(--pim-primary) 0%, var(--pim-brand-lift) 60%, var(--pim-accent-mid) 140%); box-shadow: 0 24px 60px rgba(var(--pim-brand), .18); }
.eyebrow { font-size: 11px; letter-spacing: .18em; opacity: .65; }
h2 { margin: 8px 0; font-size: 34px; } p { margin: 0; opacity: .78; }
.check-button { border: 0; background: var(--pim-accent); }
.status-card, .build-card { border: 1px solid rgba(var(--pim-brand), .1); border-radius: 24px; }
.status-line { display: flex; align-items: center; justify-content: space-between; gap: 24px; }
.status-line > div { display: grid; gap: 5px; }.status-line strong { font-size: 22px; }.status-line small { color: var(--pim-text-soft); }
.status-kicker { color: var(--pim-accent-deep); font-size: 11px; font-weight: 700; letter-spacing: .14em; }
.build-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.build-card :deep(.el-card__header) { display: flex; align-items: baseline; gap: 12px; border: 0; }
.build-card :deep(.el-card__header) span { font-size: 11px; letter-spacing: .16em; color: var(--pim-accent-deep); }
.build-card :deep(.el-card__header) strong { font-size: 20px; color: var(--pim-primary); }
dl { margin: 0; } dl div { display: grid; grid-template-columns: 110px 1fr; gap: 12px; padding: 14px 0; border-top: 1px solid var(--pim-line); }
dt { color: var(--pim-text-soft); } dd { margin: 0; color: var(--pim-text-strong); font-family: var(--pim-font-mono); overflow-wrap: anywhere; }
.frontend { border-top: 4px solid var(--pim-accent); }.backend { border-top: 4px solid var(--pim-brand-lift); }.checked-at { text-align: right; color: var(--pim-text-soft); font-size: 13px; }
@media (max-width: 720px) { .version-hero { align-items: stretch; flex-direction: column; gap: 22px; padding: 24px; } .build-grid { grid-template-columns: 1fr; } .status-line { align-items: flex-start; flex-direction: column; } dl div { grid-template-columns: 90px 1fr; } }
</style>
