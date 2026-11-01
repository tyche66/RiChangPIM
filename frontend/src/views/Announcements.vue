<template>
  <div class="announcements-page">
    <el-card>
      <div class="toolbar">
        <h2>公告管理</h2>
        <div class="toolbar-actions">
          <el-select
            v-model="filters.status"
            placeholder="全部状态"
            clearable
            class="filter-select"
            @change="fetchList"
          >
            <el-option
              label="生效中"
              value="active"
            />
            <el-option
              label="待发布"
              value="scheduled"
            />
            <el-option
              label="已过期"
              value="expired"
            />
            <el-option
              label="已停用"
              value="disabled"
            />
          </el-select>
          <el-select
            v-model="filters.audience"
            placeholder="全部受众"
            clearable
            class="filter-select"
            @change="fetchList"
          >
            <el-option
              label="仅后台"
              value="admin"
            />
            <el-option
              label="仅门户"
              value="portal"
            />
            <el-option
              label="全部"
              value="all"
            />
          </el-select>
          <el-checkbox
            v-model="filters.include_deleted"
            label="含已删除"
            @change="fetchList"
          />
          <el-button
            v-if="canManage"
            type="primary"
            @click="openCreate"
          >
            新建公告
          </el-button>
        </div>
      </div>

      <div class="table-responsive">
        <el-table
          v-loading="loading"
          :data="rows"
          border
          stripe
        >
          <el-table-column
            prop="title"
            label="标题"
            min-width="200"
            class-name="cell-strong"
            show-overflow-tooltip
          />
          <el-table-column
            label="受众"
            width="100"
            align="center"
          >
            <template #default="{ row }">
              {{ audienceLabel(row.audience) }}
            </template>
          </el-table-column>
          <el-table-column
            label="级别"
            width="90"
            align="center"
          >
            <template #default="{ row }">
              <el-tag
                :type="row.level === 'important' ? 'warning' : 'info'"
                size="small"
              >
                {{ row.level === 'important' ? '重要' : '普通' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            label="状态"
            width="110"
            align="center"
          >
            <template #default="{ row }">
              <el-tooltip
                v-if="row.is_deleted"
                :content="`删除时间：${formatBeijingTime(row.deleted_at)}`"
                placement="top"
              >
                <el-tag
                  type="danger"
                  size="small"
                >
                  已删除
                </el-tag>
              </el-tooltip>
              <el-tag
                v-else
                :type="statusTagType(deriveStatus(row))"
                size="small"
              >
                {{ statusLabel(deriveStatus(row)) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            label="发布时间"
            width="170"
            class-name="cell-soft"
          >
            <template #default="{ row }">
              {{ row.publish_at ? formatBeijingTime(row.publish_at) : '立即' }}
            </template>
          </el-table-column>
          <el-table-column
            label="过期时间"
            width="170"
            class-name="cell-soft"
          >
            <template #default="{ row }">
              {{ row.expire_at ? formatBeijingTime(row.expire_at) : '不过期' }}
            </template>
          </el-table-column>
          <el-table-column
            label="更新时间"
            width="170"
            class-name="cell-soft"
          >
            <template #default="{ row }">
              {{ formatBeijingTime(row.update_time) }}
            </template>
          </el-table-column>
          <el-table-column
            v-if="canManage"
            label="操作"
            width="220"
            align="center"
          >
            <template #default="{ row }">
              <template v-if="!row.is_deleted">
                <el-button
                  size="small"
                  text
                  class="action-link"
                  @click="openPreview(row)"
                >
                  预览
                </el-button>
                <el-button
                  size="small"
                  text
                  class="action-link"
                  @click="openEdit(row)"
                >
                  编辑
                </el-button>
                <el-button
                  size="small"
                  text
                  class="action-link"
                  @click="toggleEnabled(row)"
                >
                  {{ row.enabled ? '停用' : '启用' }}
                </el-button>
                <el-button
                  size="small"
                  text
                  class="action-link danger"
                  @click="handleDelete(row)"
                >
                  删除
                </el-button>
              </template>
              <span
                v-else
                class="cell-meta"
              >-</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="fetchList"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="editorVisible"
      :title="editingId ? '编辑公告' : '新建公告'"
      width="680px"
      align-center
      destroy-on-close
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-width="90px"
      >
        <el-form-item
          label="标题"
          prop="title"
        >
          <el-input
            v-model="form.title"
            maxlength="200"
            show-word-limit
            placeholder="公告标题"
          />
        </el-form-item>
        <el-form-item
          label="正文"
          prop="content_md"
        >
          <el-input
            v-model="form.content_md"
            type="textarea"
            :rows="10"
            maxlength="20000"
            show-word-limit
            placeholder="受限 Markdown：标题 / 粗斜体 / 列表 / 引用 / 表格 / 代码 / 链接"
          />
        </el-form-item>
        <el-form-item label="受众">
          <el-radio-group v-model="form.audience">
            <el-radio-button value="admin">
              仅后台
            </el-radio-button>
            <el-radio-button value="portal">
              仅门户
            </el-radio-button>
            <el-radio-button value="all">
              全部
            </el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="级别">
          <el-radio-group v-model="form.level">
            <el-radio-button value="info">
              普通
            </el-radio-button>
            <el-radio-button value="important">
              重要
            </el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="发布时间">
          <el-date-picker
            v-model="form.publish_at"
            type="datetime"
            placeholder="留空表示立即发布"
            value-format="YYYY-MM-DDTHH:mm:ss"
            class="time-picker"
          />
        </el-form-item>
        <el-form-item label="过期时间">
          <el-date-picker
            v-model="form.expire_at"
            type="datetime"
            placeholder="留空表示不过期"
            value-format="YYYY-MM-DDTHH:mm:ss"
            class="time-picker"
          />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
          <span class="form-hint">停用即草稿，不会向任何端下发</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editorVisible = false">取消</el-button>
        <el-button
          :loading="saving"
          type="primary"
          @click="handleSave"
        >
          保存
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="previewVisible"
      :title="previewRow?.title || '公告预览'"
      width="640px"
      align-center
    >
      <div
        class="announcement-md"
        v-html="previewHtml"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { announcementApi } from '@/api/announcement'
import type {
  Announcement,
  AnnouncementAudience,
  AnnouncementLevel,
  AnnouncementStatus,
} from '@/api/announcement'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'
import { renderMarkdown } from '@/utils/markdown'
import { beijingLocalToInstant, formatBeijingTime } from '@/utils/beijingTime'

const authStore = useAuthStore()
const canManage = computed(
  () => authStore.userRoleCode === 'admin' && hasPermission(authStore.userPermissions, 'announcement:manage'),
)

const loading = ref(false)
const rows = ref<Announcement[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const filters = reactive({
  status: undefined as AnnouncementStatus | undefined,
  audience: undefined as AnnouncementAudience | undefined,
  include_deleted: false,
})

const editorVisible = ref(false)
const saving = ref(false)
const editingId = ref<string | null>(null)
const formRef = ref<FormInstance | null>(null)

const previewVisible = ref(false)
const previewRow = ref<Announcement | null>(null)
const previewHtml = computed(() => renderMarkdown(previewRow.value?.content_md || ''))

const emptyForm = () => ({
  title: '',
  content_md: '',
  audience: 'all' as AnnouncementAudience,
  level: 'info' as AnnouncementLevel,
  enabled: true,
  publish_at: null as string | null,
  expire_at: null as string | null,
})
const form = reactive(emptyForm())

const formRules: FormRules = {
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
  content_md: [{ required: true, message: '请输入正文', trigger: 'blur' }],
}

function audienceLabel(audience: AnnouncementAudience): string {
  if (audience === 'admin') return '仅后台'
  if (audience === 'portal') return '仅门户'
  return '全部'
}

function deriveStatus(row: Announcement): AnnouncementStatus {
  if (!row.enabled) return 'disabled'
  if (row.publish_at && new Date(row.publish_at).getTime() > Date.now()) return 'scheduled'
  if (row.expire_at && new Date(row.expire_at).getTime() <= Date.now()) return 'expired'
  return 'active'
}

function statusLabel(status: AnnouncementStatus): string {
  const map: Record<AnnouncementStatus, string> = {
    active: '生效中',
    scheduled: '待发布',
    expired: '已过期',
    disabled: '已停用',
  }
  return map[status]
}

function statusTagType(status: AnnouncementStatus): 'success' | 'warning' | 'info' | 'danger' {
  if (status === 'active') return 'success'
  if (status === 'scheduled') return 'warning'
  if (status === 'expired') return 'danger'
  return 'info'
}

async function fetchList() {
  loading.value = true
  try {
    const res = await announcementApi.list({
      status: filters.status,
      audience: filters.audience,
      include_deleted: filters.include_deleted || undefined,
      page: page.value,
      page_size: pageSize,
    })
    rows.value = res.data.list
    total.value = res.data.total
  } catch {
    ElMessage.error('加载公告列表失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, emptyForm())
  editorVisible.value = true
}

function openEdit(row: Announcement) {
  editingId.value = row.id
  Object.assign(form, {
    title: row.title,
    content_md: row.content_md,
    audience: row.audience,
    level: row.level,
    enabled: row.enabled,
    // 展示口径是北京时间，编辑框回填同一口径的字面量（YYYY-MM-DDTHH:mm:ss）。
    publish_at: row.publish_at ? formatBeijingTime(row.publish_at).replace(' ', 'T') : null,
    expire_at: row.expire_at ? formatBeijingTime(row.expire_at).replace(' ', 'T') : null,
  })
  editorVisible.value = true
}

function openPreview(row: Announcement) {
  previewRow.value = row
  previewVisible.value = true
}

/** 编辑框里的北京时间字面量 → UTC 瞬时；空值原样传 null。 */
function toInstantOrEmpty(value: string | null): string | null {
  if (!value) return null
  return beijingLocalToInstant(value)
}

async function handleSave() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (form.expire_at && form.publish_at && form.expire_at <= form.publish_at) {
    ElMessage.error('过期时间必须晚于发布时间')
    return
  }
  saving.value = true
  const payload = {
    title: form.title,
    content_md: form.content_md,
    audience: form.audience,
    level: form.level,
    enabled: form.enabled,
    publish_at: toInstantOrEmpty(form.publish_at),
    expire_at: toInstantOrEmpty(form.expire_at),
  }
  try {
    if (editingId.value) {
      await announcementApi.update(editingId.value, payload)
      ElMessage.success('更新成功')
    } else {
      await announcementApi.create(payload)
      ElMessage.success('创建成功')
    }
    editorVisible.value = false
    await fetchList()
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function toggleEnabled(row: Announcement) {
  try {
    await announcementApi.update(row.id, { enabled: !row.enabled })
    ElMessage.success(row.enabled ? '已停用' : '已启用')
    await fetchList()
  } catch {
    ElMessage.error('操作失败')
  }
}

async function handleDelete(row: Announcement) {
  try {
    await ElMessageBox.confirm(`确定删除公告「${row.title}」？删除后不再下发，但列表可追溯。`, '确认删除', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await announcementApi.remove(row.id)
    ElMessage.success('删除成功')
    await fetchList()
  } catch {
    ElMessage.error('删除失败')
  }
}

onMounted(fetchList)
</script>

<style scoped>
.announcements-page {
  padding: 20px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}

.toolbar h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: rgb(var(--pim-brand));
  letter-spacing: 0.3px;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.filter-select {
  width: 130px;
}

.toolbar :deep(.el-button) {
  border-radius: 20px;
}

.table-responsive {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  border-radius: 12px;
}

.table-responsive :deep(.el-table) {
  min-width: 900px;
  border-radius: 12px;
  overflow: hidden;
}

.cell-meta {
  color: var(--pim-text-faint);
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.time-picker {
  width: 100%;
}

.form-hint {
  margin-left: 12px;
  font-size: 12px;
  color: var(--pim-text-faint);
}

/* 公告 Markdown 预览样式：补标题 / 列表 / 引用 / 代码（FR-4 §4.5）。
   颜色全部走 design token，不引入新的硬编码色值。 */
.announcement-md {
  line-height: 1.7;
  word-break: break-word;
}

.announcement-md :deep(.md-h) {
  margin: 16px 0 8px;
  font-weight: 600;
  color: rgb(var(--pim-brand));
}

.announcement-md :deep(.md-h:first-child) {
  margin-top: 0;
}

.announcement-md :deep(.md-p) {
  margin: 0 0 10px;
}

.announcement-md :deep(.md-list) {
  margin: 0 0 10px;
  padding-left: 22px;
}

.announcement-md :deep(.md-li) {
  line-height: 1.8;
}

.announcement-md :deep(.md-quote) {
  margin: 0 0 10px;
  padding: 8px 14px;
  border-left: 3px solid rgba(var(--pim-brand), 0.35);
  background: var(--pim-primary-06);
  border-radius: 6px;
  color: var(--pim-text-secondary);
}

.announcement-md :deep(.md-pre) {
  margin: 0 0 10px;
  padding: 12px;
  border-radius: 8px;
  background: var(--pim-primary-06);
  overflow-x: auto;
  font-family: var(--pim-font-mono);
  font-size: 13px;
}

.announcement-md :deep(.md-code-inline) {
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--pim-primary-12);
  font-family: var(--pim-font-mono);
  font-size: 13px;
}

.announcement-md :deep(.md-link) {
  color: rgb(var(--pim-brand));
  font-weight: 500;
}

.announcement-md :deep(.md-table-scroll) {
  overflow-x: auto;
  margin-bottom: 10px;
}

.announcement-md :deep(.md-table) {
  border-collapse: collapse;
}

.announcement-md :deep(.md-th),
.announcement-md :deep(.md-td) {
  border: 1px solid var(--pim-line-strong);
  padding: 6px 12px;
  text-align: left;
}

.announcement-md :deep(.md-th) {
  background: var(--pim-primary-06);
  font-weight: 600;
}

@media (max-width: 768px) {
  .announcements-page {
    padding: 12px;
  }
  .toolbar {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
