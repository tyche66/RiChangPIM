<template>
  <div class="knowledge-index-admin">
    <el-alert
      v-if="!status?.enabled"
      type="warning"
      :closable="false"
      show-icon
      title="向量索引服务已停用：不再发起任何新的索引任务（含手动运行）。恢复启用后从队列继续。"
    />

    <el-row :gutter="16">
      <el-col :span="24">
        <el-card shadow="never" class="block">
          <template #header>
            <div class="card-head">
              <span>服务状态</span>
              <el-switch
                :model-value="status?.enabled ?? false"
                :loading="switchBusy"
                active-text="启用"
                inactive-text="停用"
                inline-prompt
                @before-change="toggleEnabled"
              />
            </div>
          </template>
          <el-descriptions :column="3" border size="small">
            <el-descriptions-item label="当前状态">
              <el-tag :type="statusTagType" size="small">{{ statusLabel }}</el-tag>
              <el-tag
                v-if="status?.heartbeat_stale"
                type="danger"
                size="small"
                class="ml8"
              >
                心跳超时，调度进程可能未运行
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="最近心跳">
              {{ formatTime(status?.heartbeat_at) || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="调度时区">
              {{ settings?.timezone || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="调度窗口">
              {{ settings ? `${settings.window_start} - ${settings.window_end}` : '—' }}
              <span class="muted">
                （结束前 {{ settings?.safety_cutoff_minutes ?? 5 }} 分钟停止新
                embedding 请求，即安全截止
                {{ formatTime(status?.next_cutoff_at) || '—' }}）
              </span>
            </el-descriptions-item>
            <el-descriptions-item label="下次运行">
              {{ formatTime(status?.next_window_start_at) || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="生效模型">
              {{ effectiveModel || '—' }}
              <span v-if="effectiveVersion" class="muted">({{ effectiveVersion }})</span>
            </el-descriptions-item>
          </el-descriptions>

          <el-row :gutter="12" class="stat-row">
            <el-col :span="4">
              <div class="stat">
                <div class="stat-num">{{ status?.queue.backlog ?? 0 }}</div>
                <div class="stat-label">可执行积压</div>
              </div>
            </el-col>
            <el-col :span="4">
              <div class="stat">
                <div class="stat-num">{{ status?.queue.by_status?.processing ?? 0 }}</div>
                <div class="stat-label">处理中</div>
              </div>
            </el-col>
            <el-col :span="4">
              <div class="stat">
                <div class="stat-num warn">{{ status?.queue.by_status?.failed ?? 0 }}</div>
                <div class="stat-label">退避中(failed)</div>
              </div>
            </el-col>
            <el-col :span="4">
              <div class="stat">
                <div class="stat-num danger">{{ status?.queue.quarantined ?? 0 }}</div>
                <div class="stat-label">确定性隔离(dead)</div>
              </div>
            </el-col>
            <el-col :span="4">
              <div class="stat">
                <div class="stat-num">{{ status?.queue.dead_retained ?? 0 }}</div>
                <div class="stat-label">dead 保留中</div>
              </div>
            </el-col>
            <el-col :span="4">
              <div class="stat">
                <div class="stat-num">{{ status?.queue.dead_expired_purgeable ?? 0 }}</div>
                <div class="stat-label">dead 待清理(>{{ status?.queue.dead_retention_days ?? 90 }}天)</div>
              </div>
            </el-col>
          </el-row>

          <div class="actions">
            <el-button
              type="primary"
              :disabled="!status?.enabled || !!status?.current_run"
              :loading="runNowBusy"
              @click="onRunNow"
            >
              立即运行（每次最多 {{ runNowCap }} 个产品）
            </el-button>
            <el-button :disabled="busy" @click="onResetDead">重置重试隔离任务</el-button>
            <el-button :disabled="busy" @click="onResetFailed">重置重试失败任务</el-button>
            <span class="muted">
              dead 任务保留 {{ status?.queue.dead_retention_days ?? 90 }} 天，过期由夜间窗口分批清理；
              最早 dead 记录：{{ formatTime(status?.queue.oldest_dead_at) || '—' }}
            </span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="mt16">
      <el-col :span="24">
        <el-card shadow="never" class="block">
          <template #header>
            <div class="card-head">
              <span>调度与批次配置</span>
              <el-button type="primary" size="small" :loading="saving" @click="saveSettings">
                保存配置
              </el-button>
            </div>
          </template>
          <el-form label-width="200px" size="small" :disabled="busy">
            <el-form-item label="启停开关">
              <el-tag :type="form.enabled ? 'success' : 'info'" size="small">
                {{ form.enabled ? '启用（窗口内自动运行）' : '停用（不发起新任务）' }}
              </el-tag>
              <span class="muted ml8">用右上角开关修改</span>
            </el-form-item>
            <el-form-item label="时区">
              <el-select v-model="form.timezone" filterable allow-create style="width: 240px">
                <el-option
                  v-for="tz in TIMEZONES"
                  :key="tz"
                  :label="tz"
                  :value="tz"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="调度窗口（本地时间）">
              <el-time-select
                v-model="form.window_start"
                start="00:00"
                end="23:55"
                step="00:05"
                style="width: 120px"
              />
              <span class="ml8">至</span>
              <el-time-select
                v-model="form.window_end"
                start="00:00"
                end="23:55"
                step="00:05"
                style="width: 120px"
                class="ml8"
              />
            </el-form-item>
            <el-form-item label="安全截止（结束前分钟数）">
              <el-input-number v-model="form.safety_cutoff_minutes" :min="0" :max="30" />
              <span class="muted ml8">默认 5：02:30 结束即 02:25 后不再发起新 embedding 请求</span>
            </el-form-item>
            <el-form-item label="reconcile 每轮产品上限">
              <el-input-number v-model="form.reconcile_batch_size" :min="1" :max="1000" />
            </el-form-item>
            <el-form-item label="单次 embedding 合并产品数">
              <el-input-number v-model="form.embedding_batch_size" :min="1" :max="96" />
            </el-form-item>
            <el-form-item label="请求间隔（秒）">
              <el-input-number v-model="form.request_interval_seconds" :min="0" :max="300" />
            </el-form-item>
            <el-form-item label="请求超时（秒）">
              <el-input-number v-model="form.request_timeout_seconds" :min="10" :max="600" />
            </el-form-item>
            <el-form-item label="最大尝试次数">
              <el-input-number v-model="form.max_attempts" :min="1" :max="10" />
            </el-form-item>
            <el-form-item label="指数退避基数（秒）">
              <el-input-number v-model="form.backoff_base_seconds" :min="5" :max="3600" />
            </el-form-item>
            <el-form-item label="指数退避上限（秒）">
              <el-input-number v-model="form.backoff_max_seconds" :min="30" :max="21600" />
            </el-form-item>
            <el-form-item label="dead 保留天数">
              <el-input-number v-model="form.dead_retention_days" :min="7" :max="3650" />
              <span class="muted ml8">仅清理超期 dead 记录，分批执行</span>
            </el-form-item>
            <el-form-item label="僵死锁回收阈值（分钟）">
              <el-input-number v-model="form.stale_lock_minutes" :min="5" :max="240" />
            </el-form-item>
            <el-form-item label="run-now 最长执行（秒）">
              <el-input-number v-model="form.run_now_max_duration_seconds" :min="60" :max="3600" />
            </el-form-item>
            <el-form-item label="run-now 产品上限">
              <el-tag type="warning" size="small">{{ runNowCap }}（后端硬上限，不可修改）</el-tag>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="mt16">
      <el-col :span="24">
        <el-card shadow="never" class="block">
          <template #header>
            <div class="card-head">
              <span>最近运行报告（{{ runs.length }} 条）</span>
              <el-button size="small" :loading="loading" @click="loadAll">刷新</el-button>
            </div>
          </template>
          <el-table :data="runs" size="small" border stripe>
            <el-table-column label="开始时间" width="150">
              <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
            </el-table-column>
            <el-table-column label="触发" width="120">
              <template #default="{ row }">
                {{ row.trigger_type === 'scheduled' ? '夜间窗口' : `手动(${row.operator || '-'})` }}
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag
                  size="small"
                  :type="row.status === 'completed' ? 'success' : row.status === 'failed' ? 'danger' : row.status === 'running' ? 'primary' : 'info'"
                >
                  {{ RUN_STATUS_LABEL[row.status] || row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="scanned_count" label="扫描" width="60" />
            <el-table-column prop="queued_count" label="入队" width="60" />
            <el-table-column prop="embedding_success_count" label="embedding成功" width="110" />
            <el-table-column prop="hash_skipped_count" label="hash跳过" width="85" />
            <el-table-column prop="failed_count" label="失败" width="60" />
            <el-table-column prop="quarantined_count" label="隔离" width="60" />
            <el-table-column prop="rate_limited_count" label="429" width="60" />
            <el-table-column prop="batch_count" label="批次" width="60" />
            <el-table-column label="积压(前→后)" width="110">
              <template #default="{ row }">{{ row.backlog_before }} → {{ row.backlog_after }}</template>
            </el-table-column>
            <el-table-column label="token 用量" width="130">
              <template #default="{ row }">
                <span v-if="row.token_usage_actual">实测 {{ row.token_usage_actual }}</span>
                <span v-else-if="row.token_usage_estimated" class="muted">
                  估算≈{{ row.token_usage_estimated }}
                </span>
                <span v-else>—</span>
              </template>
            </el-table-column>
            <el-table-column label="模型" width="160">
              <template #default="{ row }">{{ row.embedding_model || '—' }}</template>
            </el-table-column>
            <el-table-column label="结束原因/错误" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.error_summary || stopReasonText(row.details) }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  fetchKnowledgeIndexRuns,
  fetchKnowledgeIndexSettings,
  fetchKnowledgeIndexStatus,
  resetKnowledgeIndexJobs,
  runKnowledgeIndexNow,
  updateKnowledgeIndexSettings,
  type KnowledgeIndexRunReport,
  type KnowledgeIndexSettings,
  type StatusResponse,
} from '@/api/knowledgeIndex'

const TIMEZONES = [
  'Asia/Shanghai',
  'Asia/Hong_Kong',
  'Asia/Tokyo',
  'Asia/Singapore',
  'UTC',
  'Europe/London',
  'America/New_York',
]

const RUN_STATUS_LABEL: Record<string, string> = {
  running: '运行中',
  completed: '完成',
  stopped: '已停止',
  failed: '失败',
}

const STOP_REASON_LABEL: Record<string, string> = {
  queue_empty: '队列已清空',
  window_end: '窗口结束',
  cutoff: '到达安全截止(02:25)',
  disabled: '已停用',
  stopping: '正在收尾',
  product_cap: '达到产品上限',
}

const status = ref<StatusResponse | null>(null)
const settings = ref<KnowledgeIndexSettings | null>(null)
const runs = ref<KnowledgeIndexRunReport[]>([])
const effectiveModel = ref<string | null>(null)
const effectiveVersion = ref<string | null>(null)
const loading = ref(false)
const saving = ref(false)
const switchBusy = ref(false)
const runNowBusy = ref(false)
const busy = computed(() => loading.value || saving.value || switchBusy.value)

const form = reactive<KnowledgeIndexSettings>({
  enabled: false,
  timezone: 'Asia/Shanghai',
  window_start: '01:00',
  window_end: '02:30',
  safety_cutoff_minutes: 5,
  reconcile_batch_size: 200,
  embedding_batch_size: 48,
  request_interval_seconds: 2,
  request_timeout_seconds: 120,
  max_attempts: 3,
  backoff_base_seconds: 60,
  backoff_max_seconds: 1800,
  dead_retention_days: 90,
  stale_lock_minutes: 15,
  run_now_max_products: 200,
  run_now_max_duration_seconds: 600,
})

const runNowCap = computed(() => settings.value?.run_now_max_products ?? 200)

const statusLabel = computed(() => {
  const s = status.value
  if (!s) return '加载中…'
  if (s.scheduler_status === 'window_active') return '夜间窗口运行中'
  if (s.scheduler_status === 'run_now_active') return '手动运行中'
  if (s.scheduler_status === 'stopping') return '正在收尾'
  if (s.scheduler_status === 'disabled') return '已停用'
  return '空闲（等待窗口）'
})

const statusTagType = computed(() => {
  const s = status.value
  if (!s) return 'info'
  if (s.scheduler_status === 'window_active' || s.scheduler_status === 'run_now_active') {
    return 'success'
  }
  if (s.scheduler_status === 'disabled') return 'danger'
  return 'info'
})

function stopReasonText(details: Record<string, unknown> | null): string {
  const reason = details?.stop_reason
  return typeof reason === 'string' ? STOP_REASON_LABEL[reason] || reason : ''
}

/** 按调度配置的时区渲染时间（心跳/下次运行/报告），而非管理员浏览器时区。 */
const tzFormatter = computed<Intl.DateTimeFormat | null>(() => {
  const tz = settings.value?.timezone || 'Asia/Shanghai'
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      timeZone: tz,
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    })
  } catch {
    // 非法时区名回落浏览器本地时区
    return null
  }
})

function formatTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  if (tzFormatter.value) {
    try {
      return tzFormatter.value.format(date)
    } catch {
      /* fallthrough */
    }
  }
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

function fillForm(source: KnowledgeIndexSettings): void {
  Object.assign(form, source)
}

async function loadAll(): Promise<void> {
  loading.value = true
  try {
    const [settingsResp, statusResp, runsResp] = await Promise.all([
      fetchKnowledgeIndexSettings(),
      fetchKnowledgeIndexStatus(),
      fetchKnowledgeIndexRuns(30),
    ])
    settings.value = settingsResp.settings
    fillForm(settingsResp.settings)
    effectiveModel.value = settingsResp.effective_embedding_model
    effectiveVersion.value = settingsResp.effective_embedding_version
    status.value = statusResp
    runs.value = runsResp
  } catch {
    ElMessage.error('加载向量索引状态失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

async function toggleEnabled(): Promise<boolean> {
  const next = !(status.value?.enabled ?? false)
  const action = next ? '启用' : '停用'
  const hint = next
    ? '启用后将在调度窗口自动处理索引队列，未完成任务从队列继续。'
    : '停用后不再发起新任务；正在进行的批次将安全收尾，任务不丢失。'
  try {
    await ElMessageBox.confirm(hint, `确认${action}向量索引服务？`, {
      confirmButtonText: action,
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return false
  }
  switchBusy.value = true
  try {
    await updateKnowledgeIndexSettings({ enabled: next })
    ElMessage.success(`已${action}向量索引服务`)
    await loadAll()
    return true
  } catch {
    ElMessage.error('修改启停状态失败，请重试')
    return false
  } finally {
    switchBusy.value = false
  }
}

async function saveSettings(): Promise<void> {
  saving.value = true
  try {
    await updateKnowledgeIndexSettings({
      timezone: form.timezone,
      window_start: form.window_start,
      window_end: form.window_end,
      safety_cutoff_minutes: form.safety_cutoff_minutes,
      reconcile_batch_size: form.reconcile_batch_size,
      embedding_batch_size: form.embedding_batch_size,
      request_interval_seconds: form.request_interval_seconds,
      request_timeout_seconds: form.request_timeout_seconds,
      max_attempts: form.max_attempts,
      backoff_base_seconds: form.backoff_base_seconds,
      backoff_max_seconds: form.backoff_max_seconds,
      dead_retention_days: form.dead_retention_days,
      stale_lock_minutes: form.stale_lock_minutes,
      run_now_max_duration_seconds: form.run_now_max_duration_seconds,
    })
    ElMessage.success('配置已保存')
    await loadAll()
  } catch {
    ElMessage.error('保存配置失败，请检查取值范围后重试')
  } finally {
    saving.value = false
  }
}

async function onRunNow(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `将立即处理待索引产品，每次最多 ${runNowCap.value} 个不同产品（服务端强制），与夜间任务互斥。`,
      '确认立即运行？',
      { confirmButtonText: '立即运行', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return
  }
  runNowBusy.value = true
  try {
    await runKnowledgeIndexNow()
    ElMessage.success('已开始运行，可在状态区查看进度')
    await loadAll()
  } catch {
    ElMessage.error('无法启动：服务可能已停用或已有任务在运行')
  } finally {
    runNowBusy.value = false
  }
}

async function onResetDead(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '为确定性隔离(dead)任务的产品重新建立索引任务（保留历史记录与失败计数）。确认继续？',
      '重置重试隔离任务',
      { confirmButtonText: '重置', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    const result = await resetKnowledgeIndexJobs({ scope: 'dead', limit: 200 })
    ElMessage.success(`已为 ${result.reset} 个任务重新入队`)
    await loadAll()
  } catch {
    ElMessage.error('重置失败，请重试')
  }
}

async function onResetFailed(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '为退避中(failed)任务的产品重新建立索引任务（原任务的退避与计数保留）。确认继续？',
      '重置重试失败任务',
      { confirmButtonText: '重置', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    const result = await resetKnowledgeIndexJobs({ scope: 'failed', limit: 200 })
    ElMessage.success(`已为 ${result.reset} 个任务重新入队`)
    await loadAll()
  } catch {
    ElMessage.error('重置失败，请重试')
  }
}

let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  void loadAll()
  pollTimer = setInterval(() => {
    void fetchKnowledgeIndexStatus()
      .then((resp) => {
        status.value = resp
      })
      .catch(() => {
        /* 轮询失败静默，下一轮重试 */
      })
  }, 15000)
})

onUnmounted(() => {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
})
</script>

<style scoped>
.knowledge-index-admin {
  padding: 0;
}

.block .card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.stat-row {
  margin-top: 16px;
}

.stat {
  text-align: center;
  padding: 8px 0;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}

.stat-num {
  font-size: 22px;
  font-weight: 600;
}

.stat-num.warn {
  color: var(--el-color-warning);
}

.stat-num.danger {
  color: var(--el-color-danger);
}

.stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.actions {
  margin-top: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.ml8 {
  margin-left: 8px;
}

.mt16 {
  margin-top: 16px;
}
</style>
