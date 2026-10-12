<template>
  <el-drawer
    :model-value="modelValue"
    title="我的待办"
    size="420px"
    direction="rtl"
    class="todo-drawer"
    @update:model-value="onVisibleChange"
  >
    <div class="todo-body">
      <div class="todo-summary">
        共 <strong>{{ totalPending }}</strong> 项待处理
        <el-button
          text
          size="small"
          class="todo-refresh"
          :loading="loading"
          @click="load"
        >
          刷新
        </el-button>
      </div>

      <section class="todo-section">
        <h3 class="todo-section__title">
          提醒
          <span class="todo-section__count">{{ reminders.length }}</span>
        </h3>
        <p
          v-if="!reminders.length"
          class="todo-empty"
        >
          暂无提醒
        </p>
        <ul
          v-else
          class="todo-list"
        >
          <li
            v-for="r in reminders"
            :key="r.id"
            class="todo-item"
          >
            <div class="todo-item__main">
              <div class="todo-item__title">
                {{ r.title }}
              </div>
              <div class="todo-item__meta">
                <el-tag
                  size="small"
                  :type="r.status === 'overdue' ? 'danger' : 'info'"
                  class="capsule-tag"
                >
                  {{ labelOf(REMINDER_STATUS_MAP, r.status) }}
                </el-tag>
                <span class="todo-item__time">截止 {{ formatBeijingTime(r.due_at) || '—' }}</span>
              </div>
              <div
                v-if="r.body"
                class="todo-item__body"
              >
                {{ r.body }}
              </div>
            </div>
            <div class="todo-item__actions">
              <el-button
                size="small"
                text
                class="action-link"
                @click="doneReminder(r)"
              >
                完成
              </el-button>
              <el-dropdown
                trigger="click"
                @command="(d: number) => snoozeReminder(r, d)"
              >
                <el-button
                  size="small"
                  text
                  class="action-link"
                >
                  推迟
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item :command="1">
                      推迟 1 天
                    </el-dropdown-item>
                    <el-dropdown-item :command="3">
                      推迟 3 天
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </li>
        </ul>
      </section>

      <section class="todo-section">
        <h3 class="todo-section__title">
          跟进
          <span class="todo-section__count">{{ followUps.length }}</span>
        </h3>
        <p
          v-if="!followUps.length"
          class="todo-empty"
        >
          暂无待跟进
        </p>
        <ul
          v-else
          class="todo-list"
        >
          <li
            v-for="f in followUps"
            :key="f.id"
            class="todo-item"
          >
            <div class="todo-item__main">
              <div class="todo-item__title">
                {{ f.content }}
              </div>
              <div class="todo-item__meta">
                <el-tag
                  size="small"
                  type="info"
                  class="capsule-tag"
                >
                  {{ labelOf(FOLLOW_UP_METHOD_MAP, f.method) }}
                </el-tag>
                <span class="todo-item__time">
                  下次 {{ formatBeijingTime(f.next_follow_at) || '—' }}
                </span>
              </div>
            </div>
            <div class="todo-item__actions">
              <el-button
                size="small"
                text
                class="action-link"
                @click="goCustomer(f.customer_id)"
              >
                查看客户
              </el-button>
            </div>
          </li>
        </ul>
      </section>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { dashboardApi, type TodoFollowUp, type TodoReminder } from '@/api/dashboard'
import { reminderApi } from '@/api/reminder'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'
import { FOLLOW_UP_METHOD_MAP, REMINDER_STATUS_MAP, labelOf } from '@/constants/crm'
import { formatBeijingTime } from '@/utils/beijingTime'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const router = useRouter()
const authStore = useAuthStore()

const reminders = ref<TodoReminder[]>([])
const followUps = ref<TodoFollowUp[]>([])
const totalPending = ref(0)
const loading = ref(false)

function onVisibleChange(value: boolean) {
  emit('update:modelValue', value)
}

async function load() {
  if (!hasPermission(authStore.permissions, 'dashboard:view')) return
  loading.value = true
  try {
    const res = await dashboardApi.todos(20)
    reminders.value = res.data.reminders
    followUps.value = res.data.follow_ups
    totalPending.value = res.data.total_pending
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

async function doneReminder(r: TodoReminder) {
  try {
    await reminderApi.done(r.id)
    ElMessage.success('已完成')
    await load()
  } catch {
    // ignore
  }
}

async function snoozeReminder(r: TodoReminder, days: number) {
  const until = new Date(Date.now() + days * 24 * 3600 * 1000).toISOString()
  try {
    await reminderApi.snooze(r.id, until)
    ElMessage.success(`已推迟 ${days} 天`)
    await load()
  } catch {
    // ignore
  }
}

function goCustomer(customerId: string) {
  emit('update:modelValue', false)
  router.push(`/customers/${customerId}`)
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) load()
  },
)
</script>

<style scoped>
.todo-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.todo-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--pim-text-secondary);
  font-size: 13px;
}

.todo-summary strong {
  color: var(--pim-accent-solid);
  font-size: 16px;
}

.todo-refresh {
  margin-left: auto;
}

.todo-section__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  font-size: 14px;
  color: var(--pim-text-primary);
}

.todo-section__count {
  display: inline-grid;
  place-items: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 10px;
  background: rgba(var(--pim-brand), 0.08);
  font-size: 11px;
  color: var(--pim-text-secondary);
}

.todo-empty {
  margin: 0;
  padding: 12px 0;
  color: var(--pim-text-secondary);
  font-size: 13px;
}

.todo-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.todo-item {
  display: flex;
  gap: 8px;
  padding: 12px;
  border: 1px solid var(--pim-border);
  border-radius: 14px;
}

.todo-item__main {
  flex: 1;
  min-width: 0;
}

.todo-item__title {
  color: var(--pim-text-primary);
  font-size: 13px;
  line-height: 1.4;
}

.todo-item__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}

.todo-item__time {
  color: var(--pim-text-secondary);
  font-size: 12px;
}

.todo-item__body {
  margin-top: 6px;
  color: var(--pim-text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.todo-item__actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}
</style>
