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
          >
            <el-col :span="6">
              <el-statistic
                title="总分享数"
                :value="shareStats.total_shares"
              />
            </el-col>
            <el-col :span="6">
              <el-statistic
                title="总访问次数"
                :value="shareStats.total_access"
              />
            </el-col>
            <el-col :span="6">
              <el-statistic
                title="有效分享数"
                :value="shareStats.active_shares"
              />
            </el-col>
            <el-col :span="6">
              <el-statistic
                title="平均访问率"
                :value="avgAccessRate"
                suffix="%"
              />
            </el-col>
          </el-row>

          <el-divider />

          <h4>热门分享 Top 10</h4>
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
                placeholder="action"
              />
            </el-form-item>
            <el-form-item label="模块">
              <el-input
                v-model="auditFilters.module"
                clearable
                placeholder="module"
              />
            </el-form-item>
            <el-form-item label="用户ID">
              <el-input
                v-model="auditFilters.user_id"
                clearable
                placeholder="user_id"
              />
            </el-form-item>
            <el-form-item label="响应码">
              <el-input-number
                v-model="auditFilters.response_code"
                :min="100"
                :max="599"
                controls-position="right"
              />
            </el-form-item>
          </el-form>

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
            />
            <el-table-column
              prop="action"
              label="动作"
              min-width="150"
            />
            <el-table-column
              prop="module"
              label="模块"
              width="120"
            />
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
            />
            <el-table-column
              prop="ip"
              label="IP"
              min-width="120"
            />
          </el-table>

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
})
const operationLogs = ref<Array<Record<string, unknown>>>([])

const avgAccessRate = computed(() => {
  if (!shareStats.total_shares) return 0
  return Math.round((shareStats.total_access / shareStats.total_shares) * 10)
})

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
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.audit-filters {
  margin-bottom: 12px;
}

.audit-pagination {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>
