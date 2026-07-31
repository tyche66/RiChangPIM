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
            <el-form-item label="用户名">
              <el-input
                v-model="auditFilters.username"
                clearable
                placeholder="用户名"
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
                label="时间（北京时间）"
                class-name="cell-num"
                min-width="180"
              >
                <template #default="{ row }">
                  {{ formatBeijingTime(row.operate_time) }}
                </template>
              </el-table-column>
              <el-table-column
                prop="action"
                label="动作"
                class-name="cell-strong"
                min-width="150"
              >
                <template #default="{ row }">
                  {{ ACTION_NAMES[row.action] || row.action }}
                </template>
              </el-table-column>
              <el-table-column
                prop="module"
                label="模块"
                class-name="cell-soft"
                width="120"
              >
                <template #default="{ row }">
                  {{ MODULE_NAMES[row.module] || row.module }}
                </template>
              </el-table-column>
              <el-table-column
                prop="username"
                label="操作用户"
                min-width="180"
              >
                <template #default="{ row }">
                  <span
                    v-if="row.username"
                    class="cell-strong"
                  >{{ row.username }}</span>
                  <span
                    v-else-if="row.user_id"
                    class="cell-code"
                    :title="String(row.user_id)"
                  >{{ shortId(row.user_id) }}</span>
                  <span
                    v-else
                    class="cell-meta"
                  >匿名请求</span>
                </template>
              </el-table-column>
              <el-table-column
                prop="target_id"
                label="对象"
                class-name="cell-code"
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
                class-name="cell-code"
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
import { beijingLocalToInstant, formatBeijingTime } from '@/utils/beijingTime'

const statsLoading = ref(false)

/**
 * 模块与动作的中文名。键必须和后端 `@audit_action(action, module=...)` 写的完全一致
 * （见 backend/app/middleware/audit.py 的调用点），对不上就会把原始枚举摊给用户看。
 * 没收录的值按原样显示，不猜、不编。
 */
const MODULE_NAMES: Record<string, string> = {
  ai: 'AI',
  auth: '登录',
  files: '文件',
  knowledge: 'AI 知识',
  manuals: '资料',
  products: '产品',
  proposals: '方案',
  quotations: '报价',
  roles: '角色',
  scene_images: '场景图',
  shares: '分享',
  stats: '统计',
  users: '用户',
}

const ACTION_NAMES: Record<string, string> = {
  ai_chat: 'AI 对话',
  ai_embeddings: 'AI 向量化',
  ai_manual_parse: '资料解析',
  ai_polish: 'AI 润色',
  ai_rag_answer: 'AI 问答',
  ai_rag_index: 'AI 建索引',
  ai_rag_search: 'AI 检索',
  ai_recommend: 'AI 推荐',
  change_password: '修改密码',
  file_delete: '删除文件',
  file_download: '下载文件',
  file_preview: '预览文件',
  file_replace: '替换文件',
  file_upload: '上传文件',
  knowledge_query: 'AI 查询',
  login: '登录',
  login_failed: '登录失败',
  logout: '退出登录',
  manual_ocr: '资料 OCR',
  product_clone: '克隆产品',
  product_create: '新建产品',
  product_delete: '删除产品',
  product_image_add: '添加产品图',
  product_image_cover: '设置主图',
  product_image_delete: '删除产品图',
  product_image_reorder: '产品图排序',
  product_import: '导入产品',
  product_scene_image_bind: '绑定场景图',
  product_scene_image_reorder: '场景图排序',
  product_scene_image_unbind: '解绑场景图',
  product_status: '产品上下架',
  proposal_confirm: '确认方案',
  proposal_delete: '删除方案',
  proposal_revert_confirmation: '撤销方案确认',
  quotation_create: '新建报价',
  quotation_detail: '查看报价',
  quotation_list: '报价列表',
  quotation_pdf_export: '导出报价 PDF',
  quotation_update: '修改报价',
  role_perm_change: '调整角色权限',
  scene_image_batch_bind: '批量绑定场景图',
  scene_image_bind: '绑定场景图',
  scene_image_create: '新增场景图',
  scene_image_delete: '删除场景图',
  scene_image_unbind: '解绑场景图',
  scene_image_update: '修改场景图',
  share_access: '访问分享',
  share_access_denied: '分享访问被拒',
  share_create: '创建分享',
  share_revoke: '撤销分享',
  stats_products_hot: '热门商品统计',
  stats_shares: '分享统计',
  user_create: '新增用户',
  user_delete: '删除用户',
  user_disable: '停用用户',
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
  username: '',
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

/**
 * 操作日志时间统一按北京时间 24 小时制展示，筛选值反向换算成 UTC 瞬时。
 * 换算规则和踩过的坑都在 utils/beijingTime.ts 里，单测见
 * tests/unit/beijingTime.spec.ts。
 */

/**
 * 用户名取不到时退化显示用户编号前 8 位，完整值放在 title 属性里。
 * 不用假名字（比如「已删除用户」）填充：日志里没记下来的东西就不能编出来。
 */
function shortId(value: unknown): string {
  const text = String(value ?? '')
  return text.length > 8 ? `${text.slice(0, 8)}…` : text
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
  auditFilters.username = ''
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
      if (value === '' || value === undefined || value === null) continue
      params[key] =
        key === 'start_time' || key === 'end_time' ? beijingLocalToInstant(String(value)) : value
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
