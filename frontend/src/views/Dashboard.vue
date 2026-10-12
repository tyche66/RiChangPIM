<template>
  <div class="crm-page">
    <el-card class="crm-card">
      <template #header>
        <div class="crm-card__header">
          <span class="crm-card__title">驾驶舱</span>
          <div class="crm-card__actions">
            <el-radio-group
              v-model="range"
              @change="loadOverview"
            >
              <el-radio-button value="7d">
                近 7 天
              </el-radio-button>
              <el-radio-button value="30d">
                近 30 天
              </el-radio-button>
              <el-radio-button value="90d">
                近 90 天
              </el-radio-button>
            </el-radio-group>
            <el-button
              class="crm-btn"
              :loading="loading"
              @click="refreshAll"
            >
              刷新
            </el-button>
          </div>
        </div>
      </template>

      <div
        v-loading="loading"
        class="crm-kpi-grid"
      >
        <div
          v-for="card in kpiCards"
          :key="card.key"
          class="crm-kpi"
        >
          <div class="crm-kpi__label">
            {{ card.label }}
          </div>
          <div class="crm-kpi__value">
            <EmptyMetric
              :value="card.value"
              :reason="card.reason"
              :currency="card.currency"
            />
          </div>
          <div class="crm-kpi__foot">
            <template v-if="card.trend !== undefined && card.trend !== null">
              <span
                class="crm-trend"
                :class="card.trend >= 0 ? 'crm-trend--up' : 'crm-trend--down'"
              >
                {{ card.trend >= 0 ? '▲' : '▼' }}
                {{ Math.abs(Math.round(card.trend * 100)) }}%
              </span>
              <span>较上一周期</span>
            </template>
            <span v-else>{{ card.foot }}</span>
          </div>
        </div>
      </div>

      <div class="crm-dashboard-grid">
        <section>
          <h3 class="crm-section__title">
            客户漏斗
          </h3>
          <VChart
            v-if="funnel.length"
            class="crm-chart"
            :option="funnelOption"
            autoresize
          />
          <p
            v-else
            class="crm-empty"
          >
            暂无漏斗数据
          </p>
        </section>

        <section>
          <h3 class="crm-section__title">
            我的待办
            <span class="crm-kpi__label">{{ todos.total_pending }} 项</span>
          </h3>
          <p
            v-if="!todos.reminders.length && !todos.follow_ups.length"
            class="crm-empty"
          >
            暂无待办
          </p>
          <ul
            v-else
            class="crm-list"
          >
            <li
              v-for="r in todos.reminders"
              :key="`r-${r.id}`"
              class="crm-list-item"
            >
              <div class="crm-list-item__meta">
                <el-tag
                  size="small"
                  :type="r.status === 'overdue' ? 'danger' : 'info'"
                  class="crm-tag"
                >
                  {{ labelOf(REMINDER_RULE_MAP, r.rule_code) }}
                </el-tag>
                <span>{{ formatBeijingTime(r.due_at) || '—' }}</span>
              </div>
              <div class="crm-list-item__body">
                {{ r.title }}
              </div>
            </li>
            <li
              v-for="f in todos.follow_ups"
              :key="`f-${f.id}`"
              class="crm-list-item"
            >
              <div class="crm-list-item__meta">
                <el-tag
                  size="small"
                  type="warning"
                  class="crm-tag"
                >
                  跟进
                </el-tag>
                <span>{{ formatBeijingTime(f.next_follow_at) || '—' }}</span>
              </div>
              <div class="crm-list-item__body">
                {{ f.content }}
              </div>
            </li>
          </ul>
        </section>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref } from 'vue'
import { dashboardApi, type DashboardRange, type FunnelBucket, type OverviewData, type TodosData } from '@/api/dashboard'
import EmptyMetric from '@/components/EmptyMetric.vue'
import { STAGE_MAP, REMINDER_RULE_MAP, labelOf } from '@/constants/crm'
import { formatBeijingTime } from '@/utils/beijingTime'

