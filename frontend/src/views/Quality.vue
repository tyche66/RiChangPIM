<template>
  <div class="quality-page">
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>试点数据质量看板</span>
              <el-button
                type="primary"
                :loading="exporting"
                @click="exportQuality"
              >
                导出待补充清单
              </el-button>
            </div>
          </template>

          <div
            v-loading="summaryLoading"
            class="stats-row"
          >
            <div class="stat-pill">
              <div class="stat-num">
                {{ summary.total || 0 }}
              </div>
              <div class="stat-label">
                总产品
              </div>
            </div>
            <div class="stat-pill warn">
              <div class="stat-num">
                {{ summary.no_price || 0 }}
              </div>
              <div class="stat-label">
                待核价
              </div>
            </div>
            <div class="stat-pill warn">
              <div class="stat-num">
                {{ summary.no_image || 0 }}
              </div>
              <div class="stat-label">
                缺图片
              </div>
            </div>
            <div class="stat-pill warn">
              <div class="stat-num">
                {{ summary.no_manual || 0 }}
              </div>
              <div class="stat-label">
                缺说明书
              </div>
            </div>
            <div class="stat-pill warn">
              <div class="stat-num">
                {{ summary.no_spec || 0 }}
              </div>
              <div class="stat-label">
                缺规格
              </div>
            </div>
            <div class="stat-pill warn">
              <div class="stat-num">
                {{ summary.source_incomplete || 0 }}
              </div>
              <div class="stat-label">
                来源不完整
              </div>
            </div>
            <div class="stat-pill err">
              <div class="stat-num">
                {{ summary.ocr_failed || 0 }}
              </div>
              <div class="stat-label">
                OCR/解析失败
              </div>
            </div>
            <div class="stat-pill err">
              <div class="stat-num">
                {{ summary.long_pending || 0 }}
              </div>
              <div class="stat-label">
                长期 pend
              </div>
            </div>
          </div>

          <el-divider />

          <el-form
            :inline="true"
            :model="filters"
            class="quality-filters"
          >
            <el-form-item label="质量维度">
              <el-select
                v-model="filters.quality_flag"
                clearable
                placeholder="全部"
                style="width: 180px"
                @change="resetAndLoad"
              >
                <el-option
                  label="待核价"
                  value="no_price"
                />
                <el-option
                  label="缺图片"
                  value="no_image"
                />
                <el-option
                  label="缺说明书"
                  value="no_manual"
                />
                <el-option
                  label="缺规格"
                  value="no_spec"
                />
                <el-option
                  label="来源不完整"
                  value="source_incomplete"
                />
                <el-option
                  label="OCR/解析失败"
                  value="ocr_failed"
                />
                <el-option
                  label="长期 pending"
                  value="long_pending"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="完整度状态">
              <el-select
                v-model="filters.completeness_status"
                clearable
                placeholder="全部"
                style="width: 160px"
                @change="resetAndLoad"
              >
                <el-option
                  label="完整"
                  value="complete"
                />
                <el-option
                  label="待补充"
                  value="pending"
                />
                <el-option
                  label="未知"
                  value="unknown"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="供应商">
              <el-input
                v-model="filters.supplier_id"
                clearable
                placeholder="供应商ID"
                style="width: 220px"
                @change="resetAndLoad"
              />
            </el-form-item>
            <el-form-item label="分类">
              <el-input
                v-model="filters.category_id"
                clearable
                placeholder="分类ID"
                style="width: 220px"
                @change="resetAndLoad"
              />
            </el-form-item>
            <el-form-item label="系列标签">
              <el-input
                v-model="filters.tag_ids"
                clearable
                placeholder="tag_id（单个）"
                style="width: 220px"
                @change="resetAndLoad"
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                @click="resetAndLoad"
              >
                查询
              </el-button>
              <el-button @click="resetFilters">
                重置
              </el-button>
            </el-form-item>
          </el-form>

          <div
            v-if="listError"
            class="state-empty"
            role="alert"
          >
            加载失败：{{ listError }}
          </div>
          <div
            v-else-if="!listLoading && qualityRows.length === 0"
            class="state-empty"
          >
            暂无匹配的产品。当前筛选条件下没有待补充字段。
          </div>

          <div class="table-scroll">
            <el-table
              v-loading="listLoading"
              :data="qualityRows"
              border
              stripe
              size="small"
            >
              <el-table-column
                prop="product_no"
                label="编号"
                min-width="140"
              />
              <el-table-column
                prop="product_name"
                label="名称"
                min-width="180"
              />
              <el-table-column
                prop="completeness_status"
                label="完整度"
                width="110"
              >
                <template #default="{ row }">
                  <el-tag
                    v-if="row.completeness_status === 'pending'"
                    type="warning"
                    size="small"
                  >
                    待补充
                  </el-tag>
                  <el-tag
                    v-else-if="row.completeness_status === 'unknown'"
                    type="info"
                    size="small"
                  >
                    未知
                  </el-tag>
                  <el-tag
                    v-else
                    type="success"
                    size="small"
                  >
                    完整
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                prop="face_price_label"
                label="面价"
                min-width="110"
              />
              <el-table-column
                prop="specification"
                label="规格"
                min-width="180"
              />
              <el-table-column
                prop="supplier_name"
                label="供应商"
                min-width="140"
              />
              <el-table-column
                prop="data_source"
                label="数据来源"
                min-width="160"
              />
              <el-table-column
                prop="update_time"
                label="更新时间"
                min-width="180"
              />
            </el-table>
          </div>

          <el-pagination
            v-model:current-page="page"
            :page-size="size"
            :total="totalGreaterThan"
            layout="prev, pager, next"
            class="quality-pagination"
            @current-change="loadList"
          />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

