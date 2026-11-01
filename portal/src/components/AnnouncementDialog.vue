<script setup lang="ts">
/**
 * 门户公告弹层（FR-4）。
 *
 * 进入首页 / 对话页时检查一次 audience=portal 的公告（/active 是匿名接口，
 * 未登录也可见）；分享页 /share/:token 不挂载本组件，因此不发请求也不弹。
 * 多条按发布时间新→旧排队逐条弹出（后端 /active 已按该顺序返回），已读状态
 * 写 localStorage announcement_seen:<id>，同一条公告同一浏览器只弹一次。
 * 每次刷新都会重新检查（无轮询）。请求失败静默，不影响页面主流程。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { renderMarkdown } from '@/utils/markdown'
import { formatDateTime } from '@/utils/format'

type AnnouncementActive = {
  id: string
  title: string
  content_md: string
  level: 'info' | 'important'
  audience: 'admin' | 'portal' | 'all'
  publish_at: string | null
  update_time: string | null
}

const SEEN_PREFIX = 'announcement_seen:'

const queue = ref<AnnouncementActive[]>([])
const dialog = ref<HTMLDialogElement | null>(null)

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

watch(current, (value) => {
  const el = dialog.value
  if (!el) return
  if (value && !el.open) el.showModal()
  if (!value && el.open) el.close()
})

onMounted(async () => {
  try {
    const response = await fetch('/api/v1/announcements/active?audience=portal')
    if (!response.ok) return
    const payload = await response.json().catch(() => null)
    const list: AnnouncementActive[] = payload?.data?.list || []
    queue.value = list.filter((item) => item.id && !isSeen(item.id))
  } catch {
    // 公告检查失败不打扰主流程
  }
})
</script>

<template>
  <dialog
    ref="dialog"
    class="announcement-dialog"
    aria-label="系统公告"
    @close="dismiss"
  >
    <div v-if="current" class="announcement-dialog__body">
      <div class="announcement-dialog__meta">
        <span class="announcement-dialog__chip" :class="{ 'announcement-dialog__chip--important': current.level === 'important' }">
          {{ current.level === 'important' ? '重要公告' : '公告' }}
        </span>
        <span v-if="current.publish_at" class="announcement-dialog__time">{{ formatDateTime(current.publish_at) }}</span>
      </div>
      <h2 class="announcement-dialog__title">{{ current.title }}</h2>
      <!-- renderMarkdown 先整体转义再按白名单输出标签，v-html 只接收白名单输出 -->
      <div class="announcement-md" v-html="renderedContent" />
    </div>
    <div class="announcement-dialog__footer">
      <span v-if="remaining > 0" class="announcement-dialog__remaining">还有 {{ remaining }} 条公告</span>
      <button type="button" class="button button--primary" @click="dismiss">我知道了</button>
    </div>
  </dialog>
</template>

<style scoped>
.announcement-dialog {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 0;
  width: min(560px, calc(100vw - 32px));
  max-height: min(70vh, 640px);
  display: flex;
  flex-direction: column;
  background: var(--surface);
  color: var(--ink);
  box-shadow: var(--shadow-pop);
}

.announcement-dialog::backdrop {
  background: var(--scrim-dialog);
}

.announcement-dialog__body {
  padding: 20px 22px 8px;
  overflow-y: auto;
}

.announcement-dialog__meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.announcement-dialog__chip {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: var(--radius-pill);
  background: var(--surface-strong);
  color: var(--ink-muted);
}

.announcement-dialog__chip--important {
  background: var(--warn-bg);
  color: var(--warn-ink);
  border: 1px solid var(--warn-border);
}

.announcement-dialog__time {
  font-size: 12px;
  color: var(--ink-subtle);
}

.announcement-dialog__title {
  margin: 0 0 12px;
  font-size: 17px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.announcement-dialog__footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding: 12px 22px 16px;
  border-top: 1px solid var(--border);
}

.announcement-dialog__remaining {
  font-size: 12px;
  color: var(--ink-subtle);
  margin-right: auto;
}
</style>
