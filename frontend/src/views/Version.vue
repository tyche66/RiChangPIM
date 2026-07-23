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
            <div><dt>版本</dt><dd>{{ frontendBuild.version }}</dd></div>
            <div><dt>构建 ID</dt><dd>{{ frontendBuild.buildId }}</dd></div>
            <div><dt>Git commit</dt><dd>{{ frontendBuild.gitCommit }}</dd></div>
            <div><dt>构建时间</dt><dd>{{ frontendBuild.buildTime }}</dd></div>
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
            <div><dt>版本</dt><dd>{{ backend?.backend_version || 'unknown' }}</dd></div>
            <div><dt>构建 ID</dt><dd>{{ backend?.build_id || 'unknown' }}</dd></div>
            <div><dt>Git commit</dt><dd>{{ backend?.git_commit || 'unknown' }}</dd></div>
            <div><dt>构建时间</dt><dd>{{ backend?.build_time || 'unknown' }}</dd></div>
            <div><dt>环境</dt><dd>{{ backend?.environment || 'unknown' }}</dd></div>
            <div><dt>API</dt><dd>{{ backend?.api_version || 'unknown' }}</dd></div>
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
.version-page { display: grid; gap: 20px; max-width: 1180px; margin: 0 auto; }
.version-hero { display: flex; align-items: end; justify-content: space-between; padding: 30px 34px; border-radius: 28px; color: white; background: linear-gradient(125deg, #1e325a 0%, #294c7d 60%, #b56d3d 140%); box-shadow: 0 24px 60px rgba(30, 50, 90, .18); }
.eyebrow { font-size: 11px; letter-spacing: .18em; opacity: .65; }
h2 { margin: 8px 0; font-size: 34px; } p { margin: 0; opacity: .78; }
.check-button { border: 0; background: #e68b51; }
.status-card, .build-card { border: 1px solid rgba(30, 50, 90, .1); border-radius: 24px; }
.status-line { display: flex; align-items: center; justify-content: space-between; gap: 24px; }
.status-line > div { display: grid; gap: 5px; }.status-line strong { font-size: 22px; }.status-line small { color: #7a8496; }
.status-kicker { color: #9b613e; font-size: 11px; font-weight: 700; letter-spacing: .14em; }
.build-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.build-card :deep(.el-card__header) { display: flex; align-items: baseline; gap: 12px; border: 0; }
.build-card :deep(.el-card__header) span { font-size: 11px; letter-spacing: .16em; color: #9b613e; }
.build-card :deep(.el-card__header) strong { font-size: 20px; color: #1e325a; }
dl { margin: 0; } dl div { display: grid; grid-template-columns: 110px 1fr; gap: 12px; padding: 14px 0; border-top: 1px solid #edf0f5; }
dt { color: #7a8496; } dd { margin: 0; color: #25334d; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; overflow-wrap: anywhere; }
.frontend { border-top: 4px solid #e68b51; }.backend { border-top: 4px solid #294c7d; }.checked-at { text-align: right; color: #7a8496; font-size: 13px; }
@media (max-width: 720px) { .version-hero { align-items: stretch; flex-direction: column; gap: 22px; padding: 24px; } .build-grid { grid-template-columns: 1fr; } .status-line { align-items: flex-start; flex-direction: column; } dl div { grid-template-columns: 90px 1fr; } }
</style>