interface QualityRow {
  id: string
  product_no: string
  product_name: string
  completeness_status: string
  face_price: number | null
  face_price_label: string
  specification: string | null
  data_source: string | null
  supplier_id: string | null
  supplier_name: string | null
  category_id: string | null
  brand_id: string | null
  create_time: string | null
  update_time: string | null
}

const summaryLoading = ref(false)
const listLoading = ref(false)
const exporting = ref(false)
const listError = ref<string | null>(null)

const summary = reactive({
  total: 0,
  no_price: 0,
  no_image: 0,
  no_manual: 0,
  no_spec: 0,
  source_incomplete: 0,
  ocr_failed: 0,
  long_pending: 0,
  by_completeness: {} as Record<string, number>,
})

const filters = reactive({
  quality_flag: '',
  completeness_status: '',
  supplier_id: '',
  category_id: '',
  tag_ids: '',
})

const qualityRows = ref<QualityRow[]>([])
const page = ref(1)
const size = ref(50)

// V1.2 — list endpoint only returns a window; for preview pagination we
// expose enough info to render a "go forward" paginator. Use the size-50
// returned list as the lower bound on total.
const totalGreaterThan = computed(() => (qualityRows.value.length === size.value
  ? page.value * size.value + size.value
  : page.value * size.value))

function buildParams(): Record<string, unknown> {
  const p: Record<string, unknown> = {
    page: page.value,
    size: size.value,
  }
  if (filters.quality_flag) p.quality_flag = filters.quality_flag
  if (filters.completeness_status) p.completeness_status = filters.completeness_status
  if (filters.supplier_id) p.supplier_id = filters.supplier_id
  if (filters.category_id) p.category_id = filters.category_id
  if (filters.tag_ids) p.tag_ids = filters.tag_ids
  return p
}

async function loadSummary() {
  summaryLoading.value = true
  try {
    const resp = await api.get('/products/quality-summary')
    Object.assign(summary, resp.data?.data || {})
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail?.msg || '加载质量汇总失败')
  } finally {
    summaryLoading.value = false
  }
}

async function loadList() {
  listLoading.value = true
  listError.value = null
  try {
    const resp = await api.get('/products/quality-list', { params: buildParams() })
    qualityRows.value = (resp.data?.data?.list || []) as QualityRow[]
  } catch (e: any) {
    listError.value = e?.response?.data?.detail?.msg || e.message || '未知错误'
    qualityRows.value = []
  } finally {
    listLoading.value = false
  }
}

function resetAndLoad() {
  page.value = 1
  loadList()
}

function resetFilters() {
  filters.quality_flag = ''
  filters.completeness_status = ''
  filters.supplier_id = ''
  filters.category_id = ''
  filters.tag_ids = ''
  page.value = 1
  loadList()
}

async function exportQuality() {
  exporting.value = true
  try {
    const resp = await api.get('/products/quality-export', {
      params: buildParams(),
      responseType: 'blob',
    })
    const url = window.URL.createObjectURL(new Blob([resp.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', 'quality_export.xlsx')
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail?.msg || '导出失败')
  } finally {
    exporting.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadSummary(), loadList()])
})
</script>

<style scoped>
.quality-page {
  padding: 0 4px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stats-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.stat-pill {
  min-width: 110px;
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid rgba(30, 50, 90, 0.08);
  text-align: center;
}

.stat-pill.warn {
  background: #fffbeb;
  border-color: #f5d97b;
}

.stat-pill.err {
  background: #fef0f0;
  border-color: #f5a0a0;
}

.stat-num {
  font-size: 22px;
  font-weight: 600;
  color: rgba(30, 50, 90, 0.85);
}

.stat-pill.warn .stat-num {
  color: #b8860b;
}

.stat-pill.err .stat-num {
  color: #c0392b;
}

.stat-label {
  margin-top: 4px;
  font-size: 12px;
  color: rgba(30, 50, 90, 0.6);
}

.quality-filters {
  margin-bottom: 12px;
}

.table-scroll {
  overflow-x: auto;
}

.state-empty {
  margin: 24px 0;
  padding: 18px;
  text-align: center;
  border: 1px dashed rgba(30, 50, 90, 0.18);
  border-radius: 12px;
  color: rgba(30, 50, 90, 0.6);
}

.quality-pagination {
  margin-top: 12px;
  text-align: right;
}

@media (max-width: 600px) {
  .stat-pill {
    min-width: 88px;
  }
}
</style>
