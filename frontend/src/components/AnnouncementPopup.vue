<template>
  <el-dialog
    :model-value="current !== null"
    :title="current?.title || '公告'"
    width="560px"
    align-center
    :close-on-click-modal="false"
    :show-close="false"
    class="announcement-popup"
    @update:model-value="dismiss"
  >
    <div
      v-if="current"
      class="popup-body"
    >
      <div class="popup-meta">
        <el-tag
          :type="current.level === 'important' ? 'warning' : 'info'"
          size="small"
        >
          {{ current.level === 'important' ? '重要公告' : '公告' }}
        </el-tag>
        <span
          v-if="current.publish_at"
          class="popup-time"
        >{{ formatBeijingTime(current.publish_at) }}</span>
      </div>
      <!-- renderMarkdown 先整体转义再按白名单输出标签，v-html 只接收白名单输出 -->
      <div
        class="announcement-md"
        v-html="renderedContent"
      />
    </div>
    <template #footer>
      <div class="popup-footer">
        <span
          v-if="remaining > 0"
          class="popup-remaining"
        >还有 {{ remaining }} 条公告</span>
        <el-button
          type="primary"
          @click="dismiss"
        >
          我知道了
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * 后台公告弹窗（FR-4）。
 *
 * 登录后 / 应用启动时检查一次 admin 受众公告；多条按发布时间新→旧排队
 * 逐条弹出（后端 /active 已按该顺序返回）。已读状态写 localStorage
 * announcement_seen:<id>，同一条公告同一浏览器只弹一次。请求失败静默，
 * 不影响任何现有页面。
 */
import { computed, onMounted, ref } from 'vue'
import { announcementApi } from '@/api/announcement'
import type { AnnouncementActive } from '@/api/announcement'
import { useAuthStore } from '@/stores/auth'
import { renderMarkdown } from '@/utils/markdown'
import { formatBeijingTime } from '@/utils/beijingTime'

const SEEN_PREFIX = 'announcement_seen:'

const authStore = useAuthStore()
const queue = ref<AnnouncementActive[]>([])

const current = computed(() => queue.value[0] ?? null)
const remaining = computed(() => Math.max(queue.value.length - 1, 0))
const renderedContent = computed(() => renderMarkdown(current.value?.content_md || ''))

function isSeen(id: string): boolean {
  try {
    return localStorage.getItem(`${SEEN_PREFIX}${id}`) === '1'
  } catch {
    return false
  }
}

function markSeen(id: string) {
  try {
    localStorage.setItem(`${SEEN_PREFIX}${id}`, '1')
  } catch {
    // localStorage 不可用（隐私模式等）时放弃持久化已读，仅本次会话内不再弹
  }
}

function dismiss() {
  const head = queue.value[0]
  if (head) markSeen(head.id)
  queue.value = queue.value.slice(1)
}

async function checkAnnouncements() {
  if (!authStore.isAuthenticated) return
  try {
    const res = await announcementApi.active('admin')
    queue.value = (res.data?.list || []).filter((item) => !isSeen(item.id))
  } catch {
    // 公告检查失败不打扰主流程
  }
}

onMounted(checkAnnouncements)
</script>

<style scoped>
.popup-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.popup-time {
  font-size: 12px;
  color: var(--pim-text-faint);
}

.popup-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}

.popup-remaining {
  font-size: 12px;
  color: var(--pim-text-faint);
}

/* 公告正文样式：标题 / 列表 / 引用 / 代码（FR-4 §4.5），颜色全走 token。 */
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
</style>