// echarts 走异步加载 + 按需注册：不进常驻 chunk（HLD §12.2）。
const VChart = defineAsyncComponent(async () => {
  const [vueEcharts, echartsCore, echartsCharts, echartsComponents, echartsRenderers] =
    await Promise.all([
      import('vue-echarts'),
      import('echarts/core'),
      import('echarts/charts'),
      import('echarts/components'),
      import('echarts/renderers'),
    ])
  echartsCore.use([
    echartsCharts.BarChart,
    echartsCharts.LineChart,
    echartsCharts.PieChart,
    echartsComponents.GridComponent,
    echartsComponents.TooltipComponent,
    echartsComponents.LegendComponent,
    echartsRenderers.CanvasRenderer,
  ])
  return vueEcharts.default
})

interface KpiCard {
  key: string
  label: string
  value: number | null
  reason?: string | null
  trend?: number | null
  currency?: boolean
  foot?: string
}

const range = ref<DashboardRange>('30d')
const loading = ref(false)
const overview = ref<OverviewData | null>(null)
const funnel = ref<FunnelBucket[]>([])
const todos = ref<TodosData>({ reminders: [], follow_ups: [], total_pending: 0 })

const kpiCards = computed<KpiCard[]>(() => {
  const o = overview.value
  if (!o) {
    return [
      { key: 'new_customers', label: '新增客户', value: null, foot: '—' },
      { key: 'active_projects', label: '进行中项目', value: null, foot: '—' },
      { key: 'overdue_follow_ups', label: '逾期跟进', value: null, foot: '—' },
      { key: 'stalled_projects', label: '停滞项目', value: null, foot: '—' },
      { key: 'confirmed_amount', label: '已确认金额', value: null, foot: '—' },
    ]
  }
  const amount = o.confirmed_amount
  return [
    {
      key: 'new_customers',
      label: '新增客户',
      value: o.new_customers.value,
      reason: o.new_customers.empty_reason,
      trend: o.new_customers.trend,
      foot: '—',
    },
    {
      key: 'active_projects',
      label: '进行中项目',
      value: o.active_projects.value,
      reason: o.active_projects.empty_reason,
      trend: o.active_projects.trend,
      foot: '—',
    },
    {
      key: 'overdue_follow_ups',
      label: '逾期跟进',
      value: o.overdue_follow_ups.value,
      reason: o.overdue_follow_ups.empty_reason,
      trend: o.overdue_follow_ups.trend,
      foot: '—',
    },
    {
      key: 'stalled_projects',
      label: '停滞项目',
      value: o.stalled_projects.value,
      reason: o.stalled_projects.empty_reason,
      foot: `超过 ${o.stalled_projects.threshold_days ?? 7} 天未活动`,
    },
    {
      key: 'confirmed_amount',
      label: '已确认金额',
      value: amount.visible ? (amount.value ?? null) : null,
      reason: amount.visible ? amount.empty_reason : 'no_permission',
      currency: true,
      foot: '—',
    },
  ]
})

const funnelOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 48, right: 24, top: 24, bottom: 32 },
  xAxis: {
    type: 'category',
    data: funnel.value.map((f) => labelOf(STAGE_MAP, f.stage)),
  },
  yAxis: { type: 'value', minInterval: 1 },
  series: [
    {
      type: 'bar',
      data: funnel.value.map((f) => f.count),
      barMaxWidth: 48,
      itemStyle: { borderRadius: [6, 6, 0, 0] },
    },
  ],
}))

async function loadOverview() {
  loading.value = true
  try {
    const res = await dashboardApi.overview(range.value)
    overview.value = res.data
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

async function loadFunnel() {
  try {
    const res = await dashboardApi.funnel()
    funnel.value = res.data.customer_funnel
  } catch {
    // ignore
  }
}

async function loadTodos() {
  try {
    const res = await dashboardApi.todos(10)
    todos.value = res.data
  } catch {
    // ignore
  }
}

function refreshAll() {
  loadOverview()
  loadFunnel()
  loadTodos()
}

onMounted(refreshAll)
</script>

<style scoped>
.crm-dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
  gap: 24px;
}

@media (max-width: 900px) {
  .crm-dashboard-grid {
    grid-template-columns: 1fr;
  }
}
</style>
