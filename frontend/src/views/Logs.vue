<template>
  <div class="logs-page">
    <el-row :gutter="20">
      <!-- Share Stats -->
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>分享统计</span>
              <el-button
                type="primary"
                @click="fetchShareStats"
              >
                刷新
              </el-button>
            </div>
          </template>

          <el-row
            v-loading="statsLoading"
            :gutter="20"
            class="stats-row"
          >
            <el-col
              :xs="12"
              :sm="12"
              :md="6"
            >
              <div class="stat-card">
                <el-statistic
                  title="总分享数"
                  :value="shareStats.total_shares"
                />
              </div>
            </el-col>
            <el-col
              :xs="12"
              :sm="12"
              :md="6"
            >
              <div class="stat-card">
                <el-statistic
                  title="总访问次数"
                  :value="shareStats.total_access"
                />
              </div>
            </el-col>
            <el-col
              :xs="12"
              :sm="12"
              :md="6"
            >
              <div class="stat-card">
                <el-statistic
                  title="有效分享数"
                  :value="shareStats.active_shares"
                />
              </div>
            </el-col>
            <el-col
              :xs="12"
              :sm="12"
              :md="6"
            >
              <div class="stat-card">
                <el-statistic
                  title="平均访问率"
                  :value="avgAccessRate"
                  suffix="%"
                />
              </div>
            </el-col>
          </el-row>

          <el-divider />

          <h4 class="section-title">
            热门分享 Top 10
          </h4>
          <div class="table-responsive">
            <el-table
              :data="shareStats.top_accessed"
              border
              stripe
              size="small"
            >
              <el-table-column
                prop="proposal_name"
                label="方案名称"
              />
              <el-table-column
                prop="access_count"
                label="访问次数"
                width="120"
                sortable
              >
                <template #default="{ row }">
                  <el-tag type="warning">
                    {{ row.access_count }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-card>
      </el-col>

      <!-- Hot Products -->
      <el-col
        :span="24"
        style="margin-top: 20px;"
      >
        <el-card>
          <template #header>
            <div class="card-header">
              <span>热门商品</span>
              <el-button
                type="primary"
                @click="fetchHotProducts"
              >
                刷新
              </el-button>
            </div>
          </template>

          <div class="table-responsive">
            <el-table
              v-loading="hotLoading"
              :data="hotProducts"
              border
              stripe
            >
              <el-table-column
                prop="product_name"
                label="商品名称"
              />
              <el-table-column
                prop="ref_count"
                label="引用次数"
                width="120"
                sortable
              >
                <template #default="{ row }">
                  <el-tag type="success">
                    {{ row.ref_count }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-card>
      </el-col>

      <el-col
        :span="24"
        style="margin-top: 20px;"
      >
        <el-card>
          <template #header>
            <div class="card-header">
              <span>操作审计</span>
              <el-button
                type="primary"
                @click="fetchOperationLogs"
              >
                查询
              </el-button>
            </div>
          </template>

          <el-form
            :inline="true"
            :model="auditFilters"
            class="audit-filters"
          >
            <el-form-item label="动作">
              <el-input
                v-model="auditFilters.action"
                clearable
                placeholder="动作"
              />
            </el-form-item>
            <el-form-item label="模块">
              <el-input
                v-model="auditFilters.module"
                clearable
                placeholder="模块"
              />
            </el-form-item>
            <el-form-item label="用户ID">
              <el-input
                v-model="auditFilters.user_id"
                clearable
                placeholder="用户ID"
              />
            </el-form-item>
            <el-form-item label="响应码">
              <el-input-number
                v-model="auditFilters.response_code"
                :min="100"
                :max="599"
                controls-position="right"
                @change="resetAuditPage"
              />
            </el-form-item>
            <el-form-item label="起始时间">
              <el-date-picker
                v-model="auditFilters.start_time"
                type="datetime"
                value-format="YYYY-MM-DDTHH:mm:ss"
                placeholder="起始时间"
                @change="resetAuditPage"
              />
            </el-form-item>
            <el-form-item label="结束时间">
              <el-date-picker
                v-model="auditFilters.end_time"
                type="datetime"
                value-format="YYYY-MM-DDTHH:mm:ss"
                placeholder="结束时间"
                @change="resetAuditPage"
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                @click="resetAuditPageAndFetch"
              >
                查询
              </el-button>
              <el-button @click="resetAuditFilters">
                重置
              </el-button>
            </el-form-item>
          </el-form>

          <div
            v-if="operationLogs.length === 0 && !auditLoading"
            class="audit-empty"
          >
            暂无审计记录。可调整筛选条件后再次查询。
          </div>

          <div class="table-responsive">
            <el-table
              v-loading="auditLoading"
              :data="operationLogs"
              border
              stripe
              size="small"
            >
              <el-table-column
                prop="operate_time"
                label="时间"
                min-width="180"
              >
                <template #default="{ row }">
                  {{ formatLocalTime(row.operate_time) }}
                </template>
              </el-table-column>
              <el-table-column
                prop="action"
                label="动作"
                min-width="150"
              >
                <template #default="{ row }">
                  {{ ACTION_NAMES[row.action] || row.action }}
                </template>
              </el-table-column>
              <el-table-column
                prop="module"
                label="模块"
                width="120"
              >
                <template #default="{ row }">
                  {{ MODULE_NAMES[row.module] || row.module }}
                </template>
              </el-table-column>
              <el-table-column
                prop="user_id"
                label="用户"
                min-width="220"
              />
              <el-table-column
                prop="target_id"
                label="对象"
                min-width="220"
              />
              <el-table-column
                prop="response_code"
                label="响应码"
                width="100"
              >
                <template #default="{ row }">
                  <el-tag
                    :type="responseCodeTagType(row.response_code)"
                    size="small"
                  >
                    {{ row.response_code }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                prop="ip"
                label="IP"
                min-width="120"
              />
            </el-table>
          </div>

          <el-pagination
            v-model:current-page="auditPage"
            :page-size="20"
            :total="auditTotal"
            layout="prev, pager, next, total"
            class="audit-pagination"
            @current-change="fetchOperationLogs"
          />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { auditApi, statsApi } from '@/api'

const statsLoading = ref(false)

const MODULE_NAMES: Record<string, string> = {
  product: '产品',
  category: '品类',
  brand: '品牌',
  tag: '标签',
  supplier: '供应商',
  user: '用户',
  role: '角色',
  proposal: '方案',
  quotation: '报价',
  share: '分享',
  file: '文件',
  stats: '统计',
  ai: 'AI',
}

const ACTION_NAMES: Record<string, string> = {
  view: '查看',
  create: '新增',
  edit: '编辑',
  delete: '删除',
  import: '导入',
  export: '导出',
  status: '上下架',
  clone: '克隆',
  confirm: '确认',
  assign: '授权',
  upload: '上传',
  use: '使用',
  disable: '停用',
}
const hotLoading = ref(false)

const shareStats = reactive({
  total_shares: 0,
  total_access: 0,
  active_shares: 0,
  top_accessed: [] as { share_id: string; proposal_name: string | null; access_count: number }[],
})

const hotProducts = ref<{ product_id: string; product_name: string | null; ref_count: number }[]>([])
const auditLoading = ref(false)
const auditPage = ref(1)
const auditTotal = ref(0)
const auditFilters = reactive({
  action: '',
  module: '',
  user_id: '',
  response_code: undefined as number | undefined,
  start_time: '',
  end_time: '',
})
const operationLogs = ref<Array<Record<string, unknown>>>([])

const avgAccessRate = computed(() => {
  if (!shareStats.total_shares) return 0
  return Math.round((shareStats.total_access / shareStats.total_shares) * 10)
})

function responseCodeTagType(code: number | undefined): 'success' | 'warning' | 'danger' | 'info' {
  if (code === undefined) return 'info'
  if (code >= 500) return 'danger'
  if (code >= 400) return 'warning'
  if (code >= 200) return 'success'
  return 'info'
}

function formatLocalTime(utcOrIso: string | null): string {
  if (!utcOrIso) return ''
  // The backend stores naive timestamps in server local time (Asia/Shanghai).
  // We surface them as-is to avoid timezone drift in the admin UI; if browser
  // locale differs from server, this surfaces the raw string instead of mis-converting.
  return String(utcOrIso).replace('T', ' ')
}

function resetAuditPage() {
  auditPage.value = 1
}

function resetAuditPageAndFetch() {
  auditPage.value = 1
  fetchOperationLogs()
}

function resetAuditFilters() {
  auditFilters.action = ''
  auditFilters.module = ''
  auditFilters.user_id = ''
  auditFilters.response_code = undefined
  auditFilters.start_time = ''
  auditFilters.end_time = ''
  auditPage.value = 1
  fetchOperationLogs()
}

const fetchShareStats = async () => {
  statsLoading.value = true
  try {
    const res = await statsApi.shares() as any
    const data = res.data
    shareStats.total_shares = data.total_shares || 0
    shareStats.total_access = data.total_access || 0
    shareStats.active_shares = data.active_shares || 0
    shareStats.top_accessed = data.top_accessed || []
  } catch {
    ElMessage.error('加载分享统计失败')
  } finally {
    statsLoading.value = false
  }
}

const fetchHotProducts = async () => {
  hotLoading.value = true
  try {
    const res = await statsApi.hotProducts() as any
    const data = res.data
    hotProducts.value = data.items || []
  } catch {
    ElMessage.error('加载热门商品失败')
  } finally {
    hotLoading.value = false
  }
}

const fetchOperationLogs = async () => {
  auditLoading.value = true
  try {
    const params: Record<string, unknown> = { page: auditPage.value, size: 20 }
    for (const [key, value] of Object.entries(auditFilters)) {
      if (value !== '' && value !== undefined && value !== null) params[key] = value
    }
    const res = await auditApi.operationLogs(params) as any
    const data = res.data
    operationLogs.value = data.list || []
    auditTotal.value = data.total || 0
  } catch {
    ElMessage.error('加载操作审计失败')
  } finally {
    auditLoading.value = false
  }
}

onMounted(() => {
  fetchShareStats()
  fetchHotProducts()
  fetchOperationLogs()
})
</script>

<style scoped>
.logs-page {
  min-height: 100vh;
  background: #f0f0f0;
  padding: 24px;
  box-sizing: border-box;
}

.logs-page :deep(.el-card) {
  background: rgba(255, 255, 255, 0.68);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-radius: 28px;
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow: 0 4px 32px rgba(30, 50, 90, 0.06);
}

.logs-page :deep(.el-card__body) {
  padding: 24px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header :deep(span) {
  font-size: 20px;
  font-weight: 600;
  color: rgb(30, 50, 90);
  letter-spacing: 0.3px;
}

.card-header :deep(.el-button) {
  border-radius: 20px;
}

.stats-row {
  margin-bottom: 8px;
}

.stat-card {
  padding: 8px 0;
}

.section-title {
  color: #5E6470;
  font-weight: 600;
  font-size: 16px;
  margin: 16px 0 12px;
}

.table-responsive {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  border-radius: 12px;
}

.table-responsive :deep(.el-table) {
  min-width: 500px;
  border-radius: 12px;
  overflow: hidden;
}

.audit-filters {
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.audit-filters :deep(.el-button) {
  border-radius: 20px;
}

.audit-pagination {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 768px) {
  .logs-page {
    padding: 12px;
  }
  .logs-page :deep(.el-card__body) {
    padding: 16px;
  }
  .card-header :deep(span) {
    font-size: 18px;
  }
  .audit-pagination {
    justify-content: center;
  }
}
</style>
