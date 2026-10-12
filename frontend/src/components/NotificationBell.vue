<template>
  <el-popover
    placement="bottom-end"
    :width="360"
    trigger="click"
    popper-class="notification-popper"
    @show="load"
  >
    <template #reference>
      <button
        type="button"
        class="bell-btn"
        aria-label="通知"
        title="通知"
      >
        <el-badge
          :value="unreadCount"
          :hidden="unreadCount === 0"
          :max="99"
        >
          <el-icon :size="19">
            <Bell />
          </el-icon>
        </el-badge>
      </button>
    </template>

    <div class="bell-panel">
      <div class="bell-head">
        <strong>通知</strong>
        <el-button
          text
          size="small"
          :disabled="unreadCount === 0"
          @click="markAll"
        >
          全部已读
        </el-button>
      </div>
      <div
        v-if="loading"
        class="bell-empty"
      >
        加载中…
      </div>
      <div
        v-else-if="!items.length"
        class="bell-empty"
      >
        暂无通知
      </div>
      <ul
        v-else
        class="bell-list"
      >
        <li
          v-for="n in items"
          :key="n.id"
          class="bell-item"
          :class="{ 'is-unread': !n.read_at }"
          @click="open(n)"
        >
          <div class="bell-item__title">
            {{ n.title }}
          </div>
          <div
            v-if="n.body"
            class="bell-item__body"
          >
            {{ n.body }}
          </div>
          <div class="bell-item__time">
            {{ formatBeijingTime(n.create_time) }}
          </div>
        </li>
      </ul>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Bell } from '@element-plus/icons-vue'
import { reminderApi, type Notification } from '@/api/reminder'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'
import { formatBeijingTime } from '@/utils/beijingTime'

const router = useRouter()
const authStore = useAuthStore()

const items = ref<Notification[]>([])
const unreadCount = ref(0)
const loading = ref(false)

const canRead = () => hasPermission(authStore.permissions, 'reminder:edit')

async function load() {
  if (!canRead()) return
  loading.value = true
  try {
    const res = await reminderApi.notifications()
    items.value = res.data.list
    unreadCount.value = items.value.filter((n) => !n.read_at).length
  } catch {
    // 拦截器已提示；铃铛保持上一次状态
  } finally {
    loading.value = false
  }
}

async function markAll() {
  try {
    await reminderApi.markRead({ all: true })
    await load()
  } catch {
    // ignore
  }
}

async function open(n: Notification) {
  if (!n.read_at) {
    try {
      await reminderApi.markRead({ ids: [n.id] })
      n.read_at = new Date().toISOString()
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    } catch {
      // ignore
    }
  }
  if (n.link) router.push(n.link)
}

onMounted(load)
</script>

<style scoped>
.bell-btn {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border: 0;
  border-radius: 50%;
  background: rgba(var(--pim-brand), 0.08);
  color: rgba(var(--pim-brand), 0.8);
  cursor: pointer;
  transition: background 200ms ease;
}

.bell-btn:hover {
  background: rgba(var(--pim-brand), 0.14);
}

.bell-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 4px 10px;
  border-bottom: 1px solid var(--pim-border);
}

.bell-empty {
  padding: 24px 8px;
  text-align: center;
  color: var(--pim-text-secondary);
  font-size: 13px;
}

.bell-list {
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 360px;
  overflow-y: auto;
}

.bell-item {
  padding: 10px 8px;
  border-radius: 12px;
  cursor: pointer;
  transition: background 160ms ease;
}

.bell-item:hover {
  background: rgba(var(--pim-brand), 0.06);
}

.bell-item.is-unread .bell-item__title {
  font-weight: 600;
}

.bell-item.is-unread::before {
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 6px;
  border-radius: 50%;
  background: var(--pim-accent-solid);
  vertical-align: middle;
}

.bell-item__title {
  color: var(--pim-text-primary);
  font-size: 13px;
  line-height: 1.4;
}

.bell-item__body {
  margin-top: 2px;
  color: var(--pim-text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.bell-item__time {
  margin-top: 4px;
  color: var(--pim-text-secondary);
  font-size: 11px;
  opacity: 0.8;
}
</style>
